"""پنل ادمین و ستاد داخل ربات تلگرام."""
from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from core import staff as staff_service
from core.database import db
from config import ADMIN_IDS

router = Router()


def _parse_id(text: str | None) -> int | None:
    if not text:
        return None
    t = text.strip().lstrip("@")
    if t.isdigit():
        return int(t)
    return None


def admin_menu_kb(owner_id: int) -> InlineKeyboardMarkup:
    uid = int(owner_id)
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 آمار", callback_data=f"adm:{uid}:stats"),
            InlineKeyboardButton(text="👥 پرسنل", callback_data=f"adm:{uid}:staff"),
        ],
        [
            InlineKeyboardButton(text="📜 لاگ اخیر", callback_data=f"adm:{uid}:audit"),
            InlineKeyboardButton(text="❓ راهنمای ادمین", callback_data=f"adm:{uid}:help"),
        ],
    ])


async def _require_staff(message: Message) -> dict | None:
    profile = await staff_service.staff_profile(message.from_user.id)
    if not profile.get("is_staff"):
        await message.answer("⛔ این بخش فقط برای ادمین و پرسنل است.")
        return None
    return profile


@router.message(Command("admin", "ادمین", "مدیریت"))
@router.message(F.text.in_({"ادمین", "مدیریت", "پنل ادمین", "admin"}))
async def admin_panel(message: Message):
    profile = await _require_staff(message)
    if not profile:
        return
    role = profile.get("role_label") or profile.get("role") or "—"
    perms = profile.get("permissions") or []
    await message.answer(
        f"🛡️ <b>پنل مدیریت</b>\n\n"
        f"👤 نقش تو: <b>{role}</b>\n"
        f"🔑 دسترسی‌ها: {len(perms)} مورد\n\n"
        f"از دکمه‌های زیر استفاده کن یا دستورات متنی رو بفرست.",
        reply_markup=admin_menu_kb(message.from_user.id),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("adm:"))
async def admin_callbacks(call: CallbackQuery):
    parts = (call.data or "").split(":")
    if len(parts) < 3:
        await call.answer("دکمه قدیمی/نامعتبر — دوباره «ادمین» بزن", show_alert=True)
        return
    try:
        owner_id = int(parts[1])
    except ValueError:
        await call.answer("دکمه نامعتبر", show_alert=True)
        return
    if int(call.from_user.id) != owner_id:
        await call.answer("🚫 این پنل مال تو نیست.", show_alert=True)
        return
    profile = await staff_service.staff_profile(call.from_user.id)
    if not profile.get("is_staff"):
        await call.answer("دسترسی نداری", show_alert=True)
        return
    action = parts[2]
    await call.answer()

    if action == "stats":
        async with db().acquire() as conn:
            users = await conn.fetchval("SELECT COUNT(*) FROM users")
            banned = await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_banned")
            coins = await conn.fetchval("SELECT COALESCE(SUM(coins),0) FROM users")
            games = await conn.fetchval("SELECT COALESCE(SUM(games_played),0) FROM users")
            staff_n = await conn.fetchval("SELECT COUNT(*) FROM staff_members")
        text = (
            "📊 <b>آمار کلی ربات</b>\n\n"
            f"👥 کاربران: <b>{users:,}</b>\n"
            f"🚫 مسدود: <b>{banned:,}</b>\n"
            f"🪙 مجموع سکه‌ها: <b>{int(coins):,}</b>\n"
            f"🎮 مجموع بازی‌ها: <b>{int(games):,}</b>\n"
            f"🛡️ پرسنل ثبت‌شده: <b>{staff_n:,}</b>\n"
            f"⭐ ابرادمین (env): <b>{len(ADMIN_IDS)}</b>"
        )
        if call.message:
            await call.message.answer(text, parse_mode="HTML", reply_markup=admin_menu_kb(call.from_user.id))
        return

    if action == "staff":
        try:
            rows = await staff_service.list_staff()
        except ValueError as e:
            await call.message.answer(str(e))
            return
        if not rows:
            await call.message.answer("هنوز پرسنلی ثبت نشده.")
            return
        lines = ["👥 <b>لیست پرسنل</b>\n"]
        for r in rows[:40]:
            uname = f"@{r['username']}" if r.get("username") else "—"
            lines.append(
                f"• <b>{r.get('role_label') or r['role']}</b> — {r.get('display_name') or '—'} "
                f"({uname}) <code>{r['telegram_id']}</code>"
            )
        await call.message.answer("\n".join(lines), parse_mode="HTML", reply_markup=admin_menu_kb(call.from_user.id))
        return

    if action == "audit":
        try:
            rows = await staff_service.recent_audit(call.from_user.id, 15)
        except ValueError as e:
            await call.message.answer(str(e))
            return
        if not rows:
            await call.message.answer("لاگی نیست.")
            return
        lines = ["📜 <b>لاگ اخیر</b>\n"]
        for r in rows:
            tgt = r["target_id"] or "—"
            lines.append(
                f"#{r['id']} <code>{r['action']}</code> توسط {r['actor_name'] or r['actor_id']}\n"
                f"   هدف: <code>{tgt}</code> — {r['detail'] or '—'}"
            )
        await call.message.answer("\n".join(lines), parse_mode="HTML", reply_markup=admin_menu_kb(call.from_user.id))
        return

    if action == "help":
        await call.message.answer(_admin_help_text(), parse_mode="HTML", reply_markup=admin_menu_kb(call.from_user.id))
        return


