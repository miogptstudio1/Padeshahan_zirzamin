from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from core.database import upsert_user, db
from config import WEB_APP_URL
from membership import membership_status, join_keyboard
router=Router()

def menu(show_web_app: bool = False):
 rows = [[InlineKeyboardButton(text='🎭 مافیای کلاسیک',callback_data='menu:mafia')], [InlineKeyboardButton(text='🏙️ امپراتوری',callback_data='menu:empire'),InlineKeyboardButton(text='🃏 کودتا',callback_data='menu:coup')], [InlineKeyboardButton(text='📜 قوانین',callback_data='menu:rules')]]
 if show_web_app and WEB_APP_URL.startswith("https://"):
  rows.insert(0, [InlineKeyboardButton(text='🌐 ورود به وب‌اپ', web_app=WebAppInfo(url=WEB_APP_URL))])
 return InlineKeyboardMarkup(inline_keyboard=rows)

@router.message(CommandStart())
async def start(message:Message):
 joined, _, error = await membership_status(message.bot, message.from_user.id)
 if not joined:
  text = ('⚠️ فعلاً امکان بررسی عضویت وجود ندارد. لطفاً بعداً دوباره امتحان کن؛ مدیر ربات باید دسترسی لازم را به ربات بدهد.' if error else '👑 برای ورود به پادشاهان زیرزمین، عضویت در هر دو کانال زیر اجباری است. بعد از عضویت، «بررسی عضویت» را بزن.')
  await message.answer(text, reply_markup=join_keyboard())
  return
 await upsert_user(message.from_user.id,message.from_user.username,message.from_user.full_name or str(message.from_user.id))
 await message.answer('👑 به پادشاهان زیرزمین خوش آمدی!\nسه بازی، یک امپراتوری.\n\nبرای دریافت نقش مخفی، ابتدا باید همین‌جا /start را زده باشی.',reply_markup=menu(message.chat.type == 'private'))

@router.message(Command('profile'))
async def profile(message:Message):
 async with db().acquire() as conn:
  row=await conn.fetchrow('SELECT * FROM users WHERE telegram_id=$1',message.from_user.id)
 if not row: await message.answer('ابتدا /start را بزن.'); return
 await message.answer(f'👤 {row["display_name"]}\n🪙 سکه: {row["coins"]}\n🎮 بازی‌ها: {row["games_played"]}\n🏆 بردها: {row["wins"]}')


@router.callback_query(F.data == "membership:check")
async def check_required_membership(call: CallbackQuery):
 joined, missing, error = await membership_status(call.bot, call.from_user.id)
 if error:
  await call.answer("بررسی عضویت ناموفق بود؛ مدیر باید دسترسی ربات به کانال‌ها را بررسی کند.", show_alert=True)
  return
 if not joined:
  await call.answer("هنوز عضو هر دو کانال نشده‌ای.", show_alert=True)
  if call.message:
   try:
    await call.message.edit_text("برای ادامه، در هر دو کانال عضو شو و دوباره بررسی را بزن.", reply_markup=join_keyboard())
   except Exception:
    await call.message.answer("برای ادامه، در هر دو کانال عضو شو و دوباره بررسی را بزن.", reply_markup=join_keyboard())
  return
 await upsert_user(call.from_user.id, call.from_user.username, call.from_user.full_name or str(call.from_user.id))
 await call.answer("عضویت تأیید شد! خوش آمدی.")
 if call.message:
  try:
   await call.message.edit_text("✅ عضویت هر دو کانال تأیید شد. حالا می‌توانی وارد بازی شوی.", reply_markup=menu(call.message.chat.type == 'private'))
  except Exception:
   await call.message.answer("✅ عضویت هر دو کانال تأیید شد.", reply_markup=menu(call.message.chat.type == 'private'))
