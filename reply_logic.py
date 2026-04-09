"""
Rule-based replies for demo bot. Messenger Bot API has no inline keyboards / contact button (unlike Telegram).
"""
from __future__ import annotations

import re
from typing import Optional

# Conversations where we asked for a phone and wait for the next message
_awaiting_phone: set[str] = set()

_GREETINGS = frozenset(
    {
        "привет",
        "здравствуй",
        "здравствуйте",
        "hi",
        "hello",
        "hey",
        "добрыйдень",
        "добрыйвечер",
        "доброеутро",
        "хай",
        "ку",
    }
)


def _collapse_ws(s: str) -> str:
    return "".join(s.lower().split())


def _is_greeting(tn: str) -> bool:
    if not tn:
        return False
    collapsed = _collapse_ws(tn)
    for prefix in ("добрыйдень", "добрыйвечер", "доброеутро", "добройночи"):
        if collapsed.startswith(prefix):
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
    )
    collapsed = _collapse_ws(text_norm)
    return any(p in collapsed for p in phrases)


def _mentions_phone_topic(text_norm: str) -> bool:
    collapsed = _collapse_ws(text_norm)
    return "телефон" in collapsed or "номер" in collapsed or "позвонить" in collapsed


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


def build_reply(text: str, conversation_id: str) -> str:
    t = (text or "").strip()
    tn = t.lower()

    cid = str(conversation_id)

    if cid in _awaiting_phone:
        phone = extract_phone(t)
        if phone:
            _awaiting_phone.discard(cid)
            return (
                f"Спасибо! Номер принят: {phone}\n"
                "Если нужно что-то ещё — напишите «привет»."
            )
        if t:
            return (
                "Похоже, это не номер. Пришлите цифрами, например:\n"
                "+79001234567 или 89001234567"
            )
        _awaiting_phone.discard(cid)
        return "Ок. Если передумаете — снова напишите «привет»."

    # Standalone phone line
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
        _awaiting_phone.add(cid)
        return (
            "Привет! Рад вас видеть.\n\n"
            "Могу попросить номер для связи.\n"
            "⚠️ В этом мессенджере нет кнопки «Поделиться контактом», как в Telegram — "
            "бот получает только текст и файлы. Пришлите номер обычным сообщением "
            "(например +79001234567) — я его распознаю."
        )

    if _mentions_phone_topic(tn):
        _awaiting_phone.add(cid)
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
