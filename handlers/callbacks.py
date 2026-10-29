from aiogram import Router, F
from aiogram.types import CallbackQuery
router=Router()
@router.callback_query(F.data.startswith('menu:'))
async def menu_callback(call:CallbackQuery):
 key=call.data.split(':')[1]
 texts={
 'mafia':'🎭 مافیای کلاسیک\nدر گروه: /mafia_create برای ساخت اتاق، /mafia_join برای پیوستن، /mafia_start برای شروع و /mafia_status برای وضعیت.\nدر خصوصی: /mafia_night برای انتخاب اقدام شبانه.\nرأی روز: /mafia_vote شناسه_تلگرام',
 'empire':'🏙️ امپراتوری — اقتصاد و کسب‌وکار\n/empire_daily — پاداش ۱۰۰ سکه‌ای هر ۲۴ ساعت\n/empire_work — دریافت ۲۵ سکه هر ساعت\n/empire_buy workshop|club|factory — خرید یا ارتقا\n/empire_collect workshop|club|factory — جمع‌آوری درآمد\n/empire_assets — دارایی‌ها\n/empire_top — رتبه‌بندی',
 'coup':'🃏 کودتا\nدر گروه: /coup_create برای ساخت اتاق، /coup_join برای پیوستن و /coup_start برای شروع.\nاقدامات: /coup_help\nبرای دیدن کارت مخفی: /coup_hand را در خصوصی ربات بزن.',
 'rules':'📜 قوانین کلی\n• احترام به بازیکنان الزامی است.\n• افشای نقش مخفی ممنوع است.\n• از اسپم و چندحسابی خودداری کن.\n• برای بازی مافیا، ابتدا /start را در خصوصی ربات بزن.'}
 await call.answer()
 if call.message: await call.message.answer(texts.get(key,'بخش نامعتبر است.'))
