from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from games.empire import service
from games.events import service as event_service
from games.empire.engine import ASSETS, CITIES, MAX_ASSET_LEVEL, MAX_DEFENSE_LEVEL, hourly_income, SOLDIER_RECRUIT_COST, MAX_SOLDIERS, army_power_bonus

router = Router()
ALIASES = {'کارگاه': 'workshop', 'باشگاه': 'club', 'کارخانه': 'factory', 'workshop': 'workshop', 'club': 'club', 'factory': 'factory'}
CITY_ALIASES = {key: key for key in CITIES}
CITY_ALIASES.update({'بازار': 'market', 'بازار مرکزی': 'market', 'بندر': 'port', 'بندر قدیمی': 'port', 'ارگ': 'citadel', 'ارگ سلطنتی': 'citadel', 'صنعتی': 'industrial', 'منطقه صنعتی': 'industrial', 'پایتخت': 'capital', 'پایتخت زیرزمین': 'capital'})


def empire_keyboard(owner_id: int):
    uid = int(owner_id)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🎁 پاداش روزانه', callback_data=f'empire:{uid}:daily'), InlineKeyboardButton(text='🧰 کار روزانه', callback_data=f'empire:{uid}:work')],
        [InlineKeyboardButton(text='🏭 دارایی‌های من', callback_data=f'empire:{uid}:assets'), InlineKeyboardButton(text='🏆 رتبه‌بندی', callback_data=f'empire:{uid}:top')],
        [InlineKeyboardButton(text='🗺️ نقشهٔ قلمروها', callback_data=f'empire:{uid}:cities'), InlineKeyboardButton(text='👑 قلمروهای من', callback_data=f'empire:{uid}:mycities')],
        [InlineKeyboardButton(text='🛒 فروشگاه', callback_data=f'empire:{uid}:shop')],
    ])


@router.message(Command('empire', 'empire_menu', 'امپراتوری', 'امپراطوری'))
@router.message(F.text.in_({'امپراتوری', 'امپراطوری', 'empire'}))
async def empire_menu(message: Message):
    await message.answer(
        '🏙️ امپراتوری — اقتصاد و قلمرو\n\n'
        '/empire_daily — پاداش ۱۰۰ سکه‌ای هر ۲۴ ساعت\n'
        '/empire_work — دریافت ۲۵ سکه هر ساعت\n'
        '/empire_buy workshop|club|factory — خرید یا ارتقای کسب‌وکار\n'
        '/empire_collect workshop|club|factory — جمع‌آوری درآمد هر ساعت\n'
        '/empire_assets — دارایی‌های اقتصادی\n/empire_top — رتبه‌بندی ثروت\n\n'
        '/empire_cities — نقشهٔ قلمروها و قیمت‌ها\n'
        '/empire_city_buy market|port|citadel|industrial|capital — خرید قلمرو آزاد\n'
        '/empire_tax market — جمع‌آوری مالیات هر ۶ ساعت\n'
        '/empire_defend market — ارتقای دفاع قلمرو\n'
        '/empire_war market port — حمله از قلمرو اول به دومی\n'
        '/empire_wars — جنگ‌های در جریان\n'
        '/empire_war_resolve شناسه — نهایی‌کردن جنگ پس از ۱۰ دقیقه\n'
        '/empire_army — مشاهدهٔ ارتش\n/empire_recruit تعداد — استخدام سرباز (هر سرباز ۲۰ سکه)\n/empire_disband تعداد — مرخص‌کردن سرباز\n'
        '/empire_my_cities — قلمروهای تو\n/empire_city_top — رتبه‌بندی فرمانروایان\n\n'
        'مالیات هر قلمرو هر ۶ ساعت قابل دریافت است؛ دفاع تا سطح ۵ ارتقا می‌یابد.',
        reply_markup=empire_keyboard(message.from_user.id))


@router.message(Command('empire_daily', 'پاداش'))
@router.message(F.text.in_({'پاداش', 'پاداش روزانه'}))
async def empire_daily(message: Message):
    try:
        reward, balance = await service.claim_daily(message.from_user.id)
        try:
            await event_service.add_score(message.from_user.id, 10, 'economy')
        except Exception:
            pass
        await message.answer(f'🎁 پاداش روزانه: +{reward} سکه\n💰 موجودی: {balance}')
    except ValueError as exc:
        await message.answer(str(exc))


