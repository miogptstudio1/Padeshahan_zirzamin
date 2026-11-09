"""زورخانه و ارتقای تجهیزات."""
from __future__ import annotations
import re

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from handlers.panel_ui import panel_update
from games.gym import service as gym_service
from games.empire import equipment as equipment_service
from games.empire.equipment_rules import ITEMS

router = Router()


def gym_kb(uid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💪 قدرت", callback_data=f"gym:{uid}:train:strength"),
            InlineKeyboardButton(text="⚡ سرعت", callback_data=f"gym:{uid}:train:speed"),
        ],
        [
            InlineKeyboardButton(text="❤️ سلامتی", callback_data=f"gym:{uid}:train:vitality"),
            InlineKeyboardButton(text="🛡️ استقامت", callback_data=f"gym:{uid}:train:stamina"),
        ],
        [InlineKeyboardButton(text="🔄 تازه‌سازی", callback_data=f"gym:{uid}:status")],
    ])


@router.message(Command("gym", "زورخانه", "تمرین"))
@router.message(F.text.in_({"زورخانه", "تمرین", "gym", "باشگاه"}))
async def cmd_gym(message: Message):
    text = await gym_service.status_text(message.from_user.id)
    await message.answer(text, reply_markup=gym_kb(message.from_user.id))


@router.message(Command("train", "تمرین_کن"))
@router.message(F.text.regexp(r"^(?:تمرین)\s+(قدرت|سرعت|سلامتی|استقامت|strength|speed|vitality|stamina)\s*$", flags=re.I))
async def cmd_train(message: Message):
    m = re.search(r"(قدرت|سرعت|سلامتی|استقامت|strength|speed|vitality|stamina)", message.text or "", re.I)
    if not m:
        await message.answer("مثال: تمرین قدرت")
        return
    try:
        r = await gym_service.train(message.from_user.id, m.group(1))
        nxt = f" · بعدی {r['next_cost']}" if r.get("next_cost") else " · سقف"
        await message.answer(
            f"{r['emoji']} {r['label']} → سطح {r['level']}\n"
            f"−{r['cost']} سکه · موجودی {r['balance']}{nxt}",
            reply_markup=gym_kb(message.from_user.id),
        )
    except ValueError as e:
        await message.answer(str(e))


@router.callback_query(F.data.startswith("gym:"))
async def gym_cb(call: CallbackQuery):
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
        await call.answer("این پنل مال تو نیست.", show_alert=True)
        return
    action = parts[2]
    if action == "status":
        await call.answer()
        text = await gym_service.status_text(call.from_user.id)
        await panel_update(call, text, reply_markup=gym_kb(owner))
        return
    if action == "train" and len(parts) >= 4:
        try:
            r = await gym_service.train(call.from_user.id, parts[3])
            await call.answer(f"{r['label']} {r['level']}")
            text = await gym_service.status_text(call.from_user.id)
            await panel_update(call, text, reply_markup=gym_kb(owner))
        except ValueError as e:
            await call.answer(str(e)[:180], show_alert=True)
        return
    await call.answer("نامعتبر", show_alert=True)


def _resolve_item_key(raw: str) -> str | None:
    raw = (raw or "").strip().lower()
    if raw in ITEMS:
        return raw
    for k, v in ITEMS.items():
        if v.get("name", "").lower() == raw or k.replace("_", " ") == raw:
            return k
    # partial name
    for k, v in ITEMS.items():
        if raw in v.get("name", "") or raw in k:
            return k
    return None


@router.message(Command("upgrade", "ارتقای_تجهیزات", "ارتقا_وسیله"))
@router.message(F.text.regexp(r"^(?:ارتقای تجهیزات|ارتقا تجهیزات|ارتقا وسیله|upgrade)\b", flags=re.I))
async def cmd_upgrade(message: Message):
    text = (message.text or "").strip()
    for pref in ("/upgrade", "ارتقای تجهیزات", "ارتقا تجهیزات", "ارتقا وسیله", "upgrade"):
        if text.lower().startswith(pref.lower()) or text.startswith(pref):
            text = text[len(pref):].strip()
            break
    if not text:
        data = await equipment_service.dashboard(message.from_user.id)
        inv = data.get("inventory") or []
        if not inv:
            await message.answer("وسیله‌ای نداری. اول از فروشگاه بخر.")
            return
        lines = ["🔧 ارتقای تجهیزات\nیکی رو انتخاب کن:\n"]
        rows = []
        uid = message.from_user.id
        for it in inv[:12]:
            key = it.get("key")
            lv = int(it.get("upgrade_level") or 0)
            lines.append(f"• {it.get('name')} +{lv}")
            rows.append([InlineKeyboardButton(
                text=f"⬆️ {it.get('name')} +{lv}",
                callback_data=f"equp:{uid}:{key}",
            )])
        await message.answer(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows) if rows else None,
        )
        return
    key = _resolve_item_key(text)
    if not key:
        await message.answer("وسیله پیدا نشد. مثال: ارتقا وسیله شمشیر چوبی")
        return
    try:
        r = await equipment_service.upgrade_item(message.from_user.id, key)
        nxt = f" · بعدی {r['next_cost']}" if r.get("next_cost") else " · سقف"
        await message.answer(
            f"⬆️ {r['name']} → +{r['level']}\n"
            f"ATK {r['attack']} · DEF {r['defense']}\n"
            f"−{r['cost']} سکه · موجودی {r['balance']}{nxt}"
        )
    except ValueError as e:
        await message.answer(str(e))


@router.callback_query(F.data.startswith("equp:"))
async def equp_cb(call: CallbackQuery):
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
        await call.answer("این پنل مال تو نیست.", show_alert=True)
        return
    key = parts[2]
    try:
        r = await equipment_service.upgrade_item(call.from_user.id, key)
        await call.answer(f"+{r['level']}")
        await panel_update(
            call,
            f"⬆️ {r['name']} → +{r['level']}\n"
            f"ATK {r['attack']} · DEF {r['defense']}\n"
            f"−{r['cost']} · موجودی {r['balance']}",
        )
    except ValueError as e:
        await call.answer(str(e)[:180], show_alert=True)
