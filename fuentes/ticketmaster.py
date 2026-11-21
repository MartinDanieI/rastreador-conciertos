"""Fuente: Ticketmaster Colombia (https://www.ticketmaster.co).

Cómo está hecha la página (revisado el 2026-11-20):
    - Plataforma Crowder/Quentro (no la de Ticketmaster de EE. UU.). Desde 2025-2026
      absorbió a eTicket y La Tiquetera: Karol G, Carlos Vives, Maná, The Strokes…
    - /page/CONCIERTOS trae todos los conciertos en el HTML (sin JavaScript).
      Cada tarjeta: lugar, título, subtítulo con la fecha en texto libre
      ("Tour | 04, 05 y 06 de Diciembre de 2026", a veces sin año) y ciudad.
    - El detalle (/event/<slug>) tiene JSON-LD Event con lugar y municipio, sin
      fecha ni hora. Las preventas vienen en texto: "Preventa Bancaria AVAL:
      20/05/2026 10:00 A.M.".
    - robots.txt solo trae reglas para los bots de Google (no restringe a los demás).
      Los T&C (punto 3.10) prohíben bots para COMPRAR boletas, no para leer la cartelera.
    - Usa captcha (AWS WAF / Turnstile) solo en la compra.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date

import requests
from bs4 import BeautifulSoup

from .comun import HEADERS, MESES, TIMEOUT, FuenteError, artista_de_titulo, fecha_sin_anio, hora24, texto

log = logging.getLogger(__name__)

FUENTE = "ticketmaster"
BASE = "https://www.ticketmaster.co"
URL_CONCIERTOS = f"{BASE}/page/CONCIERTOS"

# "04, 05 y 06 de Diciembre de 2026" / "12 de Diciembre 2026" / "30 de Noviembre"
RE_FECHA = re.compile(
    r"\b(\d{1,2})(?:\s*(?:,|y|al|-)\s*\d{1,2})*\s+de\s+([a-záéíóú]+)(?:\s+(?:de\s+|del\s+)?(\d{4}))?",
    re.IGNORECASE)
# "Preventa Bancaria AVAL: 20/05/2026 10:00 A.M."
RE_PREVENTA = re.compile(
    r"\b(Pre-?venta[^:]{0,60}?):\s*(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2})\s*([ap])\.?\s*m",
    re.IGNORECASE)


def _fecha(texto_fecha: str, hoy: date) -> str | None:
    m = RE_FECHA.search(texto_fecha)
    if not m or m.group(2).lower()[:3] not in MESES:
        return None
    dia, mes = int(m.group(1)), MESES[m.group(2).lower()[:3]]
    if m.group(3):
        try:
            return date(int(m.group(3)), mes, dia).isoformat()
        except ValueError:
            return None
    f = fecha_sin_anio(dia, mes, hoy)
    return f.isoformat() if f else None


def obtener_eventos(session: requests.Session | None = None, hoy: date | None = None) -> list[dict]:
    """Lista de conciertos de Ticketmaster Colombia con el mismo formato que las demás fuentes."""
    s = session or requests.Session()
    hoy = hoy or date.today()
    try:
        r = s.get(URL_CONCIERTOS, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
    except requests.RequestException as exc:
        raise FuenteError(f"Ticketmaster no respondió: {exc}") from exc

    soup = BeautifulSoup(r.text, "html.parser")
    eventos: dict[str, dict] = {}
    for a in soup.select(".grid_element a[href*='event/']"):
        link = requests.compat.urljoin(URL_CONCIERTOS, a["href"])
        titulo = texto(a.select_one(".item_title"))
        if not titulo or link in eventos:
            continue
        subtitulo = texto(a.select_one(".details strong")) or texto(a.select_one(".grid-date"))
        ciudad = texto(a.select_one(".details span"))
        lugar_el = a.select_one(".grid-label")
        if lugar_el:
            for sr in lugar_el.select(".sr-only"):
                sr.decompose()
        eventos[link] = {
            "fuente": FUENTE,
            "artista": artista_de_titulo(titulo, ciudad, ("|", " - ")),
            "evento": f"{titulo} | {subtitulo}" if subtitulo and subtitulo not in titulo else titulo,
            "fecha": _fecha(subtitulo, hoy) or _fecha(titulo, hoy),
            "hora": None,
            "ciudad": ciudad,
            "lugar": texto(lugar_el),
            "link": link,
            "preventa": None,
        }

    if not eventos:
        raise FuenteError("Ticketmaster devolvió 0 eventos: probablemente cambió el diseño de la página")
    return list(eventos.values())


def completar_detalle(evento: dict, session: requests.Session | None = None) -> dict:
    """Añade municipio y preventas desde la página del evento (no trae hora)."""
    s = session or requests.Session()
    try:
        r = s.get(evento["link"], headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
    except requests.RequestException as exc:
        log.warning("Detalle no disponible (%s): %s", evento["link"], exc)
        return evento

    r.encoding = "utf-8"
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup.select('script[type="application/ld+json"]'):
        try:
            d = json.loads(tag.string or "")
        except json.JSONDecodeError:
            continue
        if isinstance(d, dict) and d.get("@type") == "Event":
            loc = d.get("location") or {}
            municipio = ((loc.get("address") or {}).get("addressLocality") or "").strip()
            if municipio:
                evento["municipio"] = municipio  # p. ej. Cota (Coliseo MedPlus) -> ciudad Bogotá
            if loc.get("name") and not evento.get("lugar"):
                evento["lugar"] = loc["name"]
            break

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    plano = " ".join(soup.get_text(" ").split())
    preventas: dict[str, dict] = {}
    for m in RE_PREVENTA.finditer(plano):
        nombre, dd, mm, aaaa, h, mi, ampm = m.groups()
        try:
            f = date(int(aaaa), int(mm), int(dd))
        except ValueError:
            continue
        inicio = f"{f.isoformat()}T{hora24(h, mi, ampm)}"
        preventas.setdefault(inicio + nombre.lower(), {"nombre": nombre.strip(), "inicio": inicio})
    if preventas:
        evento["preventas"] = sorted(preventas.values(), key=lambda p: p["inicio"])
        evento["preventa"] = evento["preventas"][0]["inicio"]
    return evento


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    evs = obtener_eventos()
    for e in evs:
        print(f"{e['fecha'] or '¿?':10}  {e['artista'][:28]:28}  {e['ciudad'][:14]:14}  {e['lugar'][:30]}")
    print(f"\n{len(evs)} eventos")