@router.message(Command('empire_work', 'کار'))
@router.message(F.text.in_({'کار', 'کار روزانه'}))
async def empire_work(message: Message):
    try:
        reward, balance = await service.work(message.from_user.id)
        try:
            await event_service.add_score(message.from_user.id, 5, 'economy')
        except Exception:
            pass
        await message.answer(f'🧰 {reward} سکه گرفتی!\n💰 موجودی: {balance}')
    except ValueError as exc:
        await message.answer(str(exc))


@router.message(Command('empire_buy', 'خرید_کسب'))
@router.message(F.text.regexp(r'^(?:خرید کسب|خرید کارگاه|خرید باشگاه|خرید کارخانه|/empire_buy)\s*(.*)$'))
async def empire_buy(message: Message):
    text = (message.text or '').strip()
    for pref in ('/empire_buy', 'خرید کسب', 'خرید کارگاه', 'خرید باشگاه', 'خرید کارخانه', 'خرید_کسب'):
        if text.startswith(pref):
            text = text[len(pref):].strip()
            break
    # default workshop if bare «خرید کارگاه»
    raw = text.strip().lower() or 'workshop'
    if raw not in ALIASES:
        # try last token
        parts = (message.text or '').split()
        raw = parts[-1].lower() if parts else ''
    if raw not in ALIASES:
        await message.answer('فرمت: خرید کسب کارگاه|باشگاه|کارخانه\nیا /empire_buy workshop')
        return
    key = ALIASES[raw]
    try:
        name, level, cost, balance = await service.buy_or_upgrade(message.from_user.id, key)
        await message.answer(f'🏗️ {name} ارتقا یافت!\nسطح: {level}/{MAX_ASSET_LEVEL}\nهزینه: {cost}\nدرآمد ساعتی: {hourly_income(key, level)}\n💰 موجودی: {balance}')
    except ValueError as exc:
        await message.answer(str(exc))


@router.message(Command('empire_collect', 'جمع_درآمد'))
@router.message(F.text.regexp(r'^(?:جمع درآمد|جمع‌آوری|/empire_collect)\s*(.*)$'))
async def empire_collect(message: Message):
    text = (message.text or '').strip()
    for pref in ('/empire_collect', 'جمع درآمد', 'جمع‌آوری', 'جمع_درآمد'):
        if text.startswith(pref):
            text = text[len(pref):].strip()
            break
    raw = text.strip().lower() or 'workshop'
    if raw not in ALIASES:
        parts = (message.text or '').split()
        raw = parts[-1].lower() if parts else ''
    if raw not in ALIASES:
        await message.answer('فرمت: جمع درآمد کارگاه|باشگاه|کارخانه')
        return
    try:
        name, amount, balance = await service.collect_income(message.from_user.id, ALIASES[raw])
        await message.answer(f'💵 درآمد {name}: +{amount} سکه\n💰 موجودی: {balance}')
    except ValueError as exc:
        await message.answer(str(exc))


@router.message(Command('empire_assets', 'دارایی'))
@router.message(F.text.in_({'دارایی', 'دارایی‌ها', 'دارایی ها'}))
async def empire_assets(message: Message):
    rows = await service.assets_for(message.from_user.id)
    if not rows:
        await message.answer('هنوز دارایی‌ای نداری. /empire_buy workshop')
        return
    lines = ['🏭 دارایی‌های تو:']
    for row in rows:
        key = row['asset_key']
        lines.append(f"• {ASSETS[key]['name']} — سطح {row['level']}/{MAX_ASSET_LEVEL}، {hourly_income(key, int(row['level']))} سکه در ساعت")
    await message.answer('\n'.join(lines))


@router.message(Command('empire_top', 'رتبه_ثروت'))
@router.message(F.text.in_({'رتبه ثروت', 'ثروتمندترین', 'لیدربورد ثروت'}))
async def empire_top(message: Message):
    rows = await service.leaderboard(10)
    if not rows:
        await message.answer('هنوز بازیکنی در رتبه‌بندی نیست.')
        return
    lines = ['🏆 رتبه‌بندی ثروت'] + [f"{i}. {r['display_name'] or r['telegram_id']} — {r['coins']} سکه" for i, r in enumerate(rows, 1)]
    await message.answer('\n'.join(lines))


