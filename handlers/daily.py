"""مأموریت روزانه."""
from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from games.daily import service as daily_service

router = Router()


@router.message(Command("missions", "مأموریت", "ماموریت", "تسک"))
@router.message(F.text.in_({"مأموریت", "ماموریت", "مأموریت روزانه", "تسک", "missions"}))
async def missions(message: Message):
    rows = await daily_service.status(message.from_user.id)
    lines = ["مأموریت امروز:\n"]
    for r in rows:
        mark = "✓" if r["claimed"] else ("●" if r["done"] else "○")
        lines.append(
            f"{mark} {r['title']} ({r['progress']}/{r['target']}) — {r['reward']} سکه"
        )
    lines.append("\nاگه تموم کردی بزن: جایزه مأموریت")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="دریافت جایزه‌ها",
            callback_data=f"daily:{message.from_user.id}:claim",
        )]
    ])
    await message.answer("\n".join(lines), reply_markup=kb)


@router.message(Command("claim_missions", "جایزه_مأموریت"))
@router.message(F.text.in_({"جایزه مأموریت", "جایزه ماموریت", "دریافت مأموریت"}))
async def claim(message: Message):
    r = await daily_service.claim_all(message.from_user.id)
    if not r["reward"]:
        await message.answer("چیزی برای دریافت نیست. اول مأموریت‌ها رو ببند.")
        return
    await message.answer(f"+{r['reward']} سکه گرفت. موجودی: {r['balance']}")


@router.callback_query(F.data.startswith("daily:"))
async def daily_cb(call):
    parts = (call.data or "").split(":")
    if len(parts) < 3:
        await call.answer("نامعتبر", show_alert=True)
        return
    try:
        owner = int(parts[1])
    except ValueError:
        await call.answer("نامعتبر", show_alert=True)
        return
    if call.from_user.id != owner:
        await call.answer("مال تو نیست.", show_alert=True)
        return
    if parts[2] == "claim":
        r = await daily_service.claim_all(owner)
        if not r["reward"]:
            await call.answer("چیزی نیست", show_alert=True)
            return
        await call.answer(f"+{r['reward']}")
        await call.message.answer(f"+{r['reward']} سکه · موجودی {r['balance']}")
    else:
        await call.answer("نامعتبر", show_alert=True)