def _admin_help_text() -> str:
    return (
        "❓ <b>راهنمای دستورات ادمین</b>\n\n"
        "🔹 <b>پنل</b>\n"
        "• ادمین / /admin — باز کردن پنل\n\n"
        "🔹 <b>بازیکن</b>\n"
        "• جستجو نام یا آیدی\n"
        "  مثال: <code>جستجو 123456</code> یا <code>/lookup ali</code>\n"
        "• بن آیدی\n"
        "  مثال: <code>بن 123456</code>\n"
        "• آنبن آیدی\n"
        "  مثال: <code>آنبن 123456</code>\n\n"
        "🔹 <b>سکه</b>\n"
        "• سکه +مقدار آیدی  (افزودن)\n"
        "• سکه -مقدار آیدی  (کسر)\n"
        "• سکه تنظیم مقدار آیدی\n"
        "  مثال: <code>سکه +1000 123456</code>\n"
        "  مثال: <code>سکه تنظیم 5000 123456</code>\n\n"
        "🔹 <b>مقام</b> (نیاز به manage_staff)\n"
        "• مقام moderator|support|economy|operator آیدی\n"
        "  مثال: <code>مقام support 123456</code>\n"
        "• حذف‌مقام آیدی\n\n"
        "🔹 <b>پیام همگانی</b> (فقط ابرادمین)\n"
        "• همگانی متن پیام...\n\n"
        "نقش‌ها: ناظر، پشتیبانی، مدیر اقتصاد، اپراتور، ابرادمین"
    )


@router.message(Command("lookup", "جستجو", "player"))
@router.message(F.text.regexp(r"^(?:جستجو|/lookup|/player)\s+(.+)$"))
async def cmd_lookup(message: Message):
    profile = await _require_staff(message)
    if not profile:
        return
    parts = (message.text or "").split(maxsplit=1)
    query = parts[1].strip() if len(parts) > 1 else ""
    if not query:
        await message.answer("مثال: <code>جستجو 123456</code> یا <code>جستجو نام</code>", parse_mode="HTML")
        return
    try:
        rows = await staff_service.lookup_player(message.from_user.id, query)
    except ValueError as e:
        await message.answer(f"❌ {e}")
        return
    if not rows:
        await message.answer("چیزی پیدا نشد.")
        return
    lines = ["🔎 <b>نتیجه جستجو</b>\n"]
    for r in rows[:15]:
        ban = "🚫 بن" if r["is_banned"] else "✅ فعال"
        uname = f"@{r['username']}" if r.get("username") else "—"
        lines.append(
            f"• <b>{r['display_name'] or '—'}</b> ({uname})\n"
            f"  ID: <code>{r['telegram_id']}</code> | 🪙 {r['coins']:,} | "
            f"🎮 {r['games_played']} | 🏆 {r['wins']} | {ban}"
        )
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("ban", "بن"))
@router.message(F.text.regexp(r"^(?:بن|/ban)\s+(\d+)$"))
async def cmd_ban(message: Message):
    if not await _require_staff(message):
        return
    tid = _parse_id((message.text or "").split(maxsplit=1)[-1] if message.text else "")
    if not tid:
        await message.answer("مثال: <code>بن 123456789</code>", parse_mode="HTML")
        return
    try:
        await staff_service.ban_user(message.from_user.id, tid, True)
        await message.answer(f"🚫 کاربر <code>{tid}</code> مسدود شد.", parse_mode="HTML")
        try:
            await message.bot.send_message(tid, "🚫 حساب شما در پادشاهان زیرزمین مسدود شد.")
        except Exception:
            pass
    except ValueError as e:
        await message.answer(f"❌ {e}")


