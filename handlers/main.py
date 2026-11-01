from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from core.database import upsert_user, db
from core import staff as staff_service
from config import WEB_APP_URL
from membership import membership_status, join_keyboard
from games.reputation import service as rep_service
from games.empire import crime as crime_service
from games.empire import army_advanced
from handlers.guide import GUIDE_SHORT, GUIDE_FULL

router = Router()


async def menu(user_id: int | None = None, show_web_app: bool = False):
    rows = [
        [InlineKeyboardButton(text='🎭 مافیا', callback_data='menu:mafia'),
         InlineKeyboardButton(text='🃏 کودتا', callback_data='menu:coup')],
        [InlineKeyboardButton(text='🏙️ امپراتوری', callback_data='menu:empire'),
         InlineKeyboardButton(text='⚔️ ارتش', callback_data='menu:army')],
        [InlineKeyboardButton(text='🛒 فروشگاه', callback_data='menu:shop'),
         InlineKeyboardButton(text='🏪 بازار', callback_data='menu:market')],
        [InlineKeyboardButton(text='🕶️ خلاف', callback_data='menu:crime'),
         InlineKeyboardButton(text='👹 باس', callback_data='menu:boss')],
        [InlineKeyboardButton(text='🕵️ جاسوسی', callback_data='menu:spy'),
         InlineKeyboardButton(text='📋 مأموریت', callback_data='menu:missions')],
        [InlineKeyboardButton(text='🏠 خاندان', callback_data='menu:family'),
         InlineKeyboardButton(text='🎉 ایونت', callback_data='menu:event')],
        [InlineKeyboardButton(text='👤 پروفایل', callback_data='menu:profile'),
         InlineKeyboardButton(text='❓ راهنما', callback_data='menu:help')],
    ]
    if show_web_app and WEB_APP_URL.startswith("https://"):
        rows.insert(0, [InlineKeyboardButton(text='🌐 ورود به وب‌اپ', web_app=WebAppInfo(url=WEB_APP_URL))])
    if user_id is not None:
        try:
            profile = await staff_service.staff_profile(user_id)
            if profile.get("is_staff"):
                rows.append([InlineKeyboardButton(text='🛡️ پنل ادمین', callback_data='menu:admin')])
        except Exception:
            pass
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(CommandStart())
@router.message(Command('شروع'))
@router.message(F.text.in_({'شروع', 'استارت', 'start'}))
async def start(message: Message):
    joined, _, error = await membership_status(message.bot, message.from_user.id)
    if not joined:
        text = (
            "چک عضویت الان گیر کرد.\n"
            "یه کم صبر کن دوباره بزن. اگه ادامه داشت به ادمین بگو."
            if error else
            "اول برو تو هر دو کانال عضو شو، بعد «بررسی عضویت» رو بزن.\n"
            "بدون عضویت راهت نمی‌دم."
        )
        await message.answer(text, reply_markup=join_keyboard())
        return

    # ban check
    async with db().acquire() as conn:
        banned = await conn.fetchval(
            "SELECT is_banned FROM users WHERE telegram_id=$1", message.from_user.id
        )
    if banned:
        await message.answer("🚫 حساب شما مسدود شده است. با پشتیبانی تماس بگیر.")
        return

    await upsert_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name or str(message.from_user.id),
    )
    name = message.from_user.full_name or message.from_user.username or "رفیق"
    kb = await menu(message.from_user.id, message.chat.type == 'private')
    await message.answer(
        f"سلام {name}\n"
        f"ربات آماده‌ست.\n\n"
        f"مافیا و کودتا تو گروه، امپراتوری و فروشگاه هم همین‌جا.\n"
        f"اگه گیر کردی بزن: <code>راهنما</code>\n\n"
        f"وب‌اپ فقط از دکمه داخل ربات باز می‌شه، لینک مرورگر فایده نداره.",
        reply_markup=kb,
        parse_mode="HTML",
    )


@router.message(Command('profile', 'پروفایل'))
@router.message(F.text.in_({'پروفایل', 'پروفایل من', 'profile'}))
async def profile(message: Message):
    async with db().acquire() as conn:
        row = await conn.fetchrow('SELECT * FROM users WHERE telegram_id=$1', message.from_user.id)
    if not row:
        await message.answer('اول باید «شروع» یا /start رو بزنی 😊')
        return
    if row.get("is_banned"):
        await message.answer("🚫 حساب شما مسدود است.")
        return
    try:
        rep = await rep_service.get(message.from_user.id)
        rep_score, rep_label = rep["score"], rep["label"]
    except Exception:
        rep_score, rep_label = 0, "عادی"
    try:
        hp = await crime_service.hp_status(message.from_user.id)
        hp_txt = f"{hp['hp']}/{hp['max_hp']}"
    except Exception:
        hp_txt = "—"
    try:
        army_pow = (await army_advanced.total_army_power(message.from_user.id)).get("total", 0)
    except Exception:
        army_pow = 0
    win_rate = 0
    if row["games_played"]:
        win_rate = round(100 * row["wins"] / row["games_played"], 1)
    await message.answer(
        f"👤 <b>پروفایل تو</b>\n\n"
        f"🏷️ نام: {row['display_name']}\n"
        f"🪙 سکه: <b>{row['coins']:,}</b>\n"
        f"🎮 بازی‌ها: {row['games_played']}\n"
        f"🏆 بردها: {row['wins']} ({win_rate}%)\n"
        f"⭐ شهرت: {rep_label} ({rep_score})\n"
        f"❤️ جان: {hp_txt}\n"
        f"⚔️ قدرت ارتش: {army_pow}\n"
        f"🆔 آیدی: <code>{message.from_user.id}</code>",
        parse_mode="HTML",
    )


