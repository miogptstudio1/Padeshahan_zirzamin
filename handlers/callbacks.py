from aiogram import Router, F
from aiogram.types import CallbackQuery
router = Router()


@router.callback_query(F.data.startswith('menu:'))
async def menu_callback(call: CallbackQuery):
    key = call.data.split(':')[1]
    texts = {
        'mafia': 'مافیا تو گروه: مافیا بساز · جوین · شروع\nنقش‌ها خصوصی میان. اول تو ربات شروع بزن.',
        'coup': 'کودتا تو گروه: کودتا بساز · جوین · شروع\nکارت‌ها خصوصی. با دکمه هم می‌تونی بازی کنی.',
        'empire': 'امپراتوری: پاداش · کار · قلمروها · ارتش\nمنو: امپراتوری',
        'army': 'ارتش پیشرفته: واحد تخصصی و فرمانده\nبزن: ارتش پیشرفته',
        'shop': 'فروشگاه: خرید · تجهیز · موجودی · صندوق\nبزن: فروشگاه',
        'market': 'بازار بازیکن‌ها\nبزن: بازار',
        'crime': 'حمله · جیب‌بری · باج · قاچاق · هیل\nبزن: خلاف',
        'boss': 'باس جهانی\nبزن: باس یا باس بزن',
        'spy': 'جاسوسی با ریپلای یا آیدی\nبزن: جاسوسی',
        'missions': 'مأموریت روزانه\nبزن: مأموریت',
        'family': 'خاندان\nساخت خاندان اسم | تگ',
        'event': 'ایونت فعال\nبزن: ایونت',
        'profile': 'بزن: پروفایل',
        'help': 'بزن: راهنما یا راهنما کامل',
        'rules': 'احترام · نقش مخفی لو نده · اسپم نکن',
        'admin': 'بزن: ادمین',
    }
    await call.answer()
    if call.message:
        await call.message.answer(texts.get(key, 'از منو انتخاب کن.'))
