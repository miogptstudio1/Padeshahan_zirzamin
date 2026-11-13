"""فروشگاه تجهیزات — دستورات فارسی/انگلیسی + دکمه‌های شیشه‌ای."""
from __future__ import annotations
import uuid

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from handlers.panel_ui import panel_update

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


SHOP_PAGE_SIZE = 8


def inventory_keyboard(owner_id: int, inventory: list[dict], page: int = 0) -> InlineKeyboardMarkup:
    uid = int(owner_id)
    items = [r for r in inventory if (r.get("key") or r.get("item_key"))]
    total = len(items)
    pages = max(1, (total + SHOP_PAGE_SIZE - 1) // SHOP_PAGE_SIZE)
    page = max(0, min(int(page), pages - 1))
    start = page * SHOP_PAGE_SIZE
    chunk = items[start:start + SHOP_PAGE_SIZE]
    rows = []
    for row in chunk:
        key = row.get("key") or row.get("item_key")
        name = row.get("name") or ITEMS.get(key, {}).get("name", key)
        qty = row.get("quantity", 1)
        lv = int(row.get("upgrade_level") or 0)
        rows.append([
            InlineKeyboardButton(
                text=f"🔧 تجهیز {name} +{lv} (×{qty})",
                callback_data=f"shop:{uid}:eq:{key}",
            ),
            InlineKeyboardButton(
                text="⬆️",
                callback_data=f"equp:{uid}:{key}",
            ),
        ])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️ قبلی", callback_data=f"shop:{uid}:inv:{page-1}"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton(text="بعدی ▶️", callback_data=f"shop:{uid}:inv:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([
        InlineKeyboardButton(text="📋 فروشگاه", callback_data=f"shop:{uid}:list:0"),
        InlineKeyboardButton(text="🎁 صندوق", callback_data=f"shop:{uid}:box"),
    ])
    rows.append([InlineKeyboardButton(
        text=f"🔄 موجودی ({page+1}/{pages})",
        callback_data=f"shop:{uid}:inv:{page}",
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def catalog_keyboard(owner_id: int, page: int = 0) -> InlineKeyboardMarkup:
    uid = int(owner_id)
    keys = list(ITEMS.keys())
    total = len(keys)
    pages = max(1, (total + SHOP_PAGE_SIZE - 1) // SHOP_PAGE_SIZE)
    page = max(0, min(int(page), pages - 1))
    start = page * SHOP_PAGE_SIZE
    chunk = keys[start:start + SHOP_PAGE_SIZE]
    rows = []
    for key in chunk:
        meta = ITEMS[key]
        price = meta.get("price", "?")
        name = meta.get("name", key)
        rows.append([
            InlineKeyboardButton(
                text=f"🛒 {name} — {price}🪙",
                callback_data=f"shop:{uid}:buy:{key}",
            )
        ])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️ قبلی", callback_data=f"shop:{uid}:list:{page-1}"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton(text="بعدی ▶️", callback_data=f"shop:{uid}:list:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([
        InlineKeyboardButton(text="🎒 موجودی", callback_data=f"shop:{uid}:inv:0"),
        InlineKeyboardButton(text=f"🎁 صندوق ({BOX_PRICE})", callback_data=f"shop:{uid}:box"),
    ])
    rows.append([InlineKeyboardButton(
        text=f"صفحه {page+1}/{pages}",
        callback_data=f"shop:{uid}:list:{page}",
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _owner_ok(call: CallbackQuery, owner_id: int) -> bool:
    return int(call.from_user.id) == int(owner_id)


def _format_catalog() -> str:
    return _format_catalog_page(0)


def _format_catalog_page(page: int = 0) -> str:
    keys = list(ITEMS.keys())
    pages = max(1, (len(keys) + SHOP_PAGE_SIZE - 1) // SHOP_PAGE_SIZE)
    page = max(0, min(int(page), pages - 1))
    start = page * SHOP_PAGE_SIZE
    chunk = keys[start:start + SHOP_PAGE_SIZE]
    lines = [f"🛒 <b>بازار سیاه</b> — صفحه {page+1}/{pages}\n"]
    for key in chunk:
        meta = ITEMS[key]
        lines.append(
            f"• <b>{meta.get('name', key)}</b> — {meta.get('price', '?')} سکه"
            f" | AT{meta.get('attack', 0)} DF{meta.get('defense', 0)}"
        )
    lines.append(f"\n🎁 صندوق شانس: {BOX_PRICE} سکه")
    if page < pages - 1:
        lines.append("بیشتر می‌خوای؟ «بعدی» رو بزن.")
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
        "بازار سیاه بازه. چی می‌خوای ببری؟\n"
        "از دکمه‌ها بخر یا بنویس: خرید ... / تجهیز ... / موجودی",
        reply_markup=catalog_keyboard(message.from_user.id, 0),
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
            await panel_update(call, 
                "🛒 بازار سیاه — با بعدی بقیه جنس‌ها رو ببین",
                reply_markup=catalog_keyboard(call.from_user.id, 0),
            )
        elif action == "list":
            await call.answer()
            page = 0
            try:
                page = int(extra) if extra != "" else 0
            except ValueError:
                page = 0
            await panel_update(call, 
                _format_catalog_page(page),
                parse_mode="HTML",
                reply_markup=catalog_keyboard(call.from_user.id, page),
            )
        elif action == "inv":
            await call.answer()
            page = 0
            try:
                page = int(extra) if extra != "" else 0
            except ValueError:
                page = 0
            data = await equipment_service.dashboard(call.from_user.id)
            await panel_update(call, 
                _format_inventory(data),
                parse_mode="HTML",
                reply_markup=inventory_keyboard(call.from_user.id, data.get("inventory") or [], page),
            )
        elif action == "buy" and extra:
            await call.answer("خرید…")
            result = await equipment_service.buy(call.from_user.id, extra, 1)
            data = await equipment_service.dashboard(call.from_user.id)
            await panel_update(call, 
                f"✅ {result.get('item')} خریده شد (−{result.get('cost')}🪙)\nموجودی: {result.get('coins')}",
                reply_markup=inventory_keyboard(call.from_user.id, data.get("inventory") or []),
            )
        elif action == "eq" and extra:
            await call.answer("تجهیز…")
            result = await equipment_service.equip(call.from_user.id, extra)
            stats = result.get("stats") or {}
            data = await equipment_service.dashboard(call.from_user.id)
            await panel_update(call, 
                f"🔧 <b>{result.get('item')}</b> فعال شد\nATK {stats.get('attack', 0)} · DEF {stats.get('defense', 0)}",
                parse_mode="HTML",
                reply_markup=inventory_keyboard(call.from_user.id, data.get("inventory") or []),
            )
        elif action == "box":
            await call.answer("صندوق…")
            result = await equipment_service.open_box(call.from_user.id, str(uuid.uuid4()))
            await panel_update(call, 
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
            await panel_update(call, f"❌ {e}", reply_markup=catalog_keyboard(call.from_user.id, 0))
        except Exception:
            pass