@router.message(Command('empire_cities', 'قلمروها', 'نقشه'))
@router.message(F.text.in_({'قلمروها', 'نقشه', 'نقشه قلمرو'}))
async def empire_cities(message: Message):
    rows = await service.cities_list()
    lines = ['🗺️ نقشهٔ قلمروها (مالیات هر ۶ ساعت):']
    for row in rows:
        owner = row['owner_name'] or ('آزاد' if row['owner_id'] is None else str(row['owner_id']))
        lines.append(f"• {row['name']} [{row['city_key']}] — قیمت {row['price']}، مالیات {row['tax_income']}، دفاع {row['defense_level']}/{MAX_DEFENSE_LEVEL} — مالک: {owner}")
    lines.append('\nخرید: /empire_city_buy market')
    await message.answer('\n'.join(lines))


@router.message(Command('empire_city_buy'))
async def empire_city_buy(message: Message):
    args = (message.text or '').split(maxsplit=1)
    if len(args) != 2 or args[1].strip().lower() not in CITY_ALIASES:
        await message.answer('فرمت: /empire_city_buy market|port|citadel|industrial|capital')
        return
    key = CITY_ALIASES[args[1].strip().lower()]
    try:
        name, cost, balance = await service.city_buy(message.from_user.id, key)
        await message.answer(f'👑 قلمرو «{name}» تصرف شد!\nهزینه: {cost} سکه\n💰 موجودی: {balance}\nبرای دریافت مالیات: /empire_tax {key}')
    except ValueError as exc:
        await message.answer(str(exc))


@router.message(Command('empire_tax'))
async def empire_tax(message: Message):
    args = (message.text or '').split(maxsplit=1)
    if len(args) != 2 or args[1].strip().lower() not in CITY_ALIASES:
        await message.answer('فرمت: /empire_tax market')
        return
    try:
        name, amount, balance = await service.collect_tax(message.from_user.id, CITY_ALIASES[args[1].strip().lower()])
        await message.answer(f'💰 مالیات «{name}»: +{amount} سکه\nموجودی: {balance}')
    except ValueError as exc:
        await message.answer(str(exc))


@router.message(Command('empire_defend'))
async def empire_defend(message: Message):
    args = (message.text or '').split(maxsplit=1)
    if len(args) != 2 or args[1].strip().lower() not in CITY_ALIASES:
        await message.answer('فرمت: /empire_defend market')
        return
    key = CITY_ALIASES[args[1].strip().lower()]
    try:
        name, level, cost, balance = await service.upgrade_city_defense(message.from_user.id, key)
        await message.answer(f'🛡️ دفاع «{name}» به سطح {level}/{MAX_DEFENSE_LEVEL} رسید.\nهزینه: {cost} سکه\nموجودی: {balance}')
    except ValueError as exc:
        await message.answer(str(exc))


@router.message(Command('empire_my_cities'))
async def empire_my_cities(message: Message):
    rows = await service.my_cities(message.from_user.id)
    if not rows:
        await message.answer('هنوز قلمرویی نداری. با /empire_cities نقشه را ببین.')
        return
    lines = ['👑 قلمروهای تو:']
    for row in rows:
        lines.append(f"• {row['name']} — مالیات {row['tax_income']} هر ۶ ساعت؛ دفاع {row['defense_level']}/{MAX_DEFENSE_LEVEL}؛ کلید: {row['city_key']}")
    await message.answer('\n'.join(lines))


@router.message(Command('empire_city_top'))
async def empire_city_top(message: Message):
    rows = await service.city_leaderboard(10)
    if not rows:
        await message.answer('هنوز کسی قلمرویی تصرف نکرده است.')
        return
    lines = ['🏆 فرمانروایان قلمروها:']
    for i, row in enumerate(rows, 1):
        lines.append(f"{i}. {row['display_name'] or row['telegram_id']} — {row['city_count']} قلمرو، درآمد مالیاتی پایه {row['tax_total']}، دفاع کل {row['defense_total']}")
    await message.answer('\n'.join(lines))


