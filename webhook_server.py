"""
HTTP server for Railway: receives messenger bot webhooks and replies via Bot API.

Env vars:
    MESSENGER_API_URL   — bot-gateway base URL (no trailing slash, no /api/v1)
    BOT_TOKEN           — bot token; also used as HMAC secret for signature verification
    ECHO_REPLY          — "1" (default) to reply; "0" to only log incoming webhooks
    VERIFY_SIGNATURE    — "1" (default) to require X-Bot-Signature; "0" to skip (dev only)
    SIGNATURE_MAX_SKEW  — seconds, default 300 (reject signatures older than this)

The backend signs every webhook POST with:
    X-Bot-Signature: t=<unix_ts>,v1=<hex(HMAC_SHA256(bot.token, "<t>.<raw_body>"))>
    X-Bot-Id:        <UUID>

See messenger/docs/BOT_INTEGRATION_GUIDE.md §4.1.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time

import httpx
from fastapi import FastAPI, HTTPException, Request

from reply_logic import build_reply

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("webhook_server")

app = FastAPI(title="Messenger bot webhook tester")


def _env(key: str, default: str = "") -> str:
    return (os.environ.get(key) or default).strip()


def _api_base() -> str:
    base = _env("MESSENGER_API_URL").rstrip("/")
    if not base:
        raise RuntimeError("MESSENGER_API_URL is required")
    return base


def _bot_token() -> str:
    t = _env("BOT_TOKEN")
    if not t:
        raise RuntimeError("BOT_TOKEN is required")
    return t


def _bool(key: str, default: str = "1") -> bool:
    return _env(key, default).lower() in ("1", "true", "yes", "on")


def _verify_signature(raw_body: bytes, header: str, secret: str, max_skew: int) -> None:
    """
    Verify header "t=<unix>,v1=<hex>" against HMAC_SHA256(secret, "<t>.<raw_body>").
    Raises HTTPException(401) on mismatch. Mirrors Stripe's signature scheme.
    """
    if not header:
        raise HTTPException(status_code=401, detail="missing X-Bot-Signature")

    parts = {}
    for chunk in header.split(","):
        chunk = chunk.strip()
        if "=" in chunk:
            k, _, v = chunk.partition("=")
            parts[k.strip()] = v.strip()

    ts = parts.get("t")
    v1 = parts.get("v1")
    if not ts or not v1:
        raise HTTPException(status_code=401, detail="malformed X-Bot-Signature")

    try:
        ts_int = int(ts)
    except ValueError as e:
        raise HTTPException(status_code=401, detail="bad timestamp") from e

    now = int(time.time())
    if abs(now - ts_int) > max_skew:
        # Replay defence: any captured signature older than max_skew is rejected
        # even if the digest is otherwise valid.
        raise HTTPException(status_code=401, detail="signature too old")

    mac = hmac.new(secret.encode("utf-8"), digestmod=hashlib.sha256)
    mac.update(ts.encode("utf-8"))
    mac.update(b".")
    mac.update(raw_body)
    expected = mac.hexdigest()

    if not hmac.compare_digest(expected, v1):
        raise HTTPException(status_code=401, detail="bad signature")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/webhook")
async def messenger_webhook(request: Request):
    # Read raw bytes FIRST — signature is computed over the exact body the
    # backend sent, so any re-serialisation would break the HMAC check.
    raw_body = await request.body()

    if _bool("VERIFY_SIGNATURE"):
        _verify_signature(
            raw_body=raw_body,
            header=request.headers.get("x-bot-signature", ""),
            secret=_bot_token(),
            max_skew=int(_env("SIGNATURE_MAX_SKEW", "300")),
        )

    try:
        body = await request.json()
    except Exception:
        log.warning("Webhook body is not JSON: %r", raw_body[:200])
        return {"ok": False, "error": "invalid json"}

    log.info("Webhook payload: %s", body)

    if body.get("update_type") != "message":
        return {"ok": True, "ignored": "not a message update"}

    msg = body.get("message") or {}
    conv_id = msg.get("conversationId")
    if not conv_id:
        log.warning("No conversationId in message")
        return {"ok": False, "error": "missing conversationId"}

    # Ignore messages sent by the bot itself — the backend already skips the
    # sender when dispatching, but an echo loop through another bot account in
    # the same conversation would still trip us up otherwise.
    sender_id = str(msg.get("senderId") or "")
    bot_id_header = request.headers.get("x-bot-id", "")
    if sender_id and bot_id_header and sender_id == bot_id_header:
        return {"ok": True, "ignored": "own message"}

    if not _bool("ECHO_REPLY"):
        return {"ok": True, "echo": "disabled"}

    text_in = (msg.get("text") or "").strip()
    out_text = build_reply(text_in, str(conv_id))

    if not out_text:
        return {"ok": True, "skipped": "empty reply"}

    send_status = await _send_message(str(conv_id), out_text)
    return {"ok": send_status < 400, "sendStatus": send_status}


async def _send_message(conversation_id: str, text: str) -> int:
    """
    Send a bot message with one retry on HTTP 429 (rate limit). Returns the
    final HTTP status so the webhook handler can surface it in the response.
    """
    url = f"{_api_base()}/api/v1/bot/sendMessage"
    headers = {
        "Authorization": f"Bot {_bot_token()}",
        "Content-Type": "application/json",
    }
    payload = {"conversationId": conversation_id, "text": text}

    async with httpx.AsyncClient(timeout=30.0) as client:
        for attempt in (0, 1):
            r = await client.post(url, json=payload, headers=headers)
            if r.status_code == 429 and attempt == 0:
                # Backend enforces 5 msg/s / 60 msg/min per bot. One retry is
                # enough for the 1-second window; if we still get 429 after,
                # we drop the reply rather than queue indefinitely.
                log.warning("sendMessage got 429, backing off for 1.2s then retrying")
                await _asleep(1.2)
                continue
            if r.is_success:
                log.info("sendMessage ok: %s", r.status_code)
            else:
                log.error("sendMessage failed: %s %s", r.status_code, r.text[:300])
            return r.status_code
    return 429


async def _asleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)
