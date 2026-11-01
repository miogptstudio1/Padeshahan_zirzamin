"""Required-channel membership gate for Telegram bot updates and Mini App APIs."""
from __future__ import annotations
from aiogram import BaseMiddleware
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from aiogram.exceptions import TelegramAPIError
from typing import Any, Awaitable, Callable

from membership_core import REQUIRED_CHANNELS, MEMBER_STATUSES, membership_status


def join_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 عضویت در کانال اول", url=REQUIRED_CHANNELS[0][2])],
        [InlineKeyboardButton(text="🌿 عضویت در کانال دوم", url=REQUIRED_CHANNELS[1][2])],
        [InlineKeyboardButton(text="✅ بررسی عضویت", callback_data="membership:check")],
    ])


MEMBERSHIP_TEXT = (
    "قبل از هر چیز باید تو هر دو کانال عضو باشی.\n\n"
    "دکمه‌های پایینو بزن، عضو شو، بعد «بررسی عضویت» رو بزن.\n"
    "اگه عضو باشی راهت می‌دم تو."
)

MEMBERSHIP_ERROR_TEXT = (
    "الان چک عضویت درست کار نکرد.\n"
    "یه دقیقه بعد دوباره «بررسی عضویت» بزن.\n"
    "اگه بازم همین بود به ادمین بگو ربات تو کانال‌ها ادمین باشه."
)

# Plain-text triggers that count as "using the bot" (without leading /)
BOT_TEXT_TRIGGERS = {
    "شروع", "استارت", "start",
    "پروفایل", "پروفایل من", "profile",
    "راهنما", "کمک", "هلپ", "help", "راهنما کامل", "راهنمای کامل", "راهنماکامل", "guide",
    "ادمین", "مدیریت", "پنل ادمین", "admin",
    "آمار", "stats",
    "فروشگاه", "مغازه", "شاپ", "shop", "فروشگاه تجهیزات",
    "موجودی", "کوله", "صندوق", "صندوق شانس", "جعبه",
    "امپراتوری", "امپراطوری", "empire",
    "ایونت", "رویداد", "خاندان", "خانواده", "فمیلی",
    "رتبه ایونت", "رتبه خاندان", "رتبه ثروت", "دارایی", "ارتش", "قلمروها", "نقشه",
    "قبول خاندان", "خروج خاندان",
    "مافیا بساز", "مافیا جوین", "مافیا شروع", "مافیا وضعیت", "مافیا شب", "مافیا قوانین", "مافیا لغو",
    "کودتا بساز", "کودتا جوین", "کودتا شروع", "کودتا وضعیت", "کودتا کمک", "کودتا دست", "کودتا منو",
    "حمله", "جیب‌بری", "ارتش پیشرفته", "بازار", "مارکت", "فرماندهان", "جاسوسی", "جاسوس", "باس", "رئیس", "باس بزن", "مأموریت", "ماموریت", "تسک", "جایزه مأموریت", "شهرت", "هیل", "درمان", "جان", "خون", "دزدی", "قاچاق", "باج", "باج‌گیری", "پناهگاه", "خلاف", "جرم", "ارتقا پناهگاه",
    "پاداش", "پاداش روزانه", "کار", "کار روزانه",
    "چالش", "پوشش",
}

BOT_TEXT_PREFIXES = (
    "جستجو ", "بن ", "آنبن ", "انبن ", "سکه ", "مقام ", "حذف‌مقام ", "حذفمقام ",
    "همگانی ", "خرید ", "تجهیز ", "پوشیدن ", "ساخت خاندان ", "دعوت خاندان ", "حمله ", "جیب‌بری ", "باج ", "جاسوسی ", "استخدام ", "فرمانده ", "فروش بازار ", "خرید بازار ", "لغو بازار ", "واریز خاندان ", "اخراج خاندان ", "جمع درآمد ", "خرید کسب ",
    "/mafia", "/coup", "/empire", "/admin", "/ban", "/unban", "/lookup",
    "/coins", "/grant", "/revoke", "/broadcast", "/stats", "/profile",
    "/help", "/start", "/شروع", "/پروفایل", "/راهنما", "/کمک", "/ادمین",
    "/shop", "/shop_buy", "/equip", "/inventory", "/box", "/فروشگاه", "/خرید",
)


def _is_bot_command_message(event: Message) -> bool:
    """True only when the user is actually trying to use the bot."""
    text = (event.text or event.caption or "").strip()
    if not text:
        return False
    # Telegram command entity (/start@BotName etc.)
    entities = event.entities or event.caption_entities or []
    for ent in entities:
        if getattr(ent, "type", None) == "bot_command":
            return True
    if text.startswith("/"):
        return True
    lower = text.lower()
    if text in BOT_TEXT_TRIGGERS or lower in BOT_TEXT_TRIGGERS:
        return True
    for prefix in BOT_TEXT_PREFIXES:
        if text.startswith(prefix) or lower.startswith(prefix.lower()):
            return True
    return False


class RequiredMembershipMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user is None:
            return await handler(event, data)

        # Always allow the explicit check callback through so the user can retry.
        if getattr(event, "data", None) == "membership:check":
            return await handler(event, data)

        # Super-admins from ADMIN_IDS bypass channel gate.
        try:
            from config import ADMIN_IDS
            if int(user.id) in ADMIN_IDS:
                return await handler(event, data)
        except Exception:
            pass

        # --- Only gate actual bot usage, not normal group chat ---
        if isinstance(event, Message):
            chat_type = getattr(event.chat, "type", "private")
            # In groups/channels: ignore ordinary messages completely.
            if chat_type != "private" and not _is_bot_command_message(event):
                return await handler(event, data)
            # In private: only gate when user issues a bot command / trigger.
            # Casual non-command text in private still passes (no spam).
            if chat_type == "private" and not _is_bot_command_message(event):
                return await handler(event, data)
        elif isinstance(event, CallbackQuery):
            # Inline button presses always count as bot usage → gate them.
            pass
        else:
            return await handler(event, data)

        bot = data.get("bot")
        if bot is None:
            return await handler(event, data)

        joined, _missing, error = await membership_status(bot, user.id)
        if joined:
            return await handler(event, data)

        text = MEMBERSHIP_ERROR_TEXT if error else MEMBERSHIP_TEXT
        keyboard = join_keyboard()

        chat = None
        if isinstance(event, Message):
            chat = event.chat
        elif isinstance(event, CallbackQuery) and event.message:
            chat = event.message.chat

        # Groups: short hint, don't flood with full join UI
        if chat is not None and getattr(chat, "type", "private") != "private":
            try:
                if isinstance(event, CallbackQuery):
                    await event.answer(
                        "🔒 اول تو چت خصوصی ربات عضویت دو کانال رو تأیید کن.",
                        show_alert=True,
                    )
                else:
                    await event.answer(
                        "🔒 برای استفاده از ربات، اول تو چت خصوصی ربات عضویت دو کانال رو تأیید کن."
                    )
            except TelegramAPIError:
                pass
            return None

        # Private chat: full prompt + join buttons
        try:
            if isinstance(event, Message):
                await event.answer(text, reply_markup=keyboard)
            elif isinstance(event, CallbackQuery):
                await event.answer()
                if event.message:
                    try:
                        await event.message.edit_text(text, reply_markup=keyboard)
                    except TelegramAPIError:
                        await event.message.answer(text, reply_markup=keyboard)
                else:
                    await bot.send_message(user.id, text, reply_markup=keyboard)
        except TelegramAPIError:
            pass
        return None
