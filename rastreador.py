"""Rastreador de conciertos en Colombia: revisa las boleteras y avisa de los eventos nuevos.

Ejemplos:
    python rastreador.py                    # revisa, avisa por Telegram y guarda eventos.json
    python rastreador.py --dry-run          # revisa y muestra lo nuevo, sin avisar ni guardar
    python rastreador.py --todos            # además lista todos los eventos actuales
    python rastreador.py --sin-detalle      # no abre la página de cada evento nuevo
    python rastreador.py --test-telegram    # manda un mensaje de prueba y sale
    python rastreador.py --telegram-chat-id # muestra tu TELEGRAM_CHAT_ID

Un evento es nuevo si su id (fuente + link) no estaba en eventos.json.
La primera ejecución solo guarda la línea base (no avisa de nada).
Si una fuente falla o devuelve 0 eventos, avisa una vez ("dejó de responder")
y otra cuando se recupera, sin repetir el aviso en cada revisión.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import notificador
from fuentes import FUENTES
from normalizar import normalizar

ROOT = Path(__file__).resolve().parent
PAUSA_DETALLE = 1.0  # segundos entre páginas de detalle, para no cargar la boletera
COLOMBIA = timezone(timedelta(hours=-5), "COT")  # Colombia no tiene horario de verano
DETALLE = ("fecha", "hora", "artista", "artista_norm", "precio_desde", "preventa", "preventas", "detectado")

log = logging.getLogger("rastreador")


def load_dotenv(path: Path) -> None:
    """Lector mínimo de .env (KEY=VALUE). No pisa variables ya definidas."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def evento_id(e: dict) -> str:
    return f"{e['fuente']}:{e['link']}"


def cargar(archivo: Path) -> dict | None:
    if not archivo.exists():
        return None
    return json.loads(archivo.read_text(encoding="utf-8"))


