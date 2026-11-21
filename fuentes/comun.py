"""Piezas compartidas por los módulos de fuentes."""

from __future__ import annotations

import unicodedata
from datetime import date

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


def texto(el) -> str:
    return " ".join(el.get_text(" ", strip=True).split()) if el else ""


def hora24(h: str, m: str, ampm: str) -> str:
    """('8', '00', 'p') -> '20:00'."""
    h24 = int(h) % 12 + (12 if ampm.lower() == "p" else 0)
    return f"{h24:02d}:{m}"


def fecha_sin_anio(dia: int, mes: int, hoy: date) -> date | None:
    """Fecha sin año: este año, o el siguiente si ya pasó hace más de 2 meses."""
    try:
        f = date(hoy.year, mes, dia)
        if (hoy - f).days > 60:
            f = date(hoy.year + 1, mes, dia)
        return f
    except ValueError:
        return None


def artista_de_titulo(titulo: str, ciudad: str = "", separadores=("|",)) -> str:
    """'BEÉLE | BORONDO TOUR 2026 - MEDELLÍN' -> 'BEÉLE'. Quita ' - CIUDAD' al final.

    Es una aproximación: el detalle del evento la corrige cuando trae el artista.
    """
    t = titulo.strip()
    for sep in separadores:
        if sep in t:
            t = t.split(sep, 1)[0].strip()
            break
    # 'Kase O Medellin' (ciudad Medellín) -> 'Kase O'
    c = _plano(ciudad)
    if c and _plano(t).endswith(" " + c) and len(_plano(t)) > len(c) + 1:
        t = t[: len(t) - len(ciudad)].rstrip(" -–")
    return t


def _plano(s: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(ch) != "Mn").strip()
