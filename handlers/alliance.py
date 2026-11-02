"""دستورهای اتحاد در خود ربات (قبول عضو و …)."""
from __future__ import annotations
import re

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from handlers.panel_ui import panel_update
from games.empire import alliances as alliance_service

router = Router()


def _requests_kb(uid: int, rows: list) -> InlineKeyboardMarkup:
    buttons = []
    for r in rows[:20]:
        rid = int(r["id"])
        name = r.get("requester_name") or str(r.get("requester_id"))
        buttons.append([
            InlineKeyboardButton(
                text=f"✅ قبول {name[:18]}",
                callback_data=f"allyreq:{uid}:yes:{rid}",
            ),
            InlineKeyboardButton(
                text="❌ رد",
                callback_data=f"allyreq:{uid}:no:{rid}",
            ),
        ])
    if not buttons:
        buttons = [[InlineKeyboardButton(text="خالی", callback_data=f"allyreq:{uid}:noop:0")]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("alliance_requests", "درخواست‌ها", "درخواستهای_اتحاد"))
@router.message(F.text.in_({
    "درخواست‌های اتحاد", "درخواستهای اتحاد", "درخواست اتحادها",
    "لیست درخواست اتحاد", "درخواست‌ها",
}))
async def cmd_alliance_requests(message: Message):
    try:
        rows = await alliance_service.incoming_requests(message.from_user.id)
    except ValueError as e:
        await message.answer(str(e))
        return
    if not rows:
        await message.answer(
            "درخواست معلقی نیست.\n"
            "فقط رهبر اتحاد درخواست‌ها رو می‌بینه.\n"
            "بازنیکن‌ها با «درخواست اتحاد [شماره]» درخواست می‌دن."
        )
        return
    lines = ["درخواست‌های عضویت:\n"]
    for r in rows:
        lines.append(
            f"#{r['id']} — {r.get('requester_name') or '؟'} "
            f"(آیدی {r['requester_id']})"
        )
    lines.append("\nدکمه بزن یا بنویس: قبول اتحاد ۱۲")
    await message.answer("\n".join(lines), reply_markup=_requests_kb(message.from_user.id, rows))


@router.message(Command("alliance_accept", "قبول_اتحاد"))
@router.message(F.text.regexp(r"^(?:قبول اتحاد|پذیرش اتحاد|/alliance_accept)\b", flags=re.I))
async def cmd_alliance_accept(message: Message):
    m = re.search(r"(\d{1,12})", message.text or "")
    if not m:
        await message.answer(
            "شماره درخواست رو بنویس.\n"
            "مثال: قبول اتحاد ۱۲\n"
            "لیست: درخواست‌های اتحاد"
        )
        return
    rid = int(m.group(1))
    try:
        r = await alliance_service.manage_request(message.from_user.id, rid, True)
        if r.get("status") == "accepted":
            await message.answer(
                f"عضو قبول شد.\nاتحاد: {r.get('alliance_name')}\nبازیکن: {r.get('player_id')}"
            )
        else:
            await message.answer("رد شد (شاید طرف جای دیگه عضو بوده).")
    except ValueError as e:
        await message.answer(str(e))


@router.message(Command("alliance_reject", "رد_اتحاد"))
@router.message(F.text.regexp(r"^(?:رد اتحاد|/alliance_reject)\b", flags=re.I))
async def cmd_alliance_reject(message: Message):
    m = re.search(r"(\d{1,12})", message.text or "")
    if not m:
        await message.answer("مثال: رد اتحاد ۱۲")
        return
    rid = int(m.group(1))
    try:
        r = await alliance_service.manage_request(message.from_user.id, rid, False)
        await message.answer(f"درخواست رد شد. ({r.get('alliance_name')})")
    except ValueError as e:
        await message.answer(str(e))


@router.message(Command("alliance_join", "درخواست_اتحاد"))
@router.message(F.text.regexp(r"^(?:درخواست اتحاد|عضویت اتحاد|/alliance_join)\b", flags=re.I))
async def cmd_alliance_join(message: Message):
    m = re.search(r"(\d{1,12})", message.text or "")
    if not m:
        await message.answer(
            "شماره اتحاد رو بنویس.\n"
            "مثال: درخواست اتحاد ۵\n"
            "لیست اتحادها از وب‌اپ یا «اتحادها»."
        )
        return
    aid = int(m.group(1))
    try:
        r = await alliance_service.request_to_join(message.from_user.id, aid)
        await message.answer(
            f"درخواست ثبت شد برای «{r.get('alliance_name')}».\n"
            f"شماره درخواست: {r.get('request_id')}\n"
            "صبر کن رهبر قبول کنه."
        )
    except ValueError as e:
        await message.answer(str(e))


@router.message(Command("alliances", "اتحادها"))
@router.message(F.text.in_({"اتحادها", "لیست اتحاد", "لیست اتحادها"}))
async def cmd_alliances_list(message: Message):
    try:
        rows = await alliance_service.list_alliances(limit=20, search="")
    except Exception as e:
        await message.answer(f"لیست نیومد: {e}")
        return
    if not rows:
        await message.answer("اتحادی نیست. با وب‌اپ یا دستور ساخت بساز.")
        return
    lines = ["اتحادها:\n"]
    for a in rows:
        lines.append(
            f"#{a.get('id')} — {a.get('name')} [{a.get('tag')}] "
            f"· اعضا {a.get('member_count', '?')}"
        )
    lines.append("\nبرای درخواست: درخواست اتحاد [شماره]")
    await message.answer("\n".join(lines))


@router.callback_query(F.data.startswith("allyreq:"))
async def allyreq_cb(call: CallbackQuery):
    parts = (call.data or "").split(":")
    # allyreq:uid:yes|no:request_id
    if len(parts) < 4:
        await call.answer("نامعتبر", show_alert=True)
        return
    try:
        owner = int(parts[1])
        rid = int(parts[3])
    except ValueError:
        await call.answer("نامعتبر", show_alert=True)
        return
    if call.from_user.id != owner:
        await call.answer("این پنل مال تو نیست.", show_alert=True)
        return
    action = parts[2]
    if action == "noop":
        await call.answer("خالی")
        return
    accept = action == "yes"
    try:
        r = await alliance_service.manage_request(call.from_user.id, rid, accept)
        await call.answer("انجام شد")
        if accept and r.get("status") == "accepted":
            text = f"✅ قبول شد — {r.get('alliance_name')} · بازیکن {r.get('player_id')}"
        elif accept:
            text = "درخواست رد منطقی شد (طرف جای دیگه عضو بود)."
        else:
            text = f"❌ رد شد — {r.get('alliance_name')}"
        # refresh list
        rows = await alliance_service.incoming_requests(call.from_user.id)
        if rows:
            await panel_update(call, text + "\n\nبقیه درخواست‌ها:", reply_markup=_requests_kb(owner, rows))
        else:
            await panel_update(call, text + "\n\nدیگه درخواست معلقی نیست.")
    except ValueError as e:
        await call.answer(str(e)[:180], show_alert=True)
