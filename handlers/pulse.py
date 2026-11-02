"""ایونت ساعتی جهان + باس گروهی."""
from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from handlers.panel_ui import panel_update

from games.world_pulse import service as pulse_service

router = Router()


@router.message(Command("pulse", "ایونت_جهان", "وضعیت_جهان"))
@router.message(F.text.in_({"ایونت جهان", "وضعیت جهان", "باف", "pulse", "جهان"}))
async def cmd_pulse(message: Message):
    await message.answer(await pulse_service.status_text())


@router.message(Command("group_boss", "باس_گروه"))
@router.message(F.text.in_({"باس گروه", "گروه باس", "باس گروهی"}))
async def cmd_group_boss(message: Message):
    if message.chat.type not in {"group", "supergroup"}:
        await message.answer("این دستور فقط تو گروه کار می‌کنه.\nتو گروه بنویس: باس گروه")
        return
    boss = await pulse_service.ensure_group_boss(message.chat.id, force_new=False)
    # اگر تقریبا مرده، یکی جدید
    if int(boss["hp"]) <= 0:
        boss = await pulse_service.ensure_group_boss(message.chat.id, force_new=True)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="⚔️ ضربه به باس گروه",
            callback_data=f"gboss:{message.from_user.id}:hit:{message.chat.id}",
        )]
    ])
    await message.answer(
        f"👹 باس گروه ظاهر شد: <b>{boss['name']}</b>\n"
        f"❤️ {int(boss['hp']):,} / {int(boss['max_hp']):,}\n"
        f"جایزه تقریبی: {int(boss['reward_pool']):,} سکه\n\n"
        f"همه اعضا بزنن: <code>باس بزن</code> یا دکمه زیر",
        parse_mode="HTML",
        reply_markup=kb,
    )


@router.message(Command("group_boss_hit"))
@router.message(F.text.in_({"باس گروه بزن", "ضربه باس گروه"}))
async def cmd_group_boss_hit(message: Message):
    if message.chat.type not in {"group", "supergroup"}:
        await message.answer("فقط تو گروه.")
        return
    try:
        r = await pulse_service.attack_group_boss(message.chat.id, message.from_user.id)
        msg = (
            f"⚔️ به {r['boss_name']} زدی: −{r['damage']:,}\n"
            f"❤️ {r['boss_hp']:,}/{r['boss_max']:,}"
        )
        if r["defeated"]:
            msg += "\n\n💀 باس گروه افتاد! جوایز بین برترین‌ها پخش شد."
        await message.answer(msg)
    except ValueError as e:
        await message.answer(str(e))


@router.callback_query(F.data.startswith("gboss:"))
async def gboss_cb(call):
    parts = (call.data or "").split(":")
    # gboss:uid:hit:chat_id
    if len(parts) < 4:
        await call.answer("نامعتبر", show_alert=True)
        return
    try:
        owner = int(parts[1])
        chat_id = int(parts[3])
    except ValueError:
        await call.answer("نامعتبر", show_alert=True)
        return
    if call.from_user.id != owner:
        # اجازه بده بقیه هم بزنن با دکمه خودشون - actually lock was wrong for group
        # For group boss, anyone can hit - ignore owner lock for hit, use call.from_user
        pass
    if parts[2] != "hit":
        await call.answer("نامعتبر", show_alert=True)
        return
    try:
        r = await pulse_service.attack_group_boss(chat_id, call.from_user.id)
        await call.answer(f"−{r['damage']}")
        msg = f"{call.from_user.first_name}: −{r['damage']:,} به {r['boss_name']}\n❤️ {r['boss_hp']:,}/{r['boss_max']:,}"
        if r["defeated"]:
            msg += "\n💀 باس گروه شکست."
        await panel_update(call, msg)
    except ValueError as e:
        await call.answer(str(e)[:180], show_alert=True)
