"""کیف پول و تبدیل ارزهای چندلایه."""
from __future__ import annotations
import re

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from games.currency import service as currency_service

router = Router()


@router.message(Command("wallet", "کیف", "کیف_پول", "ارزها"))
@router.message(F.text.in_({"کیف پول", "کیف", "ارزها", "موجودی ارز", "wallet"}))
async def cmd_wallet(message: Message):
    b = await currency_service.balances(message.from_user.id)
    await message.answer(
        "💰 کیف پول تو\n"
        + currency_service.format_wallet(b)
        + "\n\n"
        + currency_service.rates_text()
    )


@router.message(Command("rates", "نرخ", "نرخ_تبدیل"))
@router.message(F.text.in_({"نرخ", "نرخ تبدیل", "نرخ ارز"}))
async def cmd_rates(message: Message):
    await message.answer(currency_service.rates_text())


@router.message(Command("convert", "تبدیل"))
@router.message(F.text.regexp(r"^(?:تبدیل|/convert)\s+(.+)$", flags=re.I))
async def cmd_convert(message: Message):
    text = (message.text or "").strip()
    for pref in ("/convert", "تبدیل"):
        if text.lower().startswith(pref.lower()) or text.startswith(pref):
            text = text[len(pref):].strip()
            break
    parts = text.split()
    if not parts:
        await message.answer(currency_service.rates_text())
        return
    amount = 1
    if parts[-1].replace(",", "").isdigit():
        amount = int(parts[-1].replace(",", ""))
        parts = parts[:-1]
    key = " ".join(parts).strip().lower()

    mapping = {
        "الماس": "diamond_from_coins",
        "سکه به الماس": "diamond_from_coins",
        "الماس از سکه": "diamond_from_coins",
        "سکه": "coins_from_diamond",
        "الماس به سکه": "coins_from_diamond",
        "مینت": "mint_from_diamond",
        "الماس به مینت": "mint_from_diamond",
        "مینت از الماس": "mint_from_diamond",
        "مینت به الماس": "diamond_from_mint",
        "الماس از مینت": "diamond_from_mint",
        "نوا": "nova_from_mint",
        "مینت به نوا": "nova_from_mint",
        "نوا از مینت": "nova_from_mint",
        "نوا به مینت": "mint_from_nova",
        "مینت از نوا": "mint_from_nova",
    }
    direction = mapping.get(key)
    if not direction:
        if key in {"الماس", "diamond"}:
            direction = "diamond_from_coins"
        elif key in {"مینت", "mint"}:
            direction = "mint_from_diamond"
        elif key in {"نوا", "nova"}:
            direction = "nova_from_mint"
        else:
            await message.answer(
                "فرمت:\n"
                "تبدیل الماس ۱\n"
                "تبدیل مینت ۱\n"
                "تبدیل نوا ۱\n"
                "تبدیل الماس به سکه ۱\n"
                "تبدیل مینت به الماس ۱\n"
                "تبدیل نوا به مینت ۱"
            )
            return
    try:
        r = await currency_service.convert(message.from_user.id, direction, amount)
        await message.answer(
            f"✅ {r['message']}\n\n" + currency_service.format_wallet(r)
        )
    except ValueError as e:
        await message.answer(str(e))
