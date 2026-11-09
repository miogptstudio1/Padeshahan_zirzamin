from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from handlers.panel_ui import panel_update
from games.empire import service
from games.events import service as event_service
from games.daily import service as daily_service
from games.empire.engine import ASSETS, CITIES, MAX_ASSET_LEVEL, MAX_DEFENSE_LEVEL, hourly_income, SOLDIER_RECRUIT_COST, MAX_SOLDIERS, army_power_bonus

router = Router()
ALIASES = {'کارگاه': 'workshop', 'باشگاه': 'club', 'کارخانه': 'factory', 'workshop': 'workshop', 'club': 'club', 'factory': 'factory'}
CITY_ALIASES = {key: key for key in CITIES}
CITY_ALIASES.update({k: k for k in CITIES})
CITY_ALIASES.update({'بازار': 'market', 'بازار مرکزی': 'market', 'بندر': 'port', 'بندر قدیمی': 'port', 'ارگ': 'citadel', 'ارگ سلطنتی': 'citadel', 'صنعتی': 'industrial', 'منطقه صنعتی': 'industrial', 'پایتخت': 'capital', 'پایتخت زیرزمین': 'capital', 'زاغه': 'slums', 'معدن': 'mines', 'کازینو': 'casino', 'معبد': 'temple', 'انبار': 'arsenal', 'اسکله': 'harbor', 'بازار شب': 'bazaar', 'دژ': 'fort', 'آزمایشگاه': 'lab', 'کاخ': 'palace'})


def empire_keyboard(owner_id: int):
    uid = int(owner_id)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🎁 پاداش', callback_data=f'empire:{uid}:daily'),
         InlineKeyboardButton(text='🧰 کار', callback_data=f'empire:{uid}:work')],
        [InlineKeyboardButton(text='🏭 دارایی', callback_data=f'empire:{uid}:assets'),
         InlineKeyboardButton(text='💵 جمع درآمد', callback_data=f'empire:{uid}:collectmenu')],
        [InlineKeyboardButton(text='🏗️ خرید کارگاه', callback_data=f'empire:{uid}:buy:workshop'),
         InlineKeyboardButton(text='🏗️ باشگاه', callback_data=f'empire:{uid}:buy:club')],
        [InlineKeyboardButton(text='🏗️ کارخانه', callback_data=f'empire:{uid}:buy:factory'),
         InlineKeyboardButton(text='⚔️ ارتش', callback_data=f'empire:{uid}:army')],
        [InlineKeyboardButton(text='🪖 +5 سرباز', callback_data=f'empire:{uid}:recruit5'),
         InlineKeyboardButton(text='🗺️ قلمروها', callback_data=f'empire:{uid}:cities')],
        [InlineKeyboardButton(text='👑 قلمروهای من', callback_data=f'empire:{uid}:mycities'),
         InlineKeyboardButton(text='🏆 رتبه', callback_data=f'empire:{uid}:top')],
        [InlineKeyboardButton(text='🛒 فروشگاه', callback_data=f'empire:{uid}:shop'),
         InlineKeyboardButton(text='🕶️ خلاف', callback_data=f'empire:{uid}:crime')],
    ])


@router.message(Command('empire', 'empire_menu', 'امپراتوری', 'امپراطوری'))
@router.message(F.text.in_({'امپراتوری', 'امپراطوری', 'empire'}))
async def empire_menu(message: Message):
    await message.answer(
        'امپراتوری\nاز دکمه‌ها استفاده کن یا بنویس: پاداش، کار، ارتش، قلمروها، ارتش پیشرفته',
        reply_markup=empire_keyboard(message.from_user.id),
    )


