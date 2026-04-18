"""
Rule-based replies for the demo bot.

Key difference vs Telegram: the messenger Bot API has no inline keyboards and
no "share contact" button. The user types the number as plain text; this
module recognises Russian phone formats with a regex.

Conversation state (which chats we're actively waiting on for a phone) is
kept in-memory with a TTL so a long-silent user can't reopen the chat days
later and accidentally have "привет" parsed as a phone number. For horizontal
scaling replace the dict with Redis.
"""
from __future__ import annotations

import re
import threading
import time
from typing import Optional

# conversation_id -> unix timestamp when the ask expires.
_awaiting_phone: dict[str, float] = {}
_awaiting_lock = threading.Lock()

# How long we keep a "please send a phone" prompt active. After this the user
# has to say "привет" / "номер" again to re-open the slot.
_AWAITING_TTL_SECONDS = 15 * 60


_GREETINGS = frozenset(
    {
        "привет",
        "приветствую",
        "здравствуй",
        "здравствуйте",
        "hi",
        "hello",
        "hey",
        "хай",
        "ку",
        "йо",
        "салют",
    }
)

_GREETING_COMPOUND_PREFIXES = (
    "добрыйдень",
    "добрыйвечер",
    "доброеутро",
    "добройночи",
    "доброгодня",
    "доброговечера",
)


def _collapse_ws(s: str) -> str:
    return "".join(s.lower().split())


def _is_greeting(tn: str) -> bool:
    if not tn:
        return False
    collapsed = _collapse_ws(tn)
    if any(collapsed.startswith(p) for p in _GREETING_COMPOUND_PREFIXES):
        return True
    words = re.findall(r"[a-zа-яё]+", tn.lower())
    if not words:
        return False
    return words[0] in _GREETINGS


def _is_how_are_you(text_norm: str) -> bool:
    phrases = (
        "какдела",
        "какты",
        "какпоживаешь",
        "чтонового",
        "howareyou",
        "какнастроение",
        "какжизнь",
    )
    collapsed = _collapse_ws(text_norm)
    return any(p in collapsed for p in phrases)


def _mentions_phone_topic(text_norm: str) -> bool:
    collapsed = _collapse_ws(text_norm)
    return any(
        kw in collapsed
        for kw in ("телефон", "номер", "позвонить", "перезвонить", "контакт")
    )


def extract_phone(raw: str) -> Optional[str]:
    """Return normalized +7XXXXXXXXXX or None."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    if len(digits) == 11 and digits.startswith("7"):
        return "+" + digits
    if len(digits) == 10:
        return "+7" + digits
    return None


def _set_awaiting(cid: str) -> None:
    with _awaiting_lock:
        _awaiting_phone[cid] = time.time() + _AWAITING_TTL_SECONDS


def _clear_awaiting(cid: str) -> None:
    with _awaiting_lock:
        _awaiting_phone.pop(cid, None)


def _is_awaiting(cid: str) -> bool:
    """True iff we asked for a phone recently and the TTL hasn't expired."""
    now = time.time()
    with _awaiting_lock:
        exp = _awaiting_phone.get(cid)
        if exp is None:
            return False
        if exp < now:
            _awaiting_phone.pop(cid, None)
            return False
        return True


def build_reply(text: str, conversation_id: str) -> str:
    t = (text or "").strip()
    tn = t.lower()
    cid = str(conversation_id)

    # --- Follow-up: we're waiting on a phone number ---
    if _is_awaiting(cid):
        phone = extract_phone(t)
        if phone:
            _clear_awaiting(cid)
            return (
                f"Спасибо! Номер принят: {phone}\n"
                "Если нужно что-то ещё — напишите «привет»."
            )
        if t:
            return (
                "Похоже, это не номер. Пришлите цифрами, например:\n"
                "+79001234567 или 89001234567"
            )
        _clear_awaiting(cid)
        return "Ок. Если передумаете — снова напишите «привет»."

    # --- Standalone phone line (user dropped a number out of the blue) ---
    if t and len(t) <= 22:
        phone = extract_phone(t)
        if phone:
            return f"Спасибо! Номер принят: {phone}"

    if _is_how_are_you(tn):
        return (
            "У меня всё хорошо, я на связи 🙂\n"
            "А у вас как? Могу записать телефон — напишите «номер» или «привет»."
        )

    if _is_greeting(tn):
        _set_awaiting(cid)
        return (
            "Привет! Рад вас видеть.\n\n"
            "Могу попросить номер для связи.\n"
            "Пришлите номер обычным сообщением "
            "(например +79001234567) — я его распознаю."
        )

    if _mentions_phone_topic(tn):
        _set_awaiting(cid)
        return (
            "Хорошо. Пришлите номер одним сообщением: +7… или 8… (10–11 цифр).\n"
            "Отдельной кнопки контакта в приложении пока нет."
        )

    if not t:
        return "Пустое сообщение 🙂 Напишите «привет», «как дела» или номер телефона."

    return (
        f"Вы написали: «{t[:200]}{'…' if len(t) > 200 else ''}».\n\n"
        "Попробуйте: «привет», «как дела», «номер» или пришлите телефон цифрами."
    )
