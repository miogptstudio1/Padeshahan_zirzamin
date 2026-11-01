"""بازار بازیکن‌به‌بازیکن."""
from __future__ import annotations
import re

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from games.market import service as market_svc
from games.empire.equipment_rules import ITEMS
from handlers.shop import ITEM_ALIASES, _resolve_item

router = Router()


def market_keyboard(uid: int, listings: list) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="🔄 تازه‌سازی", callback_data=f"mkt:{uid}:list")]]
    for L in listings[:10]:
        rows.append([
            InlineKeyboardButton(
                text=f"🛒 #{L['id']} {L['item_name']} — {L['price']}🪙",
                callback_data=f"mkt:{uid}:buy:{L['id']}",
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("market", "بازار", "مارکت"))
@router.message(F.text.in_({"بازار", "مارکت", "بازار سیاه", "market"}))
async def market_list(message: Message):
    rows = await market_svc.list_open(15)
    if not rows:
        await message.answer(
            "🏪 بازار خالی است.\n"
            "فروش: <code>فروش بازار شمشیر چوبی 200</code>\n"
            "خرید: دکمه زیر یا <code>خرید بازار 12</code>",
            parse_mode="HTML",
        )
        return
    lines = ["🏪 <b>بازار بازیکن‌ها</b>\n"]
    for L in rows:
        lines.append(
            f"#{L['id']} · {L['item_name']} ×{L['quantity']} — <b>{L['price']:,}</b>🪙"
            f"\n   فروشنده: {L['seller_name'] or L['seller_id']}"
        )
    lines.append("\nفروش: <code>فروش بازار [کالا] [قیمت]</code>")
    await message.answer(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=market_keyboard(message.from_user.id, rows),
    )


@router.message(Command("market_sell", "فروش_بازار"))
@router.message(F.text.regexp(r"^(?:فروش بازار|/market_sell)\s+(.+)$"))
async def market_sell(message: Message):
    text = message.text or ""
    for pref in ("/market_sell", "فروش بازار"):
        if text.startswith(pref):
            text = text[len(pref):].strip()
            break
    # last token price
    parts = text.rsplit(maxsplit=1)
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("مثال: <code>فروش بازار شمشیر چوبی 250</code>", parse_mode="HTML")
        return
    item_text, price_s = parts[0], parts[1]
    key = _resolve_item(item_text)
    if not key:
        # try raw key
        key = ITEM_ALIASES.get(item_text.lower())
    if not key:
        await message.answer("کالا پیدا نشد. از «موجودی» نام دقیق را ببین.")
        return
    try:
        r = await market_svc.create_listing(message.from_user.id, key, int(price_s), 1)
        await message.answer(
            f"✅ آگهی #{r['id']}: {r['item']} به قیمت {r['price']:,}🪙\n"
            f"لغو: <code>لغو بازار {r['id']}</code>",
            parse_mode="HTML",
        )
    except ValueError as e:
        await message.answer(f"❌ {e}")


@router.message(Command("market_buy", "خرید_بازار"))
@router.message(F.text.regexp(r"^(?:خرید بازار|/market_buy)\s+(\d+)$"))
async def market_buy(message: Message):
    m = re.search(r"(\d+)", message.text or "")
    if not m:
        await message.answer("مثال: <code>خرید بازار 12</code>", parse_mode="HTML")
        return
    try:
        r = await market_svc.buy_listing(message.from_user.id, int(m.group(1)))
        await message.answer(
            f"✅ خریدی: {r['item']} ×{r['quantity']} (−{r['price']:,}🪙)\nموجودی: {r['balance']:,}"
        )
        try:
            await message.bot.send_message(
                r["seller_id"],
                f"🏪 آگهی‌ات فروش رفت!\n{r['item']} · +{r['price']:,} سکه",
            )
        except Exception:
            pass
    except ValueError as e:
        await message.answer(f"❌ {e}")


@router.message(Command("market_cancel", "لغو_بازار"))
@router.message(F.text.regexp(r"^(?:لغو بازار|/market_cancel)\s+(\d+)$"))
async def market_cancel(message: Message):
    m = re.search(r"(\d+)", message.text or "")
    if not m:
        await message.answer("مثال: <code>لغو بازار 12</code>", parse_mode="HTML")
        return
    try:
        await market_svc.cancel_listing(message.from_user.id, int(m.group(1)))
        await message.answer("✅ آگهی لغو شد و آیتم برگشت به موجودی.")
    except ValueError as e:
        await message.answer(f"❌ {e}")


@router.callback_query(F.data.startswith("mkt:"))
async def market_cb(call):
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
        await call.answer("🚫 این پنل مال تو نیست.", show_alert=True)
        return
    action = parts[2]
    try:
        if action == "list":
            await call.answer()
            rows = await market_svc.list_open(15)
            lines = ["🏪 بازار\n"] + [
                f"#{L['id']} {L['item_name']} — {L['price']}🪙" for L in rows
            ] or ["خالی"]
            await call.message.answer("\n".join(lines), reply_markup=market_keyboard(owner, rows))
        elif action == "buy" and len(parts) > 3:
            r = await market_svc.buy_listing(owner, int(parts[3]))
            await call.answer("خرید شد")
            await call.message.answer(f"✅ {r['item']} (−{r['price']}) · 💰 {r['balance']}")
        else:
            await call.answer("نامعتبر", show_alert=True)
    except ValueError as e:
        await call.answer(str(e)[:180], show_alert=True)
    except Exception as e:
        await call.answer(str(e)[:100], show_alert=True)
