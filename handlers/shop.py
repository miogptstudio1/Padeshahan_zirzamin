"""فروشگاه تجهیزات — دستورات فارسی/انگلیسی + دکمه‌های شیشه‌ای."""
from __future__ import annotations
import uuid

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from games.empire import equipment as equipment_service
from games.empire.equipment_rules import ITEMS, BOX_PRICE

router = Router()

ITEM_ALIASES: dict[str, str] = {}
for key, meta in ITEMS.items():
    ITEM_ALIASES[key.lower()] = key
    ITEM_ALIASES[str(meta.get("name", "")).lower()] = key
    for alias in meta.get("aliases", []) if isinstance(meta.get("aliases"), list) else []:
        ITEM_ALIASES[str(alias).lower()] = key
# common Persian names
ITEM_ALIASES.update({
    "شمشیر چوبی": "wood_sword",
    "شمشیر آهنی": "iron_sword",
    "تیغه سایه": "shadow_blade",
    "زره چرمی": "leather_armor",
    "زره زنجیری": "chain_armor",
})


def _resolve_item(text: str) -> str | None:
    t = (text or "").strip().lower()
    if t in ITEM_ALIASES:
        return ITEM_ALIASES[t]
    # fuzzy: contains
    for k, v in ITEM_ALIASES.items():
        if k and (k in t or t in k):
            return v
    return None


def shop_keyboard(owner_id: int) -> InlineKeyboardMarkup:
    uid = int(owner_id)
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📋 لیست کالا", callback_data=f"shop:{uid}:list"),
            InlineKeyboardButton(text="🎒 موجودی", callback_data=f"shop:{uid}:inv"),
        ],
        [InlineKeyboardButton(text=f"🎁 صندوق ({BOX_PRICE})", callback_data=f"shop:{uid}:box")],
        [InlineKeyboardButton(text="🛒 منوی فروشگاه", callback_data=f"shop:{uid}:home")],
    ])