@router.message(Command('empire_army', 'ارتش'))
@router.message(F.text.in_({'ارتش', 'سربازان'}))
async def empire_army(message: Message):
    army = await service.army_for(message.from_user.id)
    soldiers = army['soldiers']
    await message.answer(
        f"🪖 ارتش تو: {soldiers}/{MAX_SOLDIERS} سرباز\n"
        f"قدرت افزوده به جنگ: +{army_power_bonus(soldiers)}\n"
        f"هزینهٔ استخدام: {SOLDIER_RECRUIT_COST} سکه برای هر سرباز\n"
        "برای استخدام: /empire_recruit 10\nبرای مرخص‌کردن: /empire_disband 5"
    )


@router.message(Command('empire_recruit'))
async def empire_recruit(message: Message):
    args = (message.text or '').split(maxsplit=1)
    if len(args) != 2 or not args[1].isdigit():
        await message.answer('فرمت: /empire_recruit تعداد (از ۱ تا ۱۰۰ در هر بار)')
        return
    try:
        soldiers, cost, balance = await service.recruit_soldiers(message.from_user.id, int(args[1]))
        await message.answer(f'🪖 سربازگیری انجام شد. تعداد ارتش: {soldiers}/{MAX_SOLDIERS}\nهزینه: {cost} سکه\nموجودی: {balance} سکه\nقدرت افزوده به حمله/دفاع: +{army_power_bonus(soldiers)}')
    except ValueError as exc:
        await message.answer(str(exc))


@router.message(Command('empire_disband'))
async def empire_disband(message: Message):
    args = (message.text or '').split(maxsplit=1)
    if len(args) != 2 or not args[1].isdigit():
        await message.answer('فرمت: /empire_disband تعداد')
        return
    try:
        remaining, dismissed = await service.disband_soldiers(message.from_user.id, int(args[1]))
        await message.answer(f'🪖 {dismissed} سرباز مرخص شدند. تعداد باقی‌مانده: {remaining}. قدرت ارتش: +{army_power_bonus(remaining)}')
    except ValueError as exc:
        await message.answer(str(exc))


@router.callback_query(lambda call: call.data and call.data.startswith('empire:'))
async def empire_menu_buttons(call):
    parts = (call.data or '').split(':')
    # empire:{owner}:{action}  (legacy empire:action also accepted for owner=clicker only via reject)
    if len(parts) == 2:
        await call.answer('این دکمه قدیمی است؛ دوباره /empire بزن.', show_alert=True)
        return
    if len(parts) < 3:
        await call.answer('دکمه نامعتبر', show_alert=True)
        return
    try:
        owner_id = int(parts[1])
    except ValueError:
        await call.answer('دکمه نامعتبر', show_alert=True)
        return
    if int(call.from_user.id) != owner_id:
        await call.answer('🚫 این پنل مال تو نیست.', show_alert=True)
        return
    action = parts[2]
    await call.answer()
    if not call.message:
        return
    if action == 'shop':
        await call.message.answer('🛒 برای فروشگاه بنویس: فروشگاه یا /shop')
        return
    if action == 'daily':
        try:
            reward, balance = await service.claim_daily(call.from_user.id)
            await call.message.answer(f'🎁 +{reward} سکه. موجودی: {balance}')
        except ValueError as exc:
            await call.message.answer(str(exc))
    elif action == 'work':
        try:
            reward, balance = await service.work(call.from_user.id)
            await call.message.answer(f'🧰 +{reward} سکه. موجودی: {balance}')
        except ValueError as exc:
            await call.message.answer(str(exc))
    elif action == 'assets':
        rows = await service.assets_for(call.from_user.id)
        lines = ['🏭 دارایی‌های تو:'] if rows else ['هنوز دارایی‌ای نداری. /empire_buy workshop']
        for row in rows:
            lines.append(f"• {ASSETS[row['asset_key']]['name']} سطح {row['level']} — {hourly_income(row['asset_key'], int(row['level']))} سکه/ساعت")
        await call.message.answer('\n'.join(lines))
    elif action == 'top':
        rows = await service.leaderboard(10)
        lines = ['🏆 رتبه‌بندی ثروت'] + [f"{i}. {r['display_name'] or r['telegram_id']} — {r['coins']} سکه" for i, r in enumerate(rows, 1)]
        await call.message.answer('\n'.join(lines))
    elif action == 'cities':
        rows = await service.cities_list()
        lines = ['🗺️ قلمروها:']
        for row in rows:
            lines.append(f"• {row['name']} [{row['city_key']}] — {row['price']} سکه، مالیات {row['tax_income']}؛ مالک: {row['owner_name'] or 'آزاد'}")
        await call.message.answer('\n'.join(lines))
    elif action == 'mycities':
        rows = await service.my_cities(call.from_user.id)
        lines = ['👑 قلمروهای تو:']
        for row in rows:
            lines.append(f"• {row['name']} — مالیات {row['tax_income']}، دفاع {row['defense_level']}/{MAX_DEFENSE_LEVEL}")
        await call.message.answer('\n'.join(lines) if rows else 'هنوز قلمرویی نداری.')


