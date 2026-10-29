"""فروشگاه تجهیزات — دستورات فارسی و انگلیسی."""
from __future__ import annotations
import uuid

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from games.empire import equipment as equipment_service
from games.empire.equipment_rules import ITEMS, BOX_PRICE

router = Router()

# نام فارسی/انگلیسی → کلید آیتم
ITEM_ALIASES: dict[str, str] = {}
for key, meta in ITEMS.items():
    ITEM_ALIASES[key] = key
    ITEM_ALIASES[meta["name"]] = key
    ITEM_ALIASES[meta["name"].replace("ٔ", "")] = key


def _owner_ok(call: CallbackQuery, owner_id: int) -> bool:
    if int(call.from_user.id) != int(owner_id):
        return False
    return True


def shop_keyboard(owner_id: int) -> InlineKeyboardMarkup:
    uid = int(owner_id)
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📋 لیست کالا", callback_data=f"shop:{uid}:list"),
            InlineKeyboardButton(text="🎒 موجودی من", callback_data=f"shop:{uid}:inv"),
        ],
        [
            InlineKeyboardButton(text=f"🎁 صندوق ({BOX_PRICE} سکه)", callback_data=f"shop:{uid}:box"),
        ],
    ])


def _format_catalog() -> str:
    weapons = [v for v in ITEMS.values() if v["kind"] == "weapon"]
    armors = [v for v in ITEMS.values() if v["kind"] == "armor"]
    lines = ["🛒 <b>فروشگاه پادشاهان</b>\n", "⚔️ <b>سلاح</b>"]
    for it in weapons:
        lines.append(
            f"• {it['name']} — {it['price']:,} سکه | AT:{it['attack']} | {it['rarity']}"
        )
    lines.append("\n🛡️ <b>زره</b>")
    for it in armors:
        lines.append(
            f"• {it['name']} — {it['price']:,} سکه | DEF:{it['defense']} | {it['rarity']}"
        )
    lines.append(
        f"\n🎁 صندوق شانس: {BOX_PRICE:,} سکه\n\n"
        f"خرید: <code>خرید شمشیر چوبی</code>\n"
        f"یا: <code>/shop_buy wood_sword</code>\n"
        f" تجهیز: <code>تجهیز شمشیر آهنی</code>"
    )
    return "\n".join(lines)


@router.message(Command("shop", "فروشگاه", "مغازه", "store"))
@router.message(F.text.in_({"فروشگاه", "مغازه", "شاپ", "shop", "فروشگاه تجهیزات"}))
async def shop_menu(message: Message):
    await message.answer(
        "🛒 <b>فروشگاه تجهیزات</b>\n\n"
        "سلاح و زره بخر، تجهیز کن، یا صندوق شانس باز کن.\n"
        "همه قیمت‌ها با سکهٔ درون‌بازی است.",
        reply_markup=shop_keyboard(message.from_user.id),
        parse_mode="HTML",
    )
    await message.answer(_format_catalog(), parse_mode="HTML")


@router.message(Command("shop_buy", "خرید"))
@router.message(F.text.regexp(r"^(?:خرید|/shop_buy|/خرید)\s+(.+)$"))
async def shop_buy(message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "مثال: <code>خرید شمشیر چوبی</code>\nیا <code>/shop_buy wood_sword</code>",
            parse_mode="HTML",
        )
        return
    raw = parts[1].strip()
    # optional quantity at end: خرید شمشیر چوبی 2
    tokens = raw.rsplit(maxsplit=1)
    qty = 1
    name = raw
    if len(tokens) == 2 and tokens[1].isdigit():
        qty = max(1, min(10, int(tokens[1])))
        name = tokens[0].strip()
    key = ITEM_ALIASES.get(name) or ITEM_ALIASES.get(name.lower())
    if not key:
        # try match without spaces nuances
        for alias, k in ITEM_ALIASES.items():
            if alias.replace(" ", "") == name.replace(" ", ""):
                key = k
                break
    if not key:
        await message.answer("❌ کالا پیدا نشد. با «فروشگاه» لیست رو ببین.")
        return
    try:
        result = await equipment_service.buy(message.from_user.id, key, qty)
        await message.answer(
            f"✅ خرید انجام شد: <b>{ITEMS[key]['name']}</b> ×{qty}\n"
            f"🪙 موجودی: {result.get('coins', result.get('balance', '—'))}",
            parse_mode="HTML",
        )
    except ValueError as e:
        await message.answer(f"❌ {e}")
    except Exception as e:
        # service may return dict without raising
        await message.answer(f"❌ خطا در خرید: {e}")


