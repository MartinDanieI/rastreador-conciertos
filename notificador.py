"""Avisos por Telegram (Bot API oficial, gratis). Igual que en el bot del mercado.

Configuración (.env en local, Secrets en GitHub Actions):
    TELEGRAM_BOT_TOKEN  token que da @BotFather (/newbot)
    TELEGRAM_CHAT_ID    tu chat_id; varios separados por coma.
                        `python rastreador.py --telegram-chat-id` lo muestra
                        después de escribirle cualquier cosa al bot.

Sin TELEGRAM_BOT_TOKEN los avisos solo se imprimen en consola.
Los mensajes van en HTML de Telegram (los nombres con _ o * no rompen el formato).
"""

from __future__ import annotations

import logging
import os
import time

import requests

log = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/{method}"
LIMITE = 4096


class NotificadorError(RuntimeError):
    pass


def configurado() -> bool:
    return bool(os.getenv("TELEGRAM_BOT_TOKEN"))


def _llamar(method: str, payload: dict | None = None, intentos: int = 4) -> dict:
    url = API.format(token=os.environ["TELEGRAM_BOT_TOKEN"], method=method)
    for i in range(1, intentos + 1):
        try:
            resp = requests.post(url, json=payload or {}, timeout=20)
            break
        except requests.ConnectionError as exc:
            if i == intentos:  # sin el token en el mensaje de error
                raise NotificadorError(f"Telegram sin conexión: {type(exc).__name__}") from None
            time.sleep(2 * i)
    try:
        body = resp.json()
    except ValueError:
        body = {"ok": False, "description": resp.text[:300]}
    if not body.get("ok"):
        raise NotificadorError(f"Telegram HTTP {resp.status_code}: {body.get('description')}")
    return body


def _partir(bloques: list[str]) -> list[str]:
    """Junta bloques en mensajes de menos de 4096 caracteres sin cortar un bloque."""
    mensajes, actual = [], ""
    for b in bloques:
        if actual and len(actual) + len(b) + 2 > LIMITE:
            mensajes.append(actual)
            actual = ""
        actual = f"{actual}\n\n{b}" if actual else b[:LIMITE]
    return mensajes + ([actual] if actual else [])


def enviar(bloques: list[str]) -> None:
    """Envía los bloques (HTML) a todos los TELEGRAM_CHAT_ID. Basta con que llegue a uno."""
    if not configurado():
        return
    chats = [c.strip() for c in os.getenv("TELEGRAM_CHAT_ID", "").split(",") if c.strip()]
    if not chats:
        raise NotificadorError("Falta TELEGRAM_CHAT_ID")
    enviados = 0
    for chat in chats:
        try:
            for texto in _partir(bloques):
                _llamar("sendMessage", {"chat_id": chat, "text": texto, "parse_mode": "HTML",
                                        "disable_web_page_preview": True})
                time.sleep(0.5)  # límite de Telegram: ~1 mensaje/segundo por chat
            enviados += 1
        except NotificadorError as exc:
            log.error("Telegram: no se pudo enviar al chat …%s: %s", chat[-3:], exc)
    if not enviados:
        raise NotificadorError("Telegram: ningún chat recibió el aviso")


def chats_recientes() -> list[dict]:
    """Chats que le escribieron al bot (para descubrir el chat_id)."""
    chats: dict[int, dict] = {}
    for u in _llamar("getUpdates").get("result", []):
        msg = u.get("message") or u.get("edited_message") or {}
        chat = msg.get("chat")
        if chat:
            chats[chat["id"]] = {"chat_id": chat["id"], "nombre": chat.get("first_name") or chat.get("title") or "",
                                 "usuario": chat.get("username", ""), "ultimo_mensaje": msg.get("text", "")}
    return list(chats.values())