@router.message(Command('empire_war'))
async def empire_war(message: Message):
    args = (message.text or '').split()
    if len(args) != 3 or args[1].lower() not in CITY_ALIASES or args[2].lower() not in CITY_ALIASES:
        await message.answer('فرمت: /empire_war market port\nقلمرو اول باید مال تو و قلمرو دوم متعلق به بازیکن دیگری باشد.')
        return
    try:
        war_id, attack_name, target_name, fee, balance, resolves_at, defender_id, power = await service.declare_war(
            message.from_user.id, CITY_ALIASES[args[1].lower()], CITY_ALIASES[args[2].lower()])
        await message.answer(
            f'⚔️ جنگ شمارهٔ {war_id} اعلام شد!\nمبدأ: {attack_name}\nهدف: {target_name}\n'
            f'هزینهٔ اعلام جنگ: {fee} سکه؛ موجودی: {balance}\n'
            f'قدرت حملهٔ ثبت‌شده: {power}\nنتیجه پس از ۱۰ دقیقه قابل تعیین است.\n'
            f'مدافع می‌تواند تا آن زمان دفاع قلمرو را با /empire_defend {CITY_ALIASES[args[2].lower()]} ارتقا دهد.')
        try:
            await message.bot.send_message(defender_id, f'🚨 به قلمرو «{target_name}» حمله شده است! جنگ شمارهٔ {war_id}. برای مشاهده: /empire_wars')
        except Exception:
            pass
    except ValueError as exc:
        await message.answer(str(exc))


@router.message(Command('empire_wars', 'جنگ‌ها', 'جنگها'))
@router.message(F.text.in_({'جنگ‌ها', 'جنگها', 'جنگ های من'}))
async def empire_wars(message: Message):
    rows = await service.pending_wars(message.from_user.id)
    if not rows:
        await message.answer('در حال حاضر جنگ فعالی برای تو ثبت نشده است.')
        return
    lines = ['⚔️ جنگ‌های در جریان:']
    for row in rows:
        side = 'مهاجم' if int(row['attacker_id']) == message.from_user.id else 'مدافع'
        lines.append(f"• جنگ #{row['id']} — {row['attack_city_name']} ← {row['target_city_name']}؛ نقش تو: {side}; پایان آماده‌سازی: {row['resolves_at'].strftime('%H:%M UTC')}")
        lines.append(f"  نهایی‌سازی پس از پایان زمان: /empire_war_resolve {row['id']}")
    await message.answer('\n'.join(lines))


@router.message(Command('empire_war_resolve'))
async def empire_war_resolve(message: Message):
    args = (message.text or '').split(maxsplit=1)
    if len(args) != 2 or not args[1].isdigit():
        await message.answer('فرمت: /empire_war_resolve شناسه_جنگ')
        return
    try:
        result = await service.resolve_war(message.from_user.id, int(args[1]))
        if result.get('cancelled'):
            text = f"⚠️ جنگ #{result['id']} لغو شد، چون مالکیت هدف در این فاصله تغییر کرده است."
        elif result['won']:
            text = (f"🏆 پیروزی مهاجم در جنگ #{result['id']}!\nقلمرو «{result['target_name']}» تصرف شد.\n"
                    f"قدرت حمله: {result['attack_power']} | قدرت دفاع: {result['defense_power']}")
        else:
            text = (f"🛡️ مدافع جنگ #{result['id']} را برد و قلمرو «{result['target_name']}» را حفظ کرد.\n"
                    f"قدرت حمله: {result['attack_power']} | قدرت دفاع: {result['defense_power']}")
        await message.answer(text)
        for uid in {result['attacker_id'], result['defender_id']} - {message.from_user.id}:
            try:
                await message.bot.send_message(uid, text)
            except Exception:
                pass
    except ValueError as exc:
        await message.answer(str(exc))
