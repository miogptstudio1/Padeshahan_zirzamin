"""دستورات ایونت — فارسی و انگلیسی."""
from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from games.events import service as event_service

router = Router()


def _fmt_event(ev: dict) -> str:
    ends = ev.get("ends_at")
    ends_s = ends.strftime("%Y-%m-%d %H:%M UTC") if hasattr(ends, "strftime") else str(ends)
    return (
        f"{ev['title']}\n"
        f"{ev.get('description') or ''}\n"
        f"⏱ تا: {ends_s}\n"
        f"🎁 جایزه نفر اول: {int(ev.get('reward_coins') or 0):,} سکه"
    )


@router.message(Command("event", "events", "ایونت", "رویداد"))
@router.message(F.text.in_({"ایونت", "رویداد", "ایونت‌ها", "رویدادها", "event", "events"}))
async def cmd_event(message: Message):
    try:
        await event_service.settle_ended_events()
        ev = await event_service.active_event()
        if not ev:
            await message.answer("الان ایونت فعالی نیست. به‌زودی یکی شروع می‌شه 🎉")
            return
        mine = await event_service.my_score(message.from_user.id)
        board = await event_service.leaderboard(int(ev["id"]), 5)
        lines = ["🎉 <b>ایونت فعال</b>\n", _fmt_event(ev), ""]
        if mine:
            lines.append(
                f"📊 امتیاز تو: <b>{mine['points']:,}</b>"
                + (f" — رتبه {mine['rank']}" if mine.get("rank") else "")
            )
        lines.append("\n🏆 برترین‌ها:")
        if not board:
            lines.append("هنوز کسی امتیاز نگرفته.")
        else:
            for r in board:
                lines.append(f"{r['rank']}. {r['name'] or r['telegram_id']} — {r['points']:,}")
        lines.append("\nدستورات: <code>ایونت</code> · <code>رتبه ایونت</code> · <code>جایزه ایونت</code>")
        await message.answer("\n".join(lines), parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ {e}")


@router.message(Command("event_top", "رتبه_ایونت"))
@router.message(F.text.in_({"رتبه ایونت", "لیدربورد ایونت", "برترین ایونت"}))
async def cmd_event_top(message: Message):
    board = await event_service.leaderboard(limit=10)
    if not board:
        await message.answer("رتبه‌بندی خالی است یا ایونتی فعال نیست.")
        return
    lines = ["🏆 <b>رتبه‌بندی ایونت</b>\n"]
    for r in board:
        lines.append(f"{r['rank']}. {r['name'] or r['telegram_id']} — {r['points']:,} امتیاز")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("event_claim", "جایزه_ایونت"))
@router.message(F.text.in_({"جایزه ایونت", "دریافت جایزه ایونت"}))
async def cmd_event_claim(message: Message):
    paid = await event_service.settle_ended_events()
    mine = [p for p in paid if p["telegram_id"] == message.from_user.id]
    if not mine:
        await message.answer(
            "جایزه جدیدی برای تو ثبت نشد.\n"
            "جوایز بعد از پایان ایونت برای ۳ نفر اول خودکار واریز می‌شه."
        )
        return
    lines = ["🎁 جوایز واریزشده:"]
    for p in mine:
        lines.append(f"• {p['title']} — رتبه {p['rank']} → +{p['coins']:,} سکه")
    await message.answer("\n".join(lines))
