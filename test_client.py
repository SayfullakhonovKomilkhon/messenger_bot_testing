#!/usr/bin/env python3
"""
CLI: calls every Bot API endpoint and optionally registers webhook.

Usage:
  cp .env.example .env   # fill BOT_TOKEN and MESSENGER_API_URL
  pip install -r requirements.txt
  python test_client.py

Env:
  MESSENGER_API_URL, BOT_TOKEN (required)
  CONVERSATION_ID — for getMessages + sendMessage
  TARGET_USER_ID — for startConversation
  WEBHOOK_PUBLIC_URL — for setWebhook (your Railway URL + /webhook)
"""
from __future__ import annotations

import json
import os
import sys

import httpx


def load_dotenv() -> None:
    path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v


def base_url() -> str:
    u = (os.environ.get("MESSENGER_API_URL") or "").rstrip("/")
    if not u:
        print("Set MESSENGER_API_URL", file=sys.stderr)
        sys.exit(1)
    return u


def token() -> str:
    t = (os.environ.get("BOT_TOKEN") or "").strip()
    if not t:
        print("Set BOT_TOKEN", file=sys.stderr)
        sys.exit(1)
    return t


def headers() -> dict[str, str]:
    return {
        "Authorization": f"Bot {token()}",
        "Content-Type": "application/json",
    }


def main() -> None:
    load_dotenv()
    api = base_url()
    h = headers()
    results: list[tuple[str, bool, str]] = []

    with httpx.Client(timeout=30.0) as client:

        def ok(name: str, resp: httpx.Response) -> None:
            good = resp.is_success
            body = resp.text[:800] if resp.text else ""
            results.append((name, good, f"{resp.status_code} {body}"))

        # 1) me
        r = client.get(f"{api}/api/v1/bot/me", headers=h)
        ok("GET /api/v1/bot/me", r)

        # 2) getConversations
        r = client.get(f"{api}/api/v1/bot/getConversations", headers=h)
        ok("GET /api/v1/bot/getConversations", r)
        conv_id = (os.environ.get("CONVERSATION_ID") or "").strip()
        if not conv_id and r.is_success:
            try:
                data = r.json()
                if isinstance(data, list) and data:
                    conv_id = str(data[0].get("id") or data[0].get("conversationId") or "")
            except (json.JSONDecodeError, TypeError):
                pass

        # 3) getMessages
        if conv_id:
            r = client.get(
                f"{api}/api/v1/bot/getMessages",
                headers=h,
                params={"conversationId": conv_id, "limit": 10},
            )
            ok("GET /api/v1/bot/getMessages", r)
        else:
            results.append(
                (
                    "GET /api/v1/bot/getMessages",
                    False,
                    "skip (set CONVERSATION_ID or have at least one conversation)",
                )
            )

        # 4) startConversation
        target = (os.environ.get("TARGET_USER_ID") or "").strip()
        if target:
            r = client.post(
                f"{api}/api/v1/bot/startConversation",
                headers=h,
                params={"userId": target},
            )
            ok("POST /api/v1/bot/startConversation", r)
            if r.is_success:
                try:
                    j = r.json()
                    conv_id = str(j.get("id") or conv_id)
                except (json.JSONDecodeError, TypeError):
                    pass
        else:
            results.append(
                (
                    "POST /api/v1/bot/startConversation",
                    False,
                    "skip (set TARGET_USER_ID)",
                )
            )

        # 5) setWebhook
        wh = (os.environ.get("WEBHOOK_PUBLIC_URL") or "").strip()
        if wh:
            r = client.post(
                f"{api}/api/v1/bot/setWebhook",
                headers=h,
                json={"url": wh},
            )
            ok("POST /api/v1/bot/setWebhook", r)
        else:
            results.append(
                (
                    "POST /api/v1/bot/setWebhook",
                    False,
                    "skip (set WEBHOOK_PUBLIC_URL e.g. https://xxx.up.railway.app/webhook)",
                )
            )

        # 6) sendMessage
        if conv_id and os.environ.get("TEST_SEND_MESSAGE", "").strip() in ("1", "true", "yes"):
            r = client.post(
                f"{api}/api/v1/bot/sendMessage",
                headers=h,
                json={
                    "conversationId": conv_id,
                    "text": "[bot-test] Проверка sendMessage из test_client.py",
                },
            )
            ok("POST /api/v1/bot/sendMessage", r)
        else:
            results.append(
                (
                    "POST /api/v1/bot/sendMessage",
                    False,
                    "skip (set CONVERSATION_ID and TEST_SEND_MESSAGE=1 to send a test line)",
                )
            )

    print("\n=== Bot API test results ===\n")
    for name, good, detail in results:
        mark = "OK " if good else "FAIL"
        print(f"[{mark}] {name}")
        print(f"       {detail}\n")


if __name__ == "__main__":
    main()
