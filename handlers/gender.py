"""انتخاب و تغییر جنسیت."""
from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from handlers.panel_ui import panel_update
from games.profile import service as profile_service

router = Router()


def gender_keyboard(uid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👨 پسر", callback_data=f"gender:{uid}:male"),
            InlineKeyboardButton(text="👩 دختر", callback_data=f"gender:{uid}:female"),
        ],
        [
            InlineKeyboardButton(text="🧑 نامشخص", callback_data=f"gender:{uid}:other"),
        ],
    ])


async def prompt_gender(message: Message) -> None:
    await message.answer(
        "جنسیت کاراکترت رو انتخاب کن:\n"
        "(بعداً با دستور «جنسیت» عوضش می‌کنی)",
        reply_markup=gender_keyboard(message.from_user.id),
    )


@router.message(Command("gender", "جنسیت", "جنس"))
@router.message(F.text.in_({"جنسیت", "جنس", "gender", "انتخاب جنسیت"}))
async def cmd_gender(message: Message):
    cur = await profile_service.gender_label(message.from_user.id)
    await message.answer(
        f"الان: {cur}\nیکی رو انتخاب کن:",
        reply_markup=gender_keyboard(message.from_user.id),
    )


@router.callback_query(F.data.startswith("gender:"))
async def gender_cb(call: CallbackQuery):
    parts = (call.data or "").split(":")
    if len(parts) != 3:
        await call.answer("نامعتبر", show_alert=True)
        return
    try:
        owner = int(parts[1])
    except ValueError:
        await call.answer("نامعتبر", show_alert=True)
        return
    if call.from_user.id != owner:
        await call.answer("این پنل مال تو نیست.", show_alert=True)
        return
    key = parts[2]
    try:
        r = await profile_service.set_gender(call.from_user.id, key)
    except ValueError as e:
        await call.answer(str(e)[:180], show_alert=True)
        return
    await call.answer("ثبت شد")
    await panel_update(
        call,
        f"{r['emoji']} جنسیت ثبت شد: {r['label']}\n"
        f"هر وقت خواستی بنویس جنسیت.",
    )
