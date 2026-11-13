"""دستورات World Boss."""
from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from handlers.panel_ui import panel_update

from games.boss import service as boss_service

router = Router()


def boss_kb(uid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="ضربه به باس", callback_data=f"boss:{uid}:hit")],
        [InlineKeyboardButton(text="وضعیت / رتبه", callback_data=f"boss:{uid}:status")],
    ])


@router.message(Command("boss", "باس", "رئیس"))
@router.message(F.text.in_({"باس", "رئیس", "worldboss", "boss", "نبرد رئیس"}))
async def cmd_boss(message: Message):
    st = await boss_service.boss_status(message.from_user.id)
    b = st["boss"]
    lines = [
        f"باس: {b['name']}",
        f"جان: {int(b['hp']):,} / {int(b['max_hp']):,}",
        f"جایزه کل: {int(b['reward_pool']):,} سکه",
    ]
    if st["mine"]:
        lines.append(f"آسیب تو: {st['mine']['damage']:,} ({st['mine']['hits']} ضربه)")
    if st["top"]:
        lines.append("\nبرترین‌ها:")
        for r in st["top"][:5]:
            lines.append(f"{r['rank']}. {r['name']} — {r['damage']:,}")
    lines.append("\nبرای ضربه: باس بزن یا دکمه")
    await message.answer("\n".join(lines), reply_markup=boss_kb(message.from_user.id))


@router.message(Command("boss_hit", "باس_بزن"))
@router.message(F.text.in_({"باس بزن", "ضربه باس", "حمله باس"}))
async def cmd_boss_hit(message: Message):
    # تو گروه → باس گروهی؛ خصوصی → باس جهانی
    if message.chat.type in {"group", "supergroup"}:
        from games.world_pulse import service as pulse_service
        try:
            r = await pulse_service.attack_group_boss(message.chat.id, message.from_user.id)
            msg = (
                f"زدی به {r['boss_name']}: −{r['damage']:,}\n"
                f"جان باس: {r['boss_hp']:,}/{r['boss_max']:,}"
            )
            if r["defeated"]:
                msg += "\n\nباس گروه افتاد. جوایز واریز شد."
            await message.answer(msg)
        except ValueError as e:
            await message.answer(str(e))
        return
    try:
        r = await boss_service.attack_boss(message.from_user.id)
        msg = (
            f"زدی به {r['boss_name']}: −{r['damage']:,}\n"
            f"جان باس: {r['boss_hp']:,}/{r['boss_max']:,}\n"
            f"مجموع آسیب تو: {r['my_damage']:,}"
        )
        if r.get("player_hp"):
            msg += f"\n🩸 خون تو: {r['player_hp']['hp']}/{r['player_hp']['max_hp']} (−{r['player_hp'].get('lost', '?')})"
            if r['player_hp'].get('dead'):
                msg += "\n💀 مردی. ۱۰ دقیقه بعد زنده می‌شی."
        if r["defeated"]:
            msg += "\n\nباس افتاد. جوایز برای نفرات برتر واریز شد."
        await message.answer(msg, reply_markup=boss_kb(message.from_user.id))
    except ValueError as e:
        await message.answer(str(e))


@router.callback_query(F.data.startswith("boss:"))
async def boss_cb(call):
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
        await call.answer("این دکمه مال تو نیست.", show_alert=True)
        return
    action = parts[2]
    try:
        if action == "hit":
            r = await boss_service.attack_boss(owner)
            await call.answer(f"−{r['damage']}")
            msg = f"ضربه {r['damage']:,} · جان باس {r['boss_hp']:,}/{r['boss_max']:,}"
            if r.get("player_hp"):
                msg += f"\n🩸 خون تو: {r['player_hp']['hp']}/{r['player_hp']['max_hp']} (−{r['player_hp'].get('lost', '?')})"
            if r['player_hp'].get('dead'):
                msg += "\n💀 مردی. ۱۰ دقیقه بعد زنده می‌شی."
            if r["defeated"]:
                msg += "\nباس شکست."
            await panel_update(call, msg, reply_markup=boss_kb(owner))
        elif action == "status":
            await call.answer()
            st = await boss_service.boss_status(owner)
            b = st["boss"]
            await panel_update(call, 
                f"{b['name']}: {int(b['hp']):,}/{int(b['max_hp']):,}",
                reply_markup=boss_kb(owner),
            )
        else:
            await call.answer("نامعتبر", show_alert=True)
    except ValueError as e:
        await call.answer(str(e)[:180], show_alert=True)
