"""دستورات خاندان / خانواده — فارسی و انگلیسی."""
from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from games.family import service as family_service

router = Router()


@router.message(Command("family", "خاندان", "خانواده"))
@router.message(F.text.in_({"خاندان", "خانواده", "فمیلی", "family"}))
async def cmd_family(message: Message):
    mem = await family_service.get_membership(message.from_user.id)
    if not mem:
        await message.answer(
            "🏠 هنوز عضو خاندان نیستی.\n\n"
            f"• ساخت: <code>ساخت خاندان نام | تگ</code> (هزینه {family_service.CREATE_COST} سکه)\n"
            "• پذیرش دعوت: <code>قبول خاندان</code>\n"
            "• برترین‌ها: <code>رتبه خاندان</code>",
            parse_mode="HTML",
        )
        return
    info = await family_service.family_info(int(mem["id"]))
    lines = [
        f"🏠 <b>{info['name']}</b> [{info['tag']}]",
        f"📜 {info.get('motto') or '—'}",
        f"⭐ سطح {info['level']} · 🪙 خزانه {int(info['treasury']):,}",
        f"👥 اعضا: {info['member_count']}/{family_service.MAX_MEMBERS}",
        f"نقش تو: <b>{family_service.ROLE_LABELS.get(mem['member_role'], mem['member_role'])}</b>\n",
        "<b>اعضا:</b>",
    ]
    for m in info["members"][:15]:
        lines.append(f"• {m['role_label']} — {m['name']} <code>{m['telegram_id']}</code>")
    lines.append(
        "\nدستورات: دعوت خاندان · قبول خاندان · خروج خاندان · واریز خاندان [مبلغ] · اخراج خاندان [آیدی]"
    )
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("family_create", "ساخت_خاندان"))
@router.message(F.text.regexp(r"^(?:ساخت خاندان|ساخت خانواده|/family_create)\s+(.+)$"))
async def cmd_family_create(message: Message):
    raw = (message.text or "").split(maxsplit=2)
    # "ساخت خاندان نام | تگ" or "/family_create Name|TAG"
    body = (message.text or "")
    for prefix in ("ساخت خاندان", "ساخت خانواده", "/family_create"):
        if body.startswith(prefix):
            body = body[len(prefix):].strip()
            break
    if "|" in body:
        name, tag = [x.strip() for x in body.split("|", 1)]
    else:
        parts = body.split()
        if len(parts) < 2:
            await message.answer(
                "مثال: <code>ساخت خاندان شیرها | LION</code>",
                parse_mode="HTML",
            )
            return
        name, tag = parts[0], parts[1]
    try:
        info = await family_service.create_family(message.from_user.id, name, tag)
        await message.answer(
            f"✅ خاندان <b>{info['name']}</b> [{info['tag']}] ساخته شد!\n"
            f"هزینه: {family_service.CREATE_COST} سکه",
            parse_mode="HTML",
        )
    except ValueError as e:
        await message.answer(f"❌ {e}")


@router.message(Command("family_invite", "دعوت_خاندان"))
@router.message(F.text.regexp(r"^(?:دعوت خاندان|/family_invite)\s+(\d+)$"))
async def cmd_family_invite(message: Message):
    parts = (message.text or "").split()
    tid = None
    for p in parts:
        if p.isdigit():
            tid = int(p)
            break
    if message.reply_to_message and message.reply_to_message.from_user:
        tid = message.reply_to_message.from_user.id
    if not tid:
        await message.answer("ریپلای روی بازیکن یا بنویس: <code>دعوت خاندان 123456</code>", parse_mode="HTML")
        return
    try:
        await family_service.invite(message.from_user.id, tid)
        await message.answer(f"✅ دعوت برای <code>{tid}</code> ارسال شد.\nطرف باید بزنه: قبول خاندان", parse_mode="HTML")
        try:
            mem = await family_service.get_membership(message.from_user.id)
            await message.bot.send_message(
                tid,
                f"🏠 دعوت خاندان «{mem['name'] if mem else ''}» برات اومد.\nبرای عضویت بنویس: قبول خاندان",
            )
        except Exception:
            pass
    except ValueError as e:
        await message.answer(f"❌ {e}")


@router.message(Command("family_accept", "قبول_خاندان"))
@router.message(F.text.in_({"قبول خاندان", "پذیرش خاندان", "قبول خانواده"}))
async def cmd_family_accept(message: Message):
    try:
        info = await family_service.accept_invite(message.from_user.id)
        await message.answer(f"✅ به خاندان <b>{info['name']}</b> [{info['tag']}] پیوستی!", parse_mode="HTML")
    except ValueError as e:
        await message.answer(f"❌ {e}")


@router.message(Command("family_leave", "خروج_خاندان"))
@router.message(F.text.in_({"خروج خاندان", "ترک خاندان", "خروج خانواده"}))
async def cmd_family_leave(message: Message):
    try:
        await family_service.leave(message.from_user.id)
        await message.answer("خروج از خاندان انجام شد.")
    except ValueError as e:
        await message.answer(f"❌ {e}")


@router.message(Command("family_kick", "اخراج_خاندان"))
@router.message(F.text.regexp(r"^(?:اخراج خاندان|/family_kick)\s+(\d+)$"))
async def cmd_family_kick(message: Message):
    parts = (message.text or "").split()
    tid = next((int(p) for p in parts if p.isdigit()), None)
    if not tid:
        await message.answer("مثال: <code>اخراج خاندان 123456</code>", parse_mode="HTML")
        return
    try:
        await family_service.kick(message.from_user.id, tid)
        await message.answer(f"✅ کاربر <code>{tid}</code> اخراج شد.", parse_mode="HTML")
    except ValueError as e:
        await message.answer(f"❌ {e}")


@router.message(Command("family_deposit", "واریز_خاندان"))
@router.message(F.text.regexp(r"^(?:واریز خاندان|/family_deposit)\s+(\d+)$"))
async def cmd_family_deposit(message: Message):
    parts = (message.text or "").split()
    amount = next((int(p) for p in parts if p.isdigit()), None)
    if not amount:
        await message.answer("مثال: <code>واریز خاندان 100</code>", parse_mode="HTML")
        return
    try:
        r = await family_service.deposit(message.from_user.id, amount)
        await message.answer(f"✅ {r['paid']:,} سکه به خزانه واریز شد.\nخزانه: {r['treasury']:,}")
    except ValueError as e:
        await message.answer(f"❌ {e}")


@router.message(Command("family_top", "رتبه_خاندان"))
@router.message(F.text.in_({"رتبه خاندان", "برترین خاندان", "خاندان برتر"}))
async def cmd_family_top(message: Message):
    rows = await family_service.top_families(10)
    if not rows:
        await message.answer("هنوز خاندانی ساخته نشده.")
        return
    lines = ["🏠 <b>برترین خاندان‌ها</b>\n"]
    for i, r in enumerate(rows, 1):
        lines.append(
            f"{i}. {r['name']} [{r['tag']}] — سطح {r['level']} · "
            f"{int(r['members'])} عضو · خزانه {int(r['treasury']):,}"
        )
    await message.answer("\n".join(lines), parse_mode="HTML")
