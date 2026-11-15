"""ارتش پیشرفته و فرماندهان — دستورات فارسی."""
from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from handlers.panel_ui import panel_update

from games.empire import army_advanced as army_svc
from games.empire.army_rules import UNITS, COMMANDERS, UNIT_ALIASES, COMMANDER_ALIASES

router = Router()


async def _status_text(uid: int) -> str:
    p = await army_svc.total_army_power(uid)
    lines = [
        f"⚔️ قدرت کل: <b>{p['total']}</b>",
        f"🪖 سرباز عادی: {p['soldiers']} (قدرت {p['soldier_power']})",
        f"🧩 واحد تخصصی: قدرت {p['unit_power']}",
    ]
    for u in (p.get("units") or []):
        lines.append(f"  • {u['name']} ×{u['quantity']} (قدرت {u['power']})")
    if not (p.get("units") or []):
        lines.append("  • هنوز واحد تخصصی نداری")
    lines.append(f"⭐ فرمانده: قدرت {p['commander_power']}")
    for c in (p.get("commanders") or []):
        lines.append(f"  • {c['name']} (+{c['bonus']})")
    if p.get("gym_power"):
        lines.append(f"🏋️ زورخانه: +{p['gym_power']}")
    return "\n".join(lines)


def army_keyboard(uid: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="📊 وضعیت ارتش", callback_data=f"advarmy:{uid}:status")],
        [InlineKeyboardButton(text="📜 فهرست واحد/فرمانده", callback_data=f"advarmy:{uid}:catalog")],
    ]
    for key, meta in list(UNITS.items())[:5]:
        rows.append([
            InlineKeyboardButton(
                text=f"🪖 +1 {meta['name']} ({meta['cost']}🪙)",
                callback_data=f"advarmy:{uid}:hireunit:{key}",
            )
        ])
    for key, meta in list(COMMANDERS.items())[:4]:
        rows.append([
            InlineKeyboardButton(
                text=f"⭐ {meta['name']} ({meta['cost']}🪙)",
                callback_data=f"advarmy:{uid}:hirecmd:{key}",
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("advanced_army", "ارتش_پیشرفته"))
@router.message(F.text.in_({"ارتش پیشرفته", "ارتش تخصصی", "فرماندهان", "واحد نظامی"}))
async def army_menu(message: Message):
    try:
        text = await _status_text(message.from_user.id)
    except Exception as e:
        await message.answer(f"❌ {e}")
        return
    await message.answer(
        text + "\n\nاز دکمه‌ها واحد و فرمانده بگیر.",
        parse_mode="HTML",
        reply_markup=army_keyboard(message.from_user.id),
    )


@router.message(Command("hire_unit", "استخدام"))
@router.message(F.text.regexp(r"^(?:استخدام|/hire_unit)\s+(.+)$"))
async def hire_unit(message: Message):
    text = message.text or ""
    for pref in ("/hire_unit", "استخدام"):
        if text.startswith(pref):
            text = text[len(pref):].strip()
            break
    parts = text.split()
    unit = parts[0] if parts else ""
    count = 1
    if len(parts) >= 2 and parts[-1].isdigit():
        count = int(parts[-1])
        unit = " ".join(parts[:-1]) or parts[0]
    try:
        r = await army_svc.recruit_unit(message.from_user.id, unit, count)
        await message.answer(
            f"✅ {r['unit']} ×{count} استخدام شد (−{r['cost']}🪙)\n"
            f"تعداد کل این واحد: {r['quantity']} · موجودی: {r['balance']}"
        )
    except ValueError as e:
        await message.answer(f"❌ {e}")


@router.message(Command("hire_commander", "فرمانده"))
@router.message(F.text.regexp(r"^(?:فرمانده|/hire_commander)\s+(.+)$"))
async def hire_cmd(message: Message):
    text = message.text or ""
    for pref in ("/hire_commander", "فرمانده"):
        if text.startswith(pref):
            text = text[len(pref):].strip()
            break
    try:
        r = await army_svc.hire_commander(message.from_user.id, text)
        await message.answer(
            f"⭐ فرمانده <b>{r['commander']}</b> استخدام شد!\n"
            f"{r['desc']}\n−{r['cost']}🪙 · موجودی {r['balance']}",
            parse_mode="HTML",
        )
    except ValueError as e:
        await message.answer(f"❌ {e}")


@router.callback_query(F.data.startswith("advarmy:"))
async def army_cb(call):
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
    extra = parts[3] if len(parts) > 3 else ""
    try:
        if action == "status":
            await call.answer()
            await panel_update(call, await _status_text(owner), parse_mode="HTML", reply_markup=army_keyboard(owner))
        elif action == "catalog":
            await call.answer()
            await panel_update(call, army_svc.catalog_text(), parse_mode="HTML", reply_markup=army_keyboard(owner))
        elif action == "hireunit" and extra:
            r = await army_svc.recruit_unit(owner, extra, 1)
            await call.answer(f"{r['unit']} ×{r['quantity']}")
            body = (
                f"✅ {r['unit']} استخدام شد (الان ×{r['quantity']})\n"
                f"−{r['cost']}🪙 · موجودی {r['balance']}\n\n"
                + await _status_text(owner)
            )
            await panel_update(call, body, parse_mode="HTML", reply_markup=army_keyboard(owner))
        elif action == "hirecmd" and extra:
            r = await army_svc.hire_commander(owner, extra)
            await call.answer("فرمانده آمد")
            body = (
                f"⭐ {r['commander']} (+{r['bonus']}) (−{r['cost']})\n\n"
                + await _status_text(owner)
            )
            await panel_update(call, body, parse_mode="HTML", reply_markup=army_keyboard(owner))
        else:
            await call.answer("اقدام نامعتبر", show_alert=True)
    except ValueError as e:
        await call.answer(str(e)[:180], show_alert=True)
    except Exception as e:
        await call.answer(str(e)[:100], show_alert=True)
