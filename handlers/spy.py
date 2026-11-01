"""دستورات جاسوسی."""
from __future__ import annotations
import re

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from games.spy import service as spy_service

router = Router()


def _target(message: Message) -> int | None:
    if message.reply_to_message and message.reply_to_message.from_user:
        return int(message.reply_to_message.from_user.id)
    nums = re.findall(r"\d{5,15}", message.text or "")
    return int(nums[-1]) if nums else None


@router.message(Command("spy", "جاسوسی", "جاسوس"))
@router.message(F.text.regexp(r"^(?:جاسوسی|جاسوس|/spy)\b"))
async def cmd_spy(message: Message):
    tid = _target(message)
    if not tid:
        await message.answer(
            "ریپلای کن یا بنویس: جاسوسی 123456\n"
            f"هزینه هر بار {spy_service.SPY_COST} سکه."
        )
        return
    try:
        r = await spy_service.spy_on(message.from_user.id, tid)
        if r["success"]:
            await message.answer(f"گزارش جاسوس (−{r['cost']}):\n\n{r['report']}")
        else:
            await message.answer(f"{r['report']}\n−{r['cost']} سکه")
            try:
                await message.bot.send_message(
                    tid,
                    f"یکی خواست ازت جاسوسی کنه و لو رفت.\nمظنون احتمالی: {message.from_user.full_name or message.from_user.id}",
                )
            except Exception:
                pass
    except ValueError as e:
        await message.answer(str(e))
