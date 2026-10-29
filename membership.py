"""Required-channel membership gate for Telegram bot updates and Mini App APIs."""
from __future__ import annotations
from aiogram import BaseMiddleware
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramAPIError
from typing import Any, Awaitable, Callable

from membership_core import REQUIRED_CHANNELS, MEMBER_STATUSES, membership_status


def join_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 عضویت در کانال اول", url=REQUIRED_CHANNELS[0][2])],
        [InlineKeyboardButton(text="🌿 عضویت در کانال دوم", url=REQUIRED_CHANNELS[1][2])],
        [InlineKeyboardButton(text="✅ بررسی عضویت", callback_data="membership:check")],
    ])


class RequiredMembershipMiddleware(BaseMiddleware):
    async def __call__(self, handler: Callable[[Any, dict[str, Any]], Awaitable[Any]], event: Any, data: dict[str, Any]) -> Any:
        user = getattr(event, "from_user", None)
        if user is None:
            return await handler(event, data)
        # Always allow the explicit check callback through so the user can retry.
        if getattr(event, "data", None) == "membership:check":
            return await handler(event, data)
        bot = data.get("bot")
        if bot is None:
            return await handler(event, data)
        joined, _missing, error = await membership_status(bot, user.id)
        if joined:
            return await handler(event, data)
        text = (
            "⚠️ فعلاً امکان بررسی عضویت در کانال‌ها وجود ندارد.\n"
            "لطفاً کمی بعد دوباره «بررسی عضویت» را بزن. اگر مشکل ادامه داشت، مدیر ربات باید دسترسی لازم را به ربات بدهد."
            if error else
            "👑 برای استفاده از «پادشاهان زیرزمین»، عضویت در هر دو کانال زیر اجباری است.\n\n"
            "۱) عضو کانال اول شو.\n۲) عضو کانال دوم شو.\n۳) روی «بررسی عضویت» بزن."
        )
        keyboard = join_keyboard()
        # Keep gate prompts in private chats to avoid flooding game groups.
        if getattr(event, "message", None) is not None and getattr(event.message.chat, "type", "private") != "private":
            await event.answer("برای استفاده از ربات، ابتدا در خصوصی ربات عضویت دو کانال را بررسی کن.")
            return None
        try:
            if hasattr(event, "answer") and hasattr(event, "message") and event.message is not None:
                await event.answer(text, reply_markup=keyboard)
            elif hasattr(event, "answer"):
                await event.answer(text, show_alert=True)
                if getattr(event, "message", None):
                    await event.message.answer(text, reply_markup=keyboard)
        except TelegramAPIError:
            pass
        return None
