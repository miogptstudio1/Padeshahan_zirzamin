"""کمک‌کننده UI پنل: ویرایش همان پیام یا پاک کردن قبلی."""
from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message


async def panel_update(
    call: CallbackQuery,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = None,
) -> Message | None:
    """پیام پنل را همان‌جا آپدیت کن؛ اگر نشد قبلی را پاک کن و جدید بفرست."""
    msg = call.message
    if msg is None:
        return None
    try:
        await msg.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        return msg
    except TelegramBadRequest as exc:
        err = str(exc).lower()
        # محتوای یکسان — مشکلی نیست
        if "message is not modified" in err:
            return msg
    except Exception:
        pass
    # fallback: پاک کردن قبلی + پیام جدید
    try:
        await msg.delete()
    except Exception:
        pass
    try:
        return await msg.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception:
        return None


async def panel_answer_plain(
    call: CallbackQuery,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> Message | None:
    """مثل panel_update بدون parse_mode HTML."""
    return await panel_update(call, text, reply_markup=reply_markup, parse_mode=None)
