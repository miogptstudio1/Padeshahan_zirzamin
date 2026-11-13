from aiogram import Router, F
from aiogram.types import CallbackQuery
from handlers.panel_ui import panel_update

router = Router()


@router.callback_query(F.data.startswith("menu:"))
async def menu_callback(call: CallbackQuery):
    key = (call.data or "").split(":")[1] if call.data else ""
    await call.answer()
    if not call.message:
        return
    uid = call.from_user.id

    try:
        if key == "games":
            await panel_update(
                call,
                "🎮 بازی‌های گروهی (تو گروه اسمش رو بزن):\n"
                "جاسوس ناشناس · اتاق فرار · پادشاه خیانت\n"
                "جزیره گمشده · کارآگاه خصوصی · نبرد امپراتوری‌ها\n"
                "مزایده مرگبار · دادگاه سلطنتی · آخرین بازمانده\n"
                "بمب ساعتی · شکار گنج · نبرد کلمات\n\n"
                "سریع: تاس · شیر/خط · دوئل (ریپلای)\n"
                "لیست: بازی‌ها",
            )
            return
        if key == "gym":
            from games.gym import service as gym_service
            from handlers.gym import gym_kb
            text = await gym_service.status_text(uid)
            await panel_update(call, text, reply_markup=gym_kb(uid))
            return
        if key == "shop":
            from handlers.shop import catalog_keyboard, _format_catalog_page  # noqa: F401
            await panel_update(
                call,
                _format_catalog_page(0),
                parse_mode="HTML",
                reply_markup=catalog_keyboard(uid, 0),
            )
            return
        if key == "empire":
            from handlers.empire import empire_keyboard
            await panel_update(
                call,
                "امپراتوری زیرزمین.\nقلمرو بگیر، مالیات بکش، جنگ راه بنداز.",
                reply_markup=empire_keyboard(uid),
            )
            return
        if key == "army":
            from handlers.army import army_keyboard
            try:
                from games.empire import army_advanced as army_svc
                text = army_svc.catalog_text()
            except Exception:
                text = "ارتش پیشرفته\nبزن: ارتش پیشرفته"
            await panel_update(call, text, reply_markup=army_keyboard(uid))
            return
        if key == "boss":
            from handlers.boss import boss_kb
            try:
                from games.boss import service as boss_service
                st = await boss_service.boss_status(uid)
                b = st.get("boss") or st
                text = (
                    f"👹 {b.get('name', 'باس')}\n"
                    f"❤️ {int(b.get('hp') or 0):,}/{int(b.get('max_hp') or 0):,}\n"
                    f"بزن: باس بزن"
                )
            except Exception:
                text = "باس جهانی\nبزن: باس بزن"
            await panel_update(call, text, reply_markup=boss_kb(uid))
            return
        if key == "crime":
            await panel_update(
                call,
                "🕶️ کار کثیف\n"
                "حمله · جیب‌بری · باج · قاچاق · آتش · یورش · دعوا\n"
                "جونت تموم شد؟ هیل بزن. مردی ده دقیقه خاکی.",
            )
            return
        if key == "help":
            from handlers.guide import GUIDE_SHORT
            await panel_update(call, GUIDE_SHORT, parse_mode="HTML")
            return
        if key == "profile":
            await panel_update(call, "برای پروفایل کامل بنویس: پروفایل")
            return
    except Exception as exc:
        await panel_update(call, f"گیر کرد: {exc}")
        return

    texts = {
        "mafia": "مافیا تو گروه: مافیا بساز · جوین · شروع. نقش‌ها خصوصی میان.",
        "coup": "کودتا تو گروه: کودتا بساز. دکمه‌ها توضیح دارن؛ الکی نزن.",
        "market": "بازار بازیکن‌ها.\nبزن: بازار",
        "pulse": "شهر شلوغ شده؟\nبزن: وضعیت جهان",
        "spy": "جاسوسی: ریپلای کن یا آیدی بده.",
        "missions": "کار روزانه.\nبزن: مأموریت",
        "family": "خونت کجاست؟\nساخت خاندان اسم | تگ",
        "event": "رقابت فصل.\nبزن: ایونت",
        "rules": "احترام · نقش لو نده · اسپم نکن · پنل بقیه رو لمس نکن",
        "admin": "پنل ادمین.\nبزن: ادمین",
    }
    await panel_update(call, texts.get(key, "از منو یکی رو بردار."))
