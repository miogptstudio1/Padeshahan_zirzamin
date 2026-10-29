from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from core.database import upsert_user, db
from core import staff as staff_service
from config import WEB_APP_URL
from membership import membership_status, join_keyboard
from handlers.guide import GUIDE_SHORT, GUIDE_FULL

router = Router()


async def menu(user_id: int | None = None, show_web_app: bool = False):
    rows = [
        [InlineKeyboardButton(text='🎭 مافیای کلاسیک', callback_data='menu:mafia')],
        [
            InlineKeyboardButton(text='🏙️ امپراتوری', callback_data='menu:empire'),
            InlineKeyboardButton(text='🃏 کودتا', callback_data='menu:coup'),
        ],
        [
            InlineKeyboardButton(text='🛒 فروشگاه', callback_data='menu:shop'),
            InlineKeyboardButton(text='👤 پروفایل', callback_data='menu:profile'),
        ],
        [
            InlineKeyboardButton(text='📜 قوانین', callback_data='menu:rules'),
            InlineKeyboardButton(text='❓ راهنما', callback_data='menu:help'),
        ],
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
            "⚠️ اوه! فعلاً نمی‌تونم عضویتت رو چک کنم.\n\n"
            "یه کم صبر کن و دوباره روی «بررسی عضویت» بزن 🔄\n"
            "اگه مشکل ادامه داشت، به ادمین بگو ربات رو توی کانال‌ها ادمین کنه 🛠️"
            if error else
            "👑 به پادشاهان زیرزمین خوش اومدی!\n\n"
            "برای ورود به دنیای بازی‌ها، باید عضو هر دو کانال باشی:\n\n"
            "1️⃣ اول روی دکمه «📢 عضویت در کانال اول» بزن و عضو شو\n"
            "2️⃣ بعد روی دکمه «🌿 عضویت در کانال دوم» بزن و عضو شو\n"
            "3️⃣ وقتی عضو شدی، روی «✅ بررسی عضویت» بزن تا وارد شی 🚀\n\n"
            "منتظرتم... 😉"
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
    name = message.from_user.full_name or message.from_user.username or "فرمانروا"
    kb = await menu(message.from_user.id, message.chat.type == 'private')
    await message.answer(
        f"👑 سلام <b>{name}</b>!\n"
        f"به <b>پادشاهان زیرزمین</b> خوش اومدی 🔥\n\n"
        f"🎮 سه بازی منتظرته:\n"
        f"• 🎭 مافیا — نقش مخفی و رأی‌گیری\n"
        f"• 🏙️ امپراتوری — اقتصاد، قلمرو و جنگ\n"
        f"• 🃏 کودتا — بلوف و کارت\n\n"
        f"از منو انتخاب کن یا بنویس:\n"
        f"• <code>شروع</code> · <code>پروفایل</code> · <code>راهنما</code>",
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
    win_rate = 0
    if row["games_played"]:
        win_rate = round(100 * row["wins"] / row["games_played"], 1)
    await message.answer(
        f"👤 <b>پروفایل تو</b>\n\n"
        f"🏷️ نام: {row['display_name']}\n"
        f"🪙 سکه: <b>{row['coins']:,}</b>\n"
        f"🎮 بازی‌ها: {row['games_played']}\n"
        f"🏆 بردها: {row['wins']} ({win_rate}%)\n"
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
    await call.answer("عضویت تأیید شد! خوش اومدی 🎉")
    kb = await menu(call.from_user.id, call.message.chat.type == 'private' if call.message else True)
    if call.message:
        try:
            await call.message.edit_text(
                "✅ عضویت هر دو کانال تأیید شد!\n\n"
                "حالا می‌تونی وارد دنیای پادشاهان زیرزمین شی 👑\n"
                "یکی از بازی‌ها رو از منوی پایین انتخاب کن:",
                reply_markup=kb,
            )
        except Exception:
            await call.message.answer(
                "✅ عضویت هر دو کانال تأیید شد! خوش اومدی 🎉",
                reply_markup=kb,
            )


@router.callback_query(F.data == "menu:profile")
async def menu_profile(call: CallbackQuery):
    await call.answer()
    # reuse profile logic via synthetic text
    call.message.from_user = call.from_user  # type: ignore
    async with db().acquire() as conn:
        row = await conn.fetchrow('SELECT * FROM users WHERE telegram_id=$1', call.from_user.id)
    if not row:
        await call.message.answer('اول باید «شروع» رو بزنی 😊')
        return
    win_rate = round(100 * row["wins"] / row["games_played"], 1) if row["games_played"] else 0
    await call.message.answer(
        f"👤 <b>پروفایل تو</b>\n\n"
        f"🏷️ نام: {row['display_name']}\n"
        f"🪙 سکه: <b>{row['coins']:,}</b>\n"
        f"🎮 بازی‌ها: {row['games_played']}\n"
        f"🏆 بردها: {row['wins']} ({win_rate}%)\n"
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
