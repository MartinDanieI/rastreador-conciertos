"""Fuente: Tuboleta (https://www.tuboleta.com).

Cómo está hecha la página (revisado el 2026-11-20):
    - www.tuboleta.com es Drupal detrás de Cloudflare, sin captcha ni fila virtual.
    - La categoría /es/categorias/conciertos trae TODOS los eventos en el HTML
      (no hace falta JavaScript ni Playwright). Cada tarjeta tiene título,
      lugar, ciudad y fecha corta ("28 Nov", sin año).
    - El link de cada tarjeta (/es/eventos/<slug>) redirige a
      eventos.tuboleta.com/<slug> (HubSpot). Esa página trae un JSON-LD
      schema.org/MusicEvent con la fecha y hora exactas.
    - robots.txt permite /es/categorias/ y /es/eventos/ (solo bloquea /admin,
      /user, /search, /core, etc.).

Para no cargar el sitio, la lista sale de UNA sola petición. El detalle
(fecha exacta) solo se pide para los eventos que el bot todavía no conoce.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

FUENTE = "tuboleta"
BASE = "https://www.tuboleta.com"
URL_CONCIERTOS = f"{BASE}/es/categorias/conciertos"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0 Safari/537.36 rastreador-conciertos",
    "Accept-Language": "es-CO,es;q=0.9",
}
TIMEOUT = 30

MESES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
         "jul": 7, "ago": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12}


class FuenteError(RuntimeError):
    """La fuente no respondió o cambió su diseño."""


def _texto(el) -> str:
    return " ".join(el.get_text(" ", strip=True).split()) if el else ""


def _artista(titulo: str, ciudad: str) -> str:
    """'BEÉLE | BORONDO TOUR 2026 - MEDELLÍN' -> 'BEÉLE'.

    Sin '|' el título suele ser el artista, a veces con ' - CIUDAD' al final.
    Es una aproximación: el detalle (JSON-LD performer) la corrige cuando existe.
    """
    if "|" in titulo:
        return titulo.split("|", 1)[0].strip()
    if ciudad and titulo.lower().endswith(f" - {ciudad.lower()}"):
        return titulo[: -len(ciudad) - 3].strip()
    return titulo.strip()


def _fecha_corta(texto: str, hoy: date) -> str | None:
    """'28 Nov' -> '2026-11-28'. Sin año: si ya pasó hace más de 2 meses, es el año siguiente."""
    m = re.match(r"(\d{1,2})\s+([A-Za-zé]{3})", texto)
    if not m or m.group(2).lower()[:3] not in MESES:
        return None
    dia, mes = int(m.group(1)), MESES[m.group(2).lower()[:3]]
    try:
        f = date(hoy.year, mes, dia)
        if (hoy - f).days > 60:
            f = date(hoy.year + 1, mes, dia)
    except ValueError:
        return None
    return f.isoformat()


def obtener_eventos(session: requests.Session | None = None, hoy: date | None = None) -> list[dict]:
    """Lista de conciertos de Tuboleta: artista, evento, fecha, ciudad, lugar, link."""
    s = session or requests.Session()
    hoy = hoy or date.today()
    try:
        r = s.get(URL_CONCIERTOS, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
    except requests.RequestException as exc:
        raise FuenteError(f"Tuboleta no respondió: {exc}") from exc

    soup = BeautifulSoup(r.text, "html.parser")
    eventos: dict[str, dict] = {}
    for a in soup.select("article a.content-link-container[href*='/eventos/']"):
        link = requests.compat.urljoin(BASE, a["href"])
        if link in eventos:
            continue
        info = a.select(".content-info > div")
        titulo = _texto(info[0]) if info else ""
        if not titulo:
            continue
        fecha_el = a.select_one(".content-date .d-md-none") or a.select_one(".content-date")
        ciudad = _texto(info[2]) if len(info) > 2 else ""
        eventos[link] = {
            "fuente": FUENTE,
            "artista": _artista(titulo, ciudad),
            "evento": titulo,
            "fecha": _fecha_corta(_texto(fecha_el), hoy),
            "hora": None,
            "ciudad": ciudad,
            "lugar": _texto(info[1]) if len(info) > 1 else "",
            "link": link,
            "preventa": None,
        }

    if not eventos:
        raise FuenteError("Tuboleta devolvió 0 eventos: probablemente cambió el diseño de la página")
    return list(eventos.values())


_DIA = r"(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)"
_HORA = r"(\d{1,2}):(\d{2})\s*([ap])\.?\s*m"
# "Preventa Clientes Movistar Total (AGOTADO): Martes 1 de septiembre a las 12:00 p.m. hasta…"
# "Preventa tarjetas Davivienda*, DaviPlata y Davibank Lunes 14 de septiembre, 11:00 a.m. a…"
RE_PREVENTA = re.compile(
    rf"\b(Pre-?venta[^:.]{{0,80}}?):?\s*{_DIA}\s+(\d{{1,2}})\s+de\s+([a-záéíóú]+),?\s*(?:a\s+las\s*)?{_HORA}",
    re.IGNORECASE)
RE_HORA = re.compile(rf"\bHora:\s*{_HORA}", re.IGNORECASE)


def _hora24(h: str, m: str, ampm: str) -> str:
    h24 = int(h) % 12 + (12 if ampm.lower() == "p" else 0)
    return f"{h24:02d}:{m}"


def _preventas(texto: str, fecha_evento: str | None) -> list[dict]:
    """Etapas de preventa con su inicio ('2026-09-01T12:00'). El año sale de la fecha del evento."""
    anio_evento = int(fecha_evento[:4]) if fecha_evento else date.today().year
    out: dict[str, dict] = {}
    for m in RE_PREVENTA.finditer(texto):
        nombre, dia, mes, h, mi, ampm = m.groups()
        if mes.lower()[:3] not in MESES:
            continue
        try:
            f = date(anio_evento, MESES[mes.lower()[:3]], int(dia))
            if fecha_evento and f.isoformat() > fecha_evento[:10]:
                f = date(anio_evento - 1, f.month, f.day)  # la preventa no puede ser después del evento
        except ValueError:
            continue
        nombre = re.sub(r"\(.*?\)|\*", "", nombre).strip(" ,:")
        inicio = f"{f.isoformat()}T{_hora24(h, mi, ampm)}"
        out.setdefault(inicio + nombre.lower(), {"nombre": nombre, "inicio": inicio})
    return sorted(out.values(), key=lambda p: p["inicio"])


def _eventos_ld(soup: BeautifulSoup) -> list[dict]:
    """Objetos schema.org Event del JSON-LD (sueltos, en lista o dentro de @graph)."""
    out = []
    for tag in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(tag.string or "")
        except json.JSONDecodeError:
            continue
        pila = data if isinstance(data, list) else [data]
        for d in pila:
            if isinstance(d, dict):
                pila.extend(d.get("@graph") or [])
                if "Event" in str(d.get("@type", "")):
                    out.append(d)
    return out


def completar_detalle(evento: dict, session: requests.Session | None = None) -> dict:
    """Añade fecha y hora exactas, artista, precio y preventas desde la página del evento.

    Hay dos tipos de página: HubSpot (eventos.tuboleta.com / web.tuboleta.com, JSON-LD
    MusicEvent con hora real) y Drupal (www.tuboleta.com, JSON-LD con fecha correcta
    pero hora falsa 07:00; la hora real está en el texto "Hora: 8:00 p.m.").
    Si el detalle falla, deja el evento como estaba.
    """
    s = session or requests.Session()
    try:
        r = s.get(evento["link"], headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
    except requests.RequestException as exc:
        log.warning("Detalle no disponible (%s): %s", evento["link"], exc)
        return evento

    r.encoding = "utf-8"
    soup = BeautifulSoup(r.text, "html.parser")
    for d in _eventos_ld(soup)[:1]:
        inicio = str(d.get("startDate") or "")  # '2026-11-28T19:00:00-05:00' (hora de Colombia)
        if re.match(r"\d{4}-\d{2}-\d{2}", inicio):
            evento["fecha"] = inicio[:10]
            if d.get("@type") == "MusicEvent":  # solo HubSpot trae la hora real
                evento["hora"] = inicio[11:16] or None
        performer = d.get("performer")
        if isinstance(performer, list):
            performer = performer[0] if performer else None
        if isinstance(performer, dict) and performer.get("name"):
            evento["artista"] = performer["name"]
        offers = d.get("offers") or {}
        if isinstance(offers, dict) and offers.get("lowPrice"):
            evento["precio_desde"] = int(float(offers["lowPrice"]))

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    texto = " ".join(soup.get_text(" ").split())
    if not evento.get("hora") and (m := RE_HORA.search(texto)):
        evento["hora"] = _hora24(*m.groups())
    preventas = _preventas(texto, evento.get("fecha"))
    if preventas:
        evento["preventas"] = preventas
        evento["preventa"] = preventas[0]["inicio"]
    return evento


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    evs = obtener_eventos()
    for e in evs:
        print(f"{e['fecha'] or '¿?':10}  {e['artista'][:28]:28}  {e['ciudad'][:14]:14}  {e['lugar'][:30]}")
    print(f"\n{len(evs)} eventos")