@router.message(Command('help', 'راهنما', 'کمک'))
@router.message(F.text.in_({'راهنما', 'کمک', 'هلپ', 'help'}))
async def help_command(message: Message):
    await message.answer(GUIDE_SHORT, parse_mode="HTML")


@router.message(Command('guide', 'راهنماکامل'))
@router.message(F.text.in_({'راهنما کامل', 'راهنمای کامل', 'guide', 'راهنماکامل'}))
async def help_full(message: Message):
    text = GUIDE_FULL
    if len(text) <= 4000:
        await message.answer(text, parse_mode="HTML")
        return
    chunk = ""
    for block in text.split("\n\n"):
        if len(chunk) + len(block) + 2 > 4000:
            await message.answer(chunk, parse_mode="HTML")
            chunk = block
        else:
            chunk = f"{chunk}\n\n{block}" if chunk else block
    if chunk:
        await message.answer(chunk, parse_mode="HTML")


@router.callback_query(F.data == "membership:check")
async def check_required_membership(call: CallbackQuery):
    joined, missing, error = await membership_status(call.bot, call.from_user.id)
    if error:
        await call.answer(
            "⚠️ بررسی عضویت ناموفق بود. ادمین باید دسترسی ربات به کانال‌ها رو چک کنه.",
            show_alert=True,
        )
        return
    if not joined:
        await call.answer("هنوز عضو هر دو کانال نشدی 😅", show_alert=True)
        if call.message:
            try:
                await call.message.edit_text(
                    "🔒 هنوز عضو هر دو کانال نشدی!\n\n"
                    "دکمه‌های زیر رو بزن، عضو شو و دوباره «بررسی عضویت» رو امتحان کن 👇",
                    reply_markup=join_keyboard(),
                )
            except Exception:
                await call.message.answer(
                    "🔒 هنوز عضو هر دو کانال نشدی!\n\n"
                    "دکمه‌های زیر رو بزن، عضو شو و دوباره «بررسی عضویت» رو امتحان کن 👇",
                    reply_markup=join_keyboard(),
                )
        return
    await upsert_user(
        call.from_user.id,
        call.from_user.username,
        call.from_user.full_name or str(call.from_user.id),
    )
    await call.answer("باشه، عضویت اوکیه")
    kb = await menu(call.from_user.id, call.message.chat.type == 'private' if call.message else True)
    if call.message:
        try:
            await call.message.edit_text(
                "✅ عضویت هر دو کانال تأیید شد!\n\n"
                "اوکیه، می‌تونی بازی کنی.\n"
                "یکی از بازی‌ها رو از منوی پایین انتخاب کن:",
                reply_markup=kb,
            )
        except Exception:
            await call.message.answer(
                "عضویت اوکیه، بزن بریم",
                reply_markup=kb,
            )


@router.callback_query(F.data == "menu:profile")
async def menu_profile(call: CallbackQuery):
    await call.answer()
    async with db().acquire() as conn:
        row = await conn.fetchrow('SELECT * FROM users WHERE telegram_id=$1', call.from_user.id)
    if not row:
        await call.message.answer('اول باید «شروع» رو بزنی')
        return
    try:
        rep = await rep_service.get(call.from_user.id)
        rep_score, rep_label = rep["score"], rep["label"]
    except Exception:
        rep_score, rep_label = 0, "عادی"
    try:
        hp = await crime_service.hp_status(call.from_user.id)
        hp_txt = f"{hp['hp']}/{hp['max_hp']}"
    except Exception:
        hp_txt = "—"
    try:
        army_pow = (await army_advanced.total_army_power(call.from_user.id)).get("total", 0)
    except Exception:
        army_pow = 0
    win_rate = round(100 * row["wins"] / row["games_played"], 1) if row["games_played"] else 0
    await call.message.answer(
        f"👤 <b>پروفایل تو</b>\n\n"
        f"🏷️ نام: {row['display_name']}\n"
        f"🪙 سکه: <b>{row['coins']:,}</b>\n"
        f"🎮 بازی‌ها: {row['games_played']}\n"
        f"🏆 بردها: {row['wins']} ({win_rate}%)\n"
        f"⭐ شهرت: {rep_label} ({rep_score})\n"
        f"❤️ جان: {hp_txt}\n"
        f"⚔️ قدرت ارتش: {army_pow}\n"
        f"🆔 آیدی: <code>{call.from_user.id}</code>",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "menu:admin")
async def menu_admin(call: CallbackQuery):
    await call.answer()
    profile = await staff_service.staff_profile(call.from_user.id)
    if not profile.get("is_staff"):
        await call.message.answer("⛔ دسترسی نداری.")
        return
    from handlers.admin import admin_menu_kb
    role = profile.get("role_label") or profile.get("role") or "—"
    await call.message.answer(
        f"🛡️ <b>پنل مدیریت</b>\n\n"
        f"👤 نقش: <b>{role}</b>\n"
        f"از دکمه‌ها یا دستورات متنی استفاده کن.",
        reply_markup=admin_menu_kb(call.from_user.id),
        parse_mode="HTML",
    )