@router.message(Command("unban", "آنبن", "انبن"))
@router.message(F.text.regexp(r"^(?:آنبن|انبن|/unban)\s+(\d+)$"))
async def cmd_unban(message: Message):
    if not await _require_staff(message):
        return
    tid = _parse_id((message.text or "").split(maxsplit=1)[-1] if message.text else "")
    if not tid:
        await message.answer("مثال: <code>آنبن 123456789</code>", parse_mode="HTML")
        return
    try:
        await staff_service.ban_user(message.from_user.id, tid, False)
        await message.answer(f"✅ مسدودیت کاربر <code>{tid}</code> برداشته شد.", parse_mode="HTML")
        try:
            await message.bot.send_message(tid, "✅ مسدودیت حساب شما برداشته شد. خوش برگشتی!")
        except Exception:
            pass
    except ValueError as e:
        await message.answer(f"❌ {e}")


@router.message(Command("coins", "سکه"))
@router.message(F.text.regexp(r"^(?:سکه|/coins)\s+(.+)$"))
async def cmd_coins(message: Message):
    if not await _require_staff(message):
        return
    # formats:
    # سکه +1000 123
    # سکه -500 123
    # سکه تنظیم 5000 123
    # /coins add 1000 123
    raw = (message.text or "").split(maxsplit=1)
    if len(raw) < 2:
        await message.answer(
            "مثال‌ها:\n"
            "• <code>سکه +1000 123456</code>\n"
            "• <code>سکه -200 123456</code>\n"
            "• <code>سکه تنظیم 5000 123456</code>",
            parse_mode="HTML",
        )
        return
    body = raw[1].strip()
    mode = "add"
    amount = None
    target = None
    parts = body.split()
    try:
        if parts[0] in {"تنظیم", "set"} and len(parts) >= 3:
            mode = "set"
            amount = int(parts[1].replace(",", ""))
            target = int(parts[2])
        elif parts[0] in {"add", "set"} and len(parts) >= 3:
            mode = "set" if parts[0] == "set" else "add"
            amount = int(parts[1].replace(",", ""))
            target = int(parts[2])
        elif len(parts) >= 2:
            amt_s = parts[0].replace(",", "")
            amount = int(amt_s)
            target = int(parts[1])
        else:
            raise ValueError("فرمت نادرست")
    except Exception:
        await message.answer("❌ فرمت نادرست. مثال: <code>سکه +1000 123456</code>", parse_mode="HTML")
        return
    try:
        result = await staff_service.adjust_coins(message.from_user.id, target, amount, mode)
        sign = "تنظیم به" if mode == "set" else ("افزودن" if amount >= 0 else "کسر")
        await message.answer(
            f"🪙 {sign} برای <code>{target}</code>\n"
            f"موجودی جدید: <b>{result['coins']:,}</b> سکه",
            parse_mode="HTML",
        )
        try:
            await message.bot.send_message(
                target,
                f"🪙 موجودی سکه‌ات توسط پشتیبانی به‌روز شد.\nموجودی فعلی: {result['coins']:,}",
            )
        except Exception:
            pass
    except ValueError as e:
        await message.answer(f"❌ {e}")


