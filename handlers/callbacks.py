from aiogram import Router, F
from aiogram.types import CallbackQuery
router = Router()


@router.callback_query(F.data.startswith('menu:'))
async def menu_callback(call: CallbackQuery):
    key = call.data.split(':')[1]
    texts = {
        'mafia': (
            "🎭 مافیای کلاسیک\n\n"
            "در گروه:\n"
            "• /mafia_create — ساخت اتاق جدید\n"
            "• /mafia_join — پیوستن به اتاق\n"
            "• /mafia_start — شروع بازی\n"
            "• /mafia_status — وضعیت فعلی\n\n"
            "در خصوصی ربات:\n"
            "• /mafia_night — انتخاب اقدام شبانه\n\n"
            "رأی روز:\n"
            "• /mafia_vote شناسه_تلگرام\n\n"
            "💡 یادت باشه اول تو چت خصوصی /شروع رو زده باشی!"
        ),
        'empire': (
            "🏙️ امپراتوری — اقتصاد و کسب‌وکار\n\n"
            "• /empire یا /empire_menu — منوی اصلی\n"
            "• /empire_daily — پاداش روزانه ۱۰۰ سکه\n"
            "• /empire_work — کار کردن (۲۵ سکه هر ساعت)\n"
            "• /empire_buy workshop|club|factory — خرید یا ارتقا\n"
            "• /empire_collect workshop|club|factory — جمع‌آوری درآمد\n"
            "• /empire_assets — دیدن دارایی‌هات\n"
            "• /empire_top — رتبه‌بندی\n\n"
            "⚔️ جنگ و اتحاد هم داره! از منوی امپراتوری ببین."
        ),
        'coup': (
            "🃏 کودتا\n\n"
            "در گروه:\n"
            "• /coup_create — ساخت اتاق\n"
            "• /coup_join — پیوستن\n"
            "• /coup_start — شروع بازی\n\n"
            "اقدامات:\n"
            "• /coup_help — راهنمای کامل\n\n"
            "در خصوصی ربات:\n"
            "• /coup_hand — دیدن کارت‌های مخفی\n\n"
            "💡 اول تو چت خصوصی /شروع رو بزن تا نقش بگیری!"
        ),
        'rules': (
            "📜 قوانین کلی\n\n"
            "• احترام به بقیه بازیکن‌ها الزامیه 🤝\n"
            "• افشای نقش مخفی ممنوعه 🚫\n"
            "• اسپم و چندحسابی نکن ❌\n"
            "• برای بازی مافیا و کودتا، حتماً اول تو چت خصوصی ربات /شروع رو بزن\n\n"
            "بازی منصفانه و لذت‌بخش باشه! 🎮"
        ),
        'help': (
            "📖 راهنمای سریع\n\n"
            "🔹 دستورات اصلی (با یا بدون /):\n"
            "• شروع / استارت\n"
            "• پروفایل\n"
            "• راهنما / کمک\n"
            "• ادمین (فقط پرسنل)\n\n"
            "از دکمه‌های منو هم می‌تونی استفاده کنی 👆"
        ),
    }
    await call.answer()
    if call.message:
        await call.message.answer(texts.get(key, 'بخش نامعتبر است 😅'))