def guardar(archivo: Path, conocidos: dict[str, dict], fallas: dict[str, str], latido: str | None) -> None:
    # Sin marcas de "última revisión": el archivo solo cambia cuando hay algo nuevo
    # (o una vez al día por el latido), así GitHub Actions no hace commits vacíos.
    archivo.write_text(json.dumps({
        "latido": latido,
        "fallas": fallas,
        "eventos": dict(sorted(conocidos.items())),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _cuando(e: dict) -> str:
    return " ".join(x for x in (e.get("fecha") or "sin fecha", e.get("hora")) if x)


def formato_consola(e: dict) -> str:
    precio = f"  desde ${e['precio_desde']:,}".replace(",", ".") if e.get("precio_desde") else ""
    lugar = f"{e['lugar']}, {e['ciudad']}" + (f" ({e['municipio']})" if e.get("municipio") else "")
    preventa = f"\n   🎟️ Preventa: {e['preventa'].replace('T', ' ')}" if e.get("preventa") else ""
    return (f"🎤 {e['artista']} — {e['evento']}\n"
            f"   📅 {_cuando(e)}  📍 {lugar}{precio}{preventa}\n"
            f"   🔗 {e['link']}")


def formato_telegram(e: dict) -> str:
    lineas = [f"🎤 <b>{escape(e['artista'])}</b>", escape(e["evento"]),
              f"📅 {_cuando(e)}",
              f"📍 {escape(e['lugar'])}, {escape(e['ciudad'])}"
              + (f" ({escape(e['municipio'])})" if e.get("municipio") else "")]
    if e.get("precio_desde"):
        lineas.append(f"💵 Desde ${e['precio_desde']:,}".replace(",", "."))
    for p in e.get("preventas") or []:
        lineas.append(f"🎟️ {escape(p['nombre'])}: {p['inicio'].replace('T', ' ')}")
    lineas.append(f'<a href="{escape(e["link"])}">Ver en {escape(e["fuente"].capitalize())}</a>')
    return "\n".join(lineas)


HORA_LATIDO = int(os.getenv("HEARTBEAT_HOUR", "8"))  # hora de Colombia del mensaje diario


def mensaje_latido(conocidos: dict[str, dict], actuales: list[dict], nuevos: list[dict],
                   fallas: dict[str, str]) -> str:
    """'Sigo activo' con el resumen de las últimas 24 horas."""
    hace_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(timespec="seconds")
    ids_nuevos = {evento_id(e) for e in nuevos}
    recientes = sum(1 for eid, e in conocidos.items()
                    if eid not in ids_nuevos and (e.get("detectado") or "") >= hace_24h) + len(nuevos)
    estado = ("⚠️ Fuentes caídas: " + ", ".join(escape(f) for f in fallas)) if fallas \
        else f"✅ Fuentes funcionando: {', '.join(escape(f) for f in FUENTES)}"
    return (f"🤖 <b>El rastreador sigue activo</b>\n"
            f"📋 {len(actuales)} conciertos en las boleteras\n"
            f"🆕 {recientes} nuevo(s) en las últimas 24 horas\n"
            f"{estado}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Rastreador de conciertos en Colombia")
    parser.add_argument("--dry-run", action="store_true", help="no avisa ni guarda eventos.json")
    parser.add_argument("--todos", action="store_true", help="lista también todos los eventos actuales")
    parser.add_argument("--sin-detalle", action="store_true", help="no abre el detalle de los eventos nuevos")
    parser.add_argument("--latido", action="store_true", help="manda el mensaje diario de 'sigo activo' ya")
    parser.add_argument("--test-telegram", action="store_true", help="manda un mensaje de prueba y sale")
    parser.add_argument("--telegram-chat-id", action="store_true", help="muestra tu TELEGRAM_CHAT_ID")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    for stream in (sys.stdout, sys.stderr):  # emojis en la consola de Windows
        if stream.encoding and stream.encoding.lower() != "utf-8":
            stream.reconfigure(encoding="utf-8")
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    archivo = Path(os.getenv("EVENTOS_FILE", ROOT / "eventos.json"))
    dry_run = args.dry_run or os.getenv("DRY_RUN", "").lower() in ("1", "true", "si", "sí")

    if args.telegram_chat_id or args.test_telegram:
        if not notificador.configurado():
            print("Falta TELEGRAM_BOT_TOKEN en .env")
            return 2
        try:
            if args.test_telegram:
                notificador.enviar(["✅ Prueba del rastreador de conciertos: los avisos llegan."])
                print("Mensaje de prueba enviado.")
                return 0
            chats = notificador.chats_recientes()
        except notificador.NotificadorError as exc:
            print(f"Error de Telegram: {exc}")
            return 1
        if not chats:
            print("Ningún chat todavía: escríbele cualquier cosa a tu bot en Telegram y repite.")
            return 1
        for c in chats:
            print(f"TELEGRAM_CHAT_ID={c['chat_id']}   ({c['nombre']} @{c['usuario']}: {c['ultimo_mensaje']!r})")
        return 0

    previo = cargar(archivo)
    primera_vez = previo is None
    conocidos: dict[str, dict] = (previo or {}).get("eventos", {})
    fallas_previas: dict[str, str] = (previo or {}).get("fallas", {})
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=Retry(
        total=2, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504))))
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # 1. Revisar cada fuente (una rota no tumba las demás)
    actuales: list[dict] = []
    fallas: dict[str, str] = {}
    errores: dict[str, str] = {}
    for nombre, modulo in FUENTES.items():
        try:
            evs = modulo.obtener_eventos(session)
            log.info("%s: %d eventos", nombre, len(evs))
            actuales.extend(evs)
        except Exception as exc:
            log.error("La fuente %s falló: %s", nombre, exc)
            fallas[nombre] = fallas_previas.get(nombre, ahora)
            errores[nombre] = str(exc)

    # 2. Detectar los nuevos y completar su detalle (fecha exacta, preventas)
    nuevos = [e for e in actuales if evento_id(e) not in conocidos]
    if not primera_vez and not args.sin_detalle:
        for e in nuevos:
            completar = getattr(FUENTES[e["fuente"]], "completar_detalle", None)
            if completar:
                completar(e, session)
                time.sleep(PAUSA_DETALLE)
    for e in actuales:
        normalizar(e)

    # 3. Armar los avisos
    bloques: list[str] = []
    if nuevos and not primera_vez:
        nuevos.sort(key=lambda e: e.get("fecha") or "9999")
        bloques.append(f"🆕 <b>{len(nuevos)} concierto(s) nuevo(s)</b>")
        bloques += [formato_telegram(e) for e in nuevos]
    for nombre in fallas.keys() - fallas_previas.keys():
        bloques.append(f"⚠️ La fuente <b>{escape(nombre)}</b> dejó de responder:\n{escape(errores[nombre][:300])}")
    for nombre in fallas_previas.keys() - fallas.keys():
        if nombre in FUENTES:
            bloques.append(f"✅ La fuente <b>{escape(nombre)}</b> volvió a funcionar.")

    # Latido diario ("sigo activo") en la primera revisión desde las 8 a. m. de Colombia.
    # Si un día no llega, el bot se cayó.
    hoy_co = datetime.now(COLOMBIA)
    latido = (previo or {}).get("latido")
    if args.latido or (hoy_co.hour >= HORA_LATIDO and latido != hoy_co.date().isoformat()):
        latido = hoy_co.date().isoformat()
        bloques.append(mensaje_latido(conocidos, actuales, nuevos if not primera_vez else [], fallas))

    # 4. Mostrar en consola
    if args.todos:
        for e in sorted(actuales, key=lambda e: e.get("fecha") or "9999"):
            c = conocidos.get(evento_id(e), {})
            print(formato_consola({**e, **{k: c[k] for k in DETALLE if c.get(k)}}) + "\n")
    if primera_vez:
        print(f"Primera ejecución: {len(actuales)} eventos guardados como línea base. "
              "Desde la próxima se avisará solo de los nuevos.")
    elif nuevos:
        print(f"🆕 {len(nuevos)} evento(s) nuevo(s):\n")
        for e in nuevos:
            print(formato_consola(e) + "\n")
    else:
        print(f"Sin eventos nuevos ({len(actuales)} revisados).")
    if fallas:
        print(f"⚠️ Fuentes que fallaron: {', '.join(fallas)}")

    if dry_run:
        return 1 if fallas else 0

    # 5. Avisar. Si Telegram falla no se guarda, para reintentar en la próxima revisión.
    if bloques:
        if notificador.configurado():
            try:
                notificador.enviar(bloques)
                log.info("Aviso enviado por Telegram.")
            except notificador.NotificadorError as exc:
                log.error("%s. No se guarda el estado para reintentar.", exc)
                return 1
        else:
            log.info("Telegram sin configurar: los avisos solo se muestran aquí.")

    # 6. Guardar
    for e in actuales:
        eid = evento_id(e)
        if eid in conocidos:  # conserva lo que vino del detalle y cuándo se detectó
            conocidos[eid] = {**e, **{k: v for k, v in conocidos[eid].items() if k in DETALLE and v}}
        else:
            conocidos[eid] = {**e, "detectado": ahora}
    guardar(archivo, conocidos, fallas, latido)
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