@router.message(Command("equip", "تجهیز", "پوشیدن"))
@router.message(F.text.regexp(r"^(?:تجهیز|پوشیدن|/equip)\s+(.+)$"))
async def shop_equip(message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("مثال: <code>تجهیز شمشیر آهنی</code>", parse_mode="HTML")
        return
    name = parts[1].strip()
    key = ITEM_ALIASES.get(name) or ITEM_ALIASES.get(name.lower())
    if not key:
        await message.answer("❌ آیتم پیدا نشد.")
        return
    try:
        result = await equipment_service.equip(message.from_user.id, key)
        stats = result.get("stats") or {}
        await message.answer(
            "✅ تجهیز شد: <b>{}</b>\n⚔️ حمله: {} | 🛡️ دفاع: {}".format(
                ITEMS[key]["name"], stats.get("attack", 0), stats.get("defense", 0)
            ),
            parse_mode="HTML",
        )
    except ValueError as e:
        await message.answer(f"❌ {e}")
    except Exception as e:
        await message.answer(f"❌ {e}")


@router.message(Command("inventory", "موجودی", "کوله"))
@router.message(F.text.in_({"موجودی", "کوله", "اینونتوری", "inventory"}))
async def shop_inventory(message: Message):
    try:
        data = await equipment_service.dashboard(message.from_user.id)
    except Exception as e:
        await message.answer(f"❌ {e}")
        return
    inv = data.get("inventory") or data.get("items") or []
    equipped = data.get("equipped") or {}
    lines = ["🎒 <b>موجودی تجهیزات</b>\n"]
    if not inv:
        lines.append("خالی است. از «فروشگاه» خرید کن.")
    else:
        for row in inv:
            if isinstance(row, dict):
                k = row.get("item_key") or row.get("key")
                q = row.get("quantity", 1)
                name = row.get("name") or ITEMS.get(k, {}).get("name", k)
                lines.append(f"• {name} ×{q}")
            else:
                lines.append(f"• {row}")
    w = equipped.get("weapon")
    a = equipped.get("armor")
    lines.append(
        f"\n🔧 فعال: سلاح {ITEMS.get(w, {}).get('name', w or '—')} | "
        f"زره {ITEMS.get(a, {}).get('name', a or '—')}"
    )
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=shop_keyboard(message.from_user.id))


@router.message(Command("box", "صندوق"))
@router.message(F.text.in_({"صندوق", "صندوق شانس", "جعبه", "box"}))
async def shop_box(message: Message):
    req = str(uuid.uuid4())
    try:
        result = await equipment_service.open_box(message.from_user.id, req)
        reward = result.get("reward") or result
        rtype = reward.get("type")
        if rtype == "coins":
            await message.answer(f"🎁 صندوق باز شد! 🪙 +{reward.get('amount', 0)} سکه")
        elif rtype == "item":
            key = reward.get("item_key") or reward.get("key")
            name = reward.get("name") or ITEMS.get(key, {}).get("name", key)
            await message.answer(f"🎁 صندوق باز شد! آیتم: <b>{name}</b>", parse_mode="HTML")
        else:
            await message.answer(f"🎁 صندوق باز شد! {result}")
    except ValueError as e:
        await message.answer(f"❌ {e}")
    except Exception as e:
        await message.answer(f"❌ {e}")


@router.callback_query(F.data.startswith("shop:"))
async def shop_callbacks(call: CallbackQuery):
    parts = (call.data or "").split(":")
    # shop:{owner}:{action}
    if len(parts) < 3:
        await call.answer("دکمه نامعتبر", show_alert=True)
        return
    try:
        owner_id = int(parts[1])
    except ValueError:
        await call.answer("دکمه نامعتبر", show_alert=True)
        return
    if not _owner_ok(call, owner_id):
        await call.answer("🚫 این پنل مال تو نیست.", show_alert=True)
        return
    action = parts[2]
    await call.answer()
    if not call.message:
        return
    if action == "list":
        await call.message.answer(_format_catalog(), parse_mode="HTML")
    elif action == "inv":
        call.message.from_user = call.from_user  # type: ignore
        # reuse inventory display
        try:
            data = await equipment_service.dashboard(call.from_user.id)
            inv = data.get("inventory") or data.get("items") or []
            lines = ["🎒 موجودی تو:"]
            if not inv:
                lines.append("خالی است.")
            else:
                for row in inv:
                    if isinstance(row, dict):
                        k = row.get("item_key") or row.get("key")
                        q = row.get("quantity", 1)
                        lines.append(f"• {ITEMS.get(k, {}).get('name', k)} ×{q}")
            await call.message.answer("\n".join(lines), reply_markup=shop_keyboard(call.from_user.id))
        except Exception as e:
            await call.message.answer(str(e))
    elif action == "box":
        req = str(uuid.uuid4())
        try:
            result = await equipment_service.open_box(call.from_user.id, req)
            if result.get("type") == "coins" or result.get("reward_type") == "coins":
                amt = result.get("amount") or result.get("reward_amount")
                await call.message.answer(f"🎁 +{amt} سکه از صندوق!")
            else:
                key = result.get("item_key") or result.get("reward_key")
                name = ITEMS.get(key, {}).get("name", key)
                await call.message.answer(f"🎁 آیتم: {name}")
        except ValueError as e:
            await call.message.answer(str(e))
        except Exception as e:
            await call.message.answer(str(e))
