"""Normalización común a todas las fuentes.

- artista_norm: clave para comparar nombres ("Beéle" = "BEELE" = "beele").
- ciudad: nombre estándar. Los municipios del área metropolitana cuentan como
  la ciudad principal (un concierto en Sabaneta es "Medellín" para quien vive
  allá); el municipio real queda en `municipio`.
"""

from __future__ import annotations

import re
import unicodedata


def sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def clave(texto: str) -> str:
    """'  BEÉLE ' -> 'beele'; 'Karol G.' -> 'karol g'."""
    t = sin_tildes(texto).lower().replace("&", " y ")
    t = re.sub(r"[^a-z0-9ñ]+", " ", t)
    return " ".join(t.split())


# clave del municipio -> ciudad estándar
CIUDADES = {
    "bogota": "Bogotá", "bogota d c": "Bogotá", "bogota dc": "Bogotá",
    "chia": "Bogotá", "cota": "Bogotá", "soacha": "Bogotá", "funza": "Bogotá",
    "mosquera": "Bogotá", "cajica": "Bogotá", "la calera": "Bogotá", "tocancipa": "Bogotá",
    "medellin": "Medellín", "sabaneta": "Medellín", "envigado": "Medellín",
    "itagui": "Medellín", "bello": "Medellín", "el poblado": "Medellín", "rionegro": "Medellín", "la estrella": "Medellín",
    "cali": "Cali", "santiago de cali": "Cali", "jamundi": "Cali", "palmira": "Cali", "yumbo": "Cali",
    "barranquilla": "Barranquilla", "puerto colombia": "Barranquilla", "soledad": "Barranquilla",
    "cartagena": "Cartagena", "cartagena de indias": "Cartagena",
    "bucaramanga": "Bucaramanga", "floridablanca": "Bucaramanga", "giron": "Bucaramanga",
    "piedecuesta": "Bucaramanga",
    "pereira": "Pereira", "dosquebradas": "Pereira",
    "manizales": "Manizales", "armenia": "Armenia", "pasto": "Pasto", "tunja": "Tunja",
    "neiva": "Neiva", "ibague": "Ibagué", "villavicencio": "Villavicencio",
    "santa marta": "Santa Marta", "cucuta": "Cúcuta", "monteria": "Montería",
    "valledupar": "Valledupar", "popayan": "Popayán", "sincelejo": "Sincelejo",
}


def ciudad_estandar(ciudad: str) -> str:
    c = clave(ciudad)
    return CIUDADES.get(c, ciudad.strip().title() if ciudad.isupper() else ciudad.strip())


def normalizar(e: dict) -> dict:
    """Completa artista_norm, ciudad estándar y municipio. Modifica y devuelve el evento."""
    e["artista"] = " ".join(e.get("artista", "").split())
    e["artista_norm"] = clave(e["artista"])
    original = (e.get("municipio") or e.get("ciudad") or "").strip()
    e["ciudad"] = ciudad_estandar(original)
    e["municipio"] = original if clave(original) != clave(e["ciudad"]) else None
    return e