@router.message(Command('empire_daily', 'پاداش'))
@router.message(F.text.in_({'پاداش', 'پاداش روزانه'}))
async def empire_daily(message: Message):
    try:
        reward, balance = await service.claim_daily(message.from_user.id)
        try:
            await event_service.add_score(message.from_user.id, 10, 'economy')
            try:
                await daily_service.progress(message.from_user.id, 'daily', 1)
            except Exception:
                pass
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
            try:
                await daily_service.progress(message.from_user.id, 'work', 1)
            except Exception:
                pass
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
@router.message(F.text.in_({'قلمروها', 'نقشه', 'نقشه قلمرو', 'قلمرو ها', 'لیست قلمرو'}))
async def empire_cities(message: Message):
    try:
        rows = await service.cities_list()
    except Exception as exc:
        await message.answer(f'لیست قلمرو نیومد: {exc}')
        return
    if not rows:
        await message.answer('هنوز قلمروی تو دیتابیس نیست. یه بار ربات رو ری‌استارت کن.')
        return
    header = '🗺️ نقشهٔ قلمروها (مالیات هر ۶ ساعت):'
    free = [r for r in rows if r['owner_id'] is None]
    owned = [r for r in rows if r['owner_id'] is not None]
    lines = [header, f'آزاد: {len(free)} · تصرف‌شده: {len(owned)}', '']
    for row in rows:
        owner = row['owner_name'] or ('آزاد' if row['owner_id'] is None else str(row['owner_id']))
        lines.append(
            f"• {row['name']} [{row['city_key']}] — "
            f"قیمت {row['price']}، مالیات {row['tax_income']}، "
            f"دفاع {row['defense_level']}/{MAX_DEFENSE_LEVEL} — {owner}"
        )
    lines.append('')
    lines.append('خرید: خرید قلمرو market')
    lines.append('یا از دکمهٔ قلمروها تو منوی امپراتوری')
    # تلگرام سقف ۴۰۹۶ کاراکتر دارد
    chunk, size = [], 0
    for line in lines:
        add = len(line) + 1
        if chunk and size + add > 3500:
            await message.answer('\n'.join(chunk))
            chunk, size = [], 0
        chunk.append(line)
        size += add
    if chunk:
        await message.answer('\n'.join(chunk))


