"""Dependency-light membership policy and Telegram status verification."""
from __future__ import annotations
from typing import Any

REQUIRED_CHANNELS = (
    ("@miogptstudio", "کانال اول — MIO GPT Studio", "https://t.me/miogptstudio"),
    ("@shady_garden", "کانال دوم — Shady Garden", "https://t.me/shady_garden"),
)
MEMBER_STATUSES = {"creator", "administrator", "member"}

async def membership_status(bot: Any, user_id: int) -> tuple[bool, list[str], bool]:
    """Returns (all_joined, missing_channel_usernames, verification_error)."""
    missing: list[str] = []
    verification_error = False
    for channel, _label, _url in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            status = getattr(member, "status", "")
            is_member = status in MEMBER_STATUSES or (status == "restricted" and bool(getattr(member, "is_member", False)))
            if not is_member:
                missing.append(channel)
        except Exception as exc:
            # Avoid importing aiogram in this module so policy tests run without app dependencies.
            if exc.__class__.__name__ in {"TelegramAPIError", "TelegramNetworkError", "TelegramBadRequest", "TelegramForbiddenError"}:
                verification_error = True
                missing.append(channel)
            else:
                verification_error = True
                missing.append(channel)
    return not missing and not verification_error, missing, verification_error
