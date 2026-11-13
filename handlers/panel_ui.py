"""کمک‌کننده UI پنل: ترجیح با ویرایش همان پیام؛ بدون پریدن بی‌دلیل."""
from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message


def _clip(text: str, limit: int = 3900) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[: limit - 12].rstrip() + "\n… (کوتاه شد)"


async def panel_update(
    call: CallbackQuery,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = None,
) -> Message | None:
    """همان پیام پنل را آپدیت کن.

    - تا جای ممکن delete نکن (پریدن پنل)
    - اگر HTML گیر کرد بدون parse_mode امتحان کن
    - فقط وقتی edit ممکن نبود پیام جدید بفرست و بعد قبلی را پاک کن
    """
    msg = call.message
    if msg is None:
        return None
    text = _clip(text)

    async def _edit(pm: str | None) -> bool:
        try:
            await msg.edit_text(text, reply_markup=reply_markup, parse_mode=pm)
            return True
        except TelegramBadRequest as exc:
            err = str(exc).lower()
            if "message is not modified" in err:
                return True
            # دکمه‌ها/متن خیلی بزرگ یا پیام غیرقابل‌ویرایش
            return False
        except Exception:
            return False

    # 1) با parse_mode درخواستی
    if await _edit(parse_mode):
        return msg
    # 2) بدون parse_mode (اغلب HTML خراب باعث شکست می‌شود)
    if parse_mode and await _edit(None):
        return msg
    # 3) فقط reply_markup را عوض کن اگر متن سنگین است
    try:
        await msg.edit_reply_markup(reply_markup=reply_markup)
        # متن را هم در صورت امکان با answer کوتاه بگو؟ نه — پنل همان بماند
    except Exception:
        pass

    # 4) پیام جدید بفرست؛ فقط بعد از موفقیت قبلی را پاک کن
    new_msg = None
    try:
        new_msg = await msg.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception:
        try:
            new_msg = await msg.answer(text, reply_markup=reply_markup)
        except Exception:
            return msg
    if new_msg is not None:
        try:
            await msg.delete()
        except Exception:
            pass
    return new_msg or msg


async def panel_answer_plain(
    call: CallbackQuery,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> Message | None:
    return await panel_update(call, text, reply_markup=reply_markup, parse_mode=None)