@router.message(Command('empire_city_buy', 'خرید_قلمرو'))
@router.message(F.text.regexp(r'^(?:خرید قلمرو)\s+\S+'))
async def empire_city_buy(message: Message):
    text = (message.text or '').strip()
    for pref in ('/empire_city_buy', 'خرید_قلمرو', 'خرید قلمرو'):
        if text.startswith(pref):
            text = text[len(pref):].strip()
            break
    raw = (text.split()[0] if text else '').strip().lower()
    from games.empire.engine import CITIES
    key = CITY_ALIASES.get(raw, raw)
    if key not in CITIES:
        await message.answer('فرمت: خرید قلمرو market\nاز «قلمروها» کلید قلمرو را بردار.')
        return
    try:
        name, cost, balance = await service.city_buy(message.from_user.id, key)
        await message.answer(f'👑 قلمرو «{name}» تصرف شد!\nهزینه: {cost} سکه\n💰 موجودی: {balance}')
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
async def empire_menu_buttons(call: CallbackQuery):
    parts = (call.data or '').split(':')
    if len(parts) == 2:
        await call.answer('این دکمه قدیمی است؛ دوباره امپراتوری بزن.', show_alert=True)
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
    extra = parts[3] if len(parts) > 3 else ''
    await call.answer()
    if not call.message:
        return
    uid = call.from_user.id
    kb = empire_keyboard(uid)
    try:
        if action == 'shop':
            from handlers.shop import catalog_keyboard, _format_catalog
            await panel_update(call, _format_catalog(), parse_mode='HTML', reply_markup=catalog_keyboard(uid))
        elif action == 'crime':
            await panel_update(call, 
                '🕶️ خلاف: حمله · جیب‌بری · باج · قاچاق · پناهگاه',
                reply_markup=kb,
            )
        elif action == 'daily':
            reward, balance = await service.claim_daily(uid)
            try:
                await event_service.add_score(uid, 10, 'economy')
                try:
                    await daily_service.progress(uid, 'daily', 1)
                except Exception:
                    pass
            except Exception:
                pass
            await panel_update(call, f'🎁 +{reward} سکه. موجودی: {balance}', reply_markup=kb)
        elif action == 'work':
            reward, balance = await service.work(uid)
            try:
                await event_service.add_score(uid, 5, 'economy')
                try:
                    await daily_service.progress(uid, 'work', 1)
                except Exception:
                    pass
            except Exception:
                pass
            await panel_update(call, f'🧰 +{reward} سکه. موجودی: {balance}', reply_markup=kb)
        elif action == 'assets':
            rows = await service.assets_for(uid)
            lines = ['🏭 دارایی‌های تو:'] if rows else ['هنوز دارایی نداری. از دکمه‌های خرید استفاده کن.']
            for row in rows:
                lines.append(f"• {ASSETS[row['asset_key']]['name']} سطح {row['level']} — {hourly_income(row['asset_key'], int(row['level']))} سکه/ساعت")
            await panel_update(call, '\n'.join(lines), reply_markup=kb)
        elif action == 'collectmenu':
            rows = [
                [InlineKeyboardButton(text='💵 کارگاه', callback_data=f'empire:{uid}:collect:workshop'),
                 InlineKeyboardButton(text='💵 باشگاه', callback_data=f'empire:{uid}:collect:club')],
                [InlineKeyboardButton(text='💵 کارخانه', callback_data=f'empire:{uid}:collect:factory')],
                [InlineKeyboardButton(text='◀️ بازگشت', callback_data=f'empire:{uid}:assets')],
            ]
            await panel_update(call, 'کدام درآمد را جمع کنیم؟', reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
        elif action == 'collect' and extra in ASSETS:
            name, amount, balance = await service.collect_income(uid, extra)
            await panel_update(call, f'💵 {name}: +{amount}\n💰 {balance}', reply_markup=kb)
        elif action == 'buy' and extra in ASSETS:
            name, level, cost, balance = await service.buy_or_upgrade(uid, extra)
            await panel_update(call, 
                f'🏗️ {name} سطح {level}\nهزینه {cost} · موجودی {balance}',
                reply_markup=kb,
            )
        elif action == 'army':
            army = await service.army_for(uid)
            sol = int(army.get('soldiers') or 0)
            await panel_update(call, 
                f'⚔️ ارتش: {sol} سرباز\nقدرت: +{army_power_bonus(sol)}\nهزینه هر سرباز: {SOLDIER_RECRUIT_COST}',
                reply_markup=kb,
            )
        elif action == 'recruit5':
            total, cost, balance = await service.recruit_soldiers(uid, 5)
            await panel_update(call, f'🪖 سربازان: {total} (−{cost}) · 💰 {balance}', reply_markup=kb)
        elif action == 'top':
            rows = await service.leaderboard(10)
            lines = ['🏆 رتبه‌بندی ثروت'] + [f"{i}. {r['display_name'] or r['telegram_id']} — {r['coins']} سکه" for i, r in enumerate(rows, 1)]
            await panel_update(call, '\n'.join(lines), reply_markup=kb)
        elif action == 'cities':
            rows = await service.cities_list()
            free = [r for r in rows if r['owner_id'] is None]
            owned = [r for r in rows if r['owner_id'] is not None]
            lines = [
                '🗺️ قلمروها',
                f'آزاد: {len(free)} · تصرف‌شده: {len(owned)}',
                '',
                'آزادها (نمونه):',
            ]
            city_btns = []
            for row in free[:12]:
                lines.append(f"• {row['name']} [{row['city_key']}] — {row['price']}🪙")
                city_btns.append([InlineKeyboardButton(
                    text=f"🛒 {row['name'][:18]}",
                    callback_data=f"empire:{uid}:citybuy:{row['city_key']}",
                )])
            if len(free) > 12:
                lines.append(f'… و {len(free)-12} قلمرو آزاد دیگر')
                lines.append('برای لیست کامل بنویس: قلمروها')
            city_btns.append([InlineKeyboardButton(text='◀️ منو', callback_data=f'empire:{uid}:assets')])
            await panel_update(call, '\n'.join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=city_btns) if city_btns else kb)
        elif action == 'citybuy' and extra:
            name, cost, balance = await service.city_buy(uid, extra)
            await panel_update(call, f'✅ {name} خریداری شد (−{cost}) · 💰 {balance}', reply_markup=kb)
        elif action == 'mycities':
            rows = await service.my_cities(uid)
            if not rows:
                await panel_update(call, 'هنوز قلمرویی نداری.', reply_markup=kb)
                return
            lines = ['👑 قلمروهای تو:']
            btns = []
            for row in rows:
                lines.append(f"• {row['name']} — مالیات {row['tax_income']}، دفاع {row['defense_level']}/{MAX_DEFENSE_LEVEL}")
                btns.append([
                    InlineKeyboardButton(text=f"💵 مالیات {row['name'][:12]}", callback_data=f"empire:{uid}:tax:{row['city_key']}"),
                    InlineKeyboardButton(text=f"🛡️ دفاع", callback_data=f"empire:{uid}:defend:{row['city_key']}"),
                ])
            btns.append([InlineKeyboardButton(text='◀️ منو', callback_data=f'empire:{uid}:army')])
            await panel_update(call, '\n'.join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))
        elif action == 'tax' and extra:
            name, amount, balance = await service.collect_tax(uid, extra)
            await panel_update(call, f'💵 مالیات {name}: +{amount} · 💰 {balance}', reply_markup=kb)
        elif action == 'defend' and extra:
            name, level, cost, balance = await service.upgrade_city_defense(uid, extra)
            await panel_update(call, f'🛡️ دفاع {name} → سطح {level} (−{cost}) · 💰 {balance}', reply_markup=kb)
        else:
            await panel_update(call, 'اقدام پشتیبانی نشده.', reply_markup=kb)
    except ValueError as exc:
        await panel_update(call, str(exc), reply_markup=kb)
    except Exception as exc:
        await panel_update(call, f'خطا: {exc}', reply_markup=kb)


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