def inventory_keyboard(owner_id: int, inventory: list[dict]) -> InlineKeyboardMarkup:
    uid = int(owner_id)
    rows = []
    for row in inventory[:12]:
        key = row.get("key") or row.get("item_key")
        if not key:
            continue
        name = row.get("name") or ITEMS.get(key, {}).get("name", key)
        qty = row.get("quantity", 1)
        rows.append([
            InlineKeyboardButton(
                text=f"🔧 تجهیز {name} (×{qty})",
                callback_data=f"shop:{uid}:eq:{key}",
            )
        ])
    rows.append([
        InlineKeyboardButton(text="📋 فروشگاه", callback_data=f"shop:{uid}:list"),
        InlineKeyboardButton(text=f"🎁 صندوق", callback_data=f"shop:{uid}:box"),
    ])
    rows.append([InlineKeyboardButton(text="🔄 تازه‌سازی موجودی", callback_data=f"shop:{uid}:inv")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def catalog_keyboard(owner_id: int) -> InlineKeyboardMarkup:
    uid = int(owner_id)
    rows = []
    for key, meta in list(ITEMS.items())[:12]:
        price = meta.get("price", "?")
        name = meta.get("name", key)
        rows.append([
            InlineKeyboardButton(
                text=f"🛒 {name} — {price}🪙",
                callback_data=f"shop:{uid}:buy:{key}",
            )
        ])
    rows.append([
        InlineKeyboardButton(text="🎒 موجودی", callback_data=f"shop:{uid}:inv"),
        InlineKeyboardButton(text=f"🎁 صندوق ({BOX_PRICE})", callback_data=f"shop:{uid}:box"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _owner_ok(call: CallbackQuery, owner_id: int) -> bool:
    return int(call.from_user.id) == int(owner_id)


def _format_catalog() -> str:
    lines = ["🛒 <b>فروشگاه تجهیزات</b>\n"]
    for key, meta in ITEMS.items():
        lines.append(
            f"• <b>{meta.get('name', key)}</b> — {meta.get('price', '?')} سکه"
            f" | AT{meta.get('attack', 0)} DF{meta.get('defense', 0)}"
            f"\n  خرید: <code>خرید {meta.get('name', key)}</code>"
        )
    lines.append(f"\n🎁 صندوق شانس: {BOX_PRICE} سکه — <code>صندوق</code>")
    return "\n".join(lines)


def _format_inventory(data: dict) -> str:
    inv = data.get("inventory") or []
    equipped = data.get("equipped") or {}
    stats = data.get("stats") or {}
    lines = ["🎒 <b>موجودی تجهیزات</b>\n"]
    if not inv:
        lines.append("خالی است. از فروشگاه خرید کن.")
    else:
        for row in inv:
            key = row.get("key") or row.get("item_key")
            name = row.get("name") or ITEMS.get(key, {}).get("name", key)
            qty = row.get("quantity", 1)
            atk = ITEMS.get(key, {}).get("attack", 0)
            df = ITEMS.get(key, {}).get("defense", 0)
            lines.append(f"• {name} ×{qty}  (ATK {atk} / DEF {df})")
    w = equipped.get("weapon")
    a = equipped.get("armor")
    lines.append(
        f"\n🔧 <b>فعال:</b>\n"
        f"⚔️ سلاح: {ITEMS.get(w, {}).get('name', w or '—')}\n"
        f"🛡️ زره: {ITEMS.get(a, {}).get('name', a or '—')}\n"
        f"📊 قدرت تجهیز: ATK {stats.get('attack', 0)} · DEF {stats.get('defense', 0)}"
    )
    lines.append("\nروی دکمه زیر بزن تا تجهیز کنی 👇")
    return "\n".join(lines)


def _format_box_result(result: dict) -> str:
    reward = result.get("reward") or result
    rtype = reward.get("type")
    if rtype == "coins":
        return f"🎁 صندوق: 🪙 +{reward.get('amount', 0)} سکه\nموجودی: {result.get('coins', '—')}"
    if rtype == "item":
        key = reward.get("item_key") or reward.get("key")
        name = reward.get("name") or ITEMS.get(key, {}).get("name", key)
        return f"🎁 صندوق: آیتم <b>{name}</b>\nموجودی سکه: {result.get('coins', '—')}"
    return f"🎁 صندوق باز شد: {result}"


@router.message(Command("shop", "فروشگاه", "مغازه", "store"))
@router.message(F.text.in_({"فروشگاه", "مغازه", "شاپ", "store", "shop"}))
async def shop_home(message: Message):
    await message.answer(
        "🛒 <b>فروشگاه پادشاهان زیرزمین</b>\n\n"
        "با دکمه‌های زیر خرید کن، موجودی ببین یا صندوق باز کن.\n"
        "دستور متنی: <code>خرید نام‌کالا</code> · <code>تجهیز نام</code> · <code>موجودی</code>",
        parse_mode="HTML",
        reply_markup=catalog_keyboard(message.from_user.id),
    )


@router.message(Command("shop_buy", "خرید"))
@router.message(F.text.regexp(r"^(?:خرید|/shop_buy|/خرید)\s+(.+)$"))
async def shop_buy(message: Message):
    text = message.text or ""
    for pref in ("/shop_buy", "/خرید", "خرید"):
        if text.startswith(pref):
            text = text[len(pref):].strip()
            break
    key = _resolve_item(text)
    if not key:
        await message.answer("کالا پیدا نشد. بنویس: فروشگاه", reply_markup=catalog_keyboard(message.from_user.id))
        return
    try:
        result = await equipment_service.buy(message.from_user.id, key, 1)
        await message.answer(
            f"✅ خرید {result.get('item')} ×{result.get('quantity', 1)}\n"
            f"هزینه: {result.get('cost')} · 🪙 {result.get('coins')}",
            reply_markup=inventory_keyboard(
                message.from_user.id,
                (await equipment_service.dashboard(message.from_user.id)).get("inventory") or [],
            ),
        )
    except ValueError as e:
        await message.answer(f"❌ {e}")
    except Exception as e:
        await message.answer(f"❌ {e}")


@router.message(Command("equip", "تجهیز", "پوشیدن"))
@router.message(F.text.regexp(r"^(?:تجهیز|پوشیدن|/equip)\s+(.+)$"))
async def shop_equip(message: Message):
    text = message.text or ""
    for pref in ("/equip", "تجهیز", "پوشیدن"):
        if text.startswith(pref):
            text = text[len(pref):].strip()
            break
    key = _resolve_item(text)
    if not key:
        await message.answer("آیتم پیدا نشد. اول «موجودی» را ببین.")
        return
    try:
        result = await equipment_service.equip(message.from_user.id, key)
        stats = result.get("stats") or {}
        await message.answer(
            f"🔧 تجهیز شد: <b>{result.get('item')}</b>\n"
            f"ATK {stats.get('attack', 0)} · DEF {stats.get('defense', 0)}",
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
    inv = data.get("inventory") or []
    await message.answer(
        _format_inventory(data),
        parse_mode="HTML",
        reply_markup=inventory_keyboard(message.from_user.id, inv),
    )


@router.message(Command("box", "صندوق"))
@router.message(F.text.in_({"صندوق", "صندوق شانس", "جعبه", "box"}))
async def shop_box(message: Message):
    req = str(uuid.uuid4())
    try:
        result = await equipment_service.open_box(message.from_user.id, req)
        await message.answer(
            _format_box_result(result),
            parse_mode="HTML",
            reply_markup=shop_keyboard(message.from_user.id),
        )
    except ValueError as e:
        await message.answer(f"❌ {e}")
    except Exception as e:
        await message.answer(f"❌ {e}")


@router.callback_query(F.data.startswith("shop:"))
async def shop_callbacks(call: CallbackQuery):
    parts = (call.data or "").split(":")
    # shop:owner:action[:extra]
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
    extra = parts[3] if len(parts) > 3 else ""

    if not call.message:
        await call.answer()
        return

    try:
        if action == "home":
            await call.answer()
            await call.message.answer(
                "🛒 فروشگاه",
                reply_markup=catalog_keyboard(call.from_user.id),
            )
        elif action == "list":
            await call.answer()
            await call.message.answer(
                _format_catalog(),
                parse_mode="HTML",
                reply_markup=catalog_keyboard(call.from_user.id),
            )
        elif action == "inv":
            await call.answer()
            data = await equipment_service.dashboard(call.from_user.id)
            await call.message.answer(
                _format_inventory(data),
                parse_mode="HTML",
                reply_markup=inventory_keyboard(call.from_user.id, data.get("inventory") or []),
            )
        elif action == "buy" and extra:
            await call.answer("خرید…")
            result = await equipment_service.buy(call.from_user.id, extra, 1)
            data = await equipment_service.dashboard(call.from_user.id)
            await call.message.answer(
                f"✅ {result.get('item')} خریده شد (−{result.get('cost')}🪙)\nموجودی: {result.get('coins')}",
                reply_markup=inventory_keyboard(call.from_user.id, data.get("inventory") or []),
            )
        elif action == "eq" and extra:
            await call.answer("تجهیز…")
            result = await equipment_service.equip(call.from_user.id, extra)
            stats = result.get("stats") or {}
            data = await equipment_service.dashboard(call.from_user.id)
            await call.message.answer(
                f"🔧 <b>{result.get('item')}</b> فعال شد\nATK {stats.get('attack', 0)} · DEF {stats.get('defense', 0)}",
                parse_mode="HTML",
                reply_markup=inventory_keyboard(call.from_user.id, data.get("inventory") or []),
            )
        elif action == "box":
            await call.answer("صندوق…")
            result = await equipment_service.open_box(call.from_user.id, str(uuid.uuid4()))
            await call.message.answer(
                _format_box_result(result),
                parse_mode="HTML",
                reply_markup=shop_keyboard(call.from_user.id),
            )
        else:
            await call.answer("اقدام نامعتبر", show_alert=True)
    except ValueError as e:
        await call.answer(str(e)[:180], show_alert=True)
    except Exception as e:
        await call.answer("خطا", show_alert=True)
        try:
            await call.message.answer(f"❌ {e}")
        except Exception:
            pass