@router.message(Command("grant", "مقام"))
@router.message(F.text.regexp(r"^(?:مقام|/grant)\s+(\w+)\s+(\d+)$"))
async def cmd_grant(message: Message):
    if not await _require_staff(message):
        return
    parts = (message.text or "").split()
    if len(parts) < 3:
        await message.answer(
            "مثال: <code>مقام support 123456</code>\n"
            "نقش‌ها: moderator, support, economy, operator",
            parse_mode="HTML",
        )
        return
    role = parts[1].strip().lower()
    tid = _parse_id(parts[2])
    if not tid:
        await message.answer("آیدی عددی لازم است.")
        return
    try:
        profile = await staff_service.grant_role(message.from_user.id, tid, role, note="via bot")
        await message.answer(
            f"✅ مقام <b>{profile.get('role_label') or role}</b> به <code>{tid}</code> داده شد.",
            parse_mode="HTML",
        )
        try:
            await message.bot.send_message(
                tid,
                f"🛡️ به تو مقام «{profile.get('role_label') or role}» در پادشاهان زیرزمین داده شد.\n"
                f"با دستور «ادمین» پنل رو باز کن.",
            )
        except Exception:
            pass
    except ValueError as e:
        await message.answer(f"❌ {e}")


@router.message(Command("revoke", "حذف‌مقام", "حذفمقام"))
@router.message(F.text.regexp(r"^(?:حذف‌مقام|حذفمقام|/revoke)\s+(\d+)$"))
async def cmd_revoke(message: Message):
    if not await _require_staff(message):
        return
    tid = _parse_id((message.text or "").split(maxsplit=1)[-1] if message.text else "")
    if not tid:
        await message.answer("مثال: <code>حذف‌مقام 123456</code>", parse_mode="HTML")
        return
    try:
        await staff_service.revoke_role(message.from_user.id, tid)
        await message.answer(f"✅ مقام کاربر <code>{tid}</code> حذف شد.", parse_mode="HTML")
    except ValueError as e:
        await message.answer(f"❌ {e}")


@router.message(Command("broadcast", "همگانی"))
@router.message(F.text.regexp(r"^(?:همگانی|/broadcast)\s+(.+)$"))
async def cmd_broadcast(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ پیام همگانی فقط برای ابرادمین است.")
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("مثال: <code>همگانی سلام به همه بازیکن‌ها!</code>", parse_mode="HTML")
        return
    text = parts[1].strip()
    async with db().acquire() as conn:
        rows = await conn.fetch("SELECT telegram_id FROM users WHERE is_banned = FALSE")
    ok = 0
    fail = 0
    status = await message.answer(f"📢 در حال ارسال به {len(rows)} کاربر...")
    for r in rows:
        try:
            await message.bot.send_message(int(r["telegram_id"]), f"📢 پیام مدیریت:\n\n{text}")
            ok += 1
        except Exception:
            fail += 1
    await status.edit_text(f"✅ ارسال شد.\nموفق: {ok:,}\nناموفق: {fail:,}")


@router.message(Command("stats", "آمار"))
@router.message(F.text.in_({"آمار", "stats"}))
async def cmd_stats(message: Message):
    if not await _require_staff(message):
        return
    async with db().acquire() as conn:
        users = await conn.fetchval("SELECT COUNT(*) FROM users")
        banned = await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_banned")
        coins = await conn.fetchval("SELECT COALESCE(SUM(coins),0) FROM users")
        games = await conn.fetchval("SELECT COALESCE(SUM(games_played),0) FROM users")
    await message.answer(
        "📊 <b>آمار ربات</b>\n\n"
        f"👥 کاربران: <b>{users:,}</b>\n"
        f"🚫 مسدود: <b>{banned:,}</b>\n"
        f"🪙 مجموع سکه: <b>{int(coins):,}</b>\n"
        f"🎮 مجموع بازی: <b>{int(games):,}</b>",
        parse_mode="HTML",
        reply_markup=admin_menu_kb(message.from_user.id),
    )
