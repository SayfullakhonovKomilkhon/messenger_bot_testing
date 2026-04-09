"""
HTTP server for Railway: receives messenger bot webhooks and optionally echoes back.

Set env: MESSENGER_API_URL, BOT_TOKEN, ECHO_REPLY=1 (default on)
"""
from __future__ import annotations

import logging
import os

import httpx
from fastapi import FastAPI, Request

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("webhook_server")

app = FastAPI(title="Messenger bot webhook tester")


def _api_base() -> str:
    base = (os.environ.get("MESSENGER_API_URL") or "").rstrip("/")
    if not base:
        raise RuntimeError("MESSENGER_API_URL is required")
    return base


def _bot_token() -> str:
    t = (os.environ.get("BOT_TOKEN") or "").strip()
    if not t:
        raise RuntimeError("BOT_TOKEN is required")
    return t


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/webhook")
async def messenger_webhook(request: Request):
    body = await request.json()
    log.info("Webhook payload: %s", body)

    if body.get("update_type") != "message":
        return {"ok": True, "ignored": "not a message update"}

    msg = body.get("message") or {}
    conv_id = msg.get("conversationId")
    if not conv_id:
        log.warning("No conversationId in message")
        return {"ok": False, "error": "missing conversationId"}

    if os.environ.get("ECHO_REPLY", "1").strip() not in ("1", "true", "yes"):
        return {"ok": True, "echo": "disabled"}

    text_in = (msg.get("text") or "").strip()
    preview = (text_in[:180] + "…") if len(text_in) > 180 else text_in
    out_text = f"[bot-test] Получено: {preview}" if preview else "[bot-test] (пустое сообщение)"

    url = f"{_api_base()}/api/v1/bot/sendMessage"
    headers = {
        "Authorization": f"Bot {_bot_token()}",
        "Content-Type": "application/json",
    }
    payload = {"conversationId": str(conv_id), "text": out_text}

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(url, json=payload, headers=headers)
        if r.is_success:
            log.info("sendMessage ok: %s", r.status_code)
            return {"ok": True, "sendStatus": r.status_code}
        log.error("sendMessage failed: %s %s", r.status_code, r.text)
        return {"ok": False, "status": r.status_code, "body": r.text[:500]}
