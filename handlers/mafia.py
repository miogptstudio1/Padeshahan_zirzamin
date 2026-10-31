import asyncio
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from core.database import db, upsert_user
from games.mafia import service
from config import NIGHT_SECONDS, DAY_SECONDS, ADMIN_IDS

router = Router()
_timer_tasks: dict[int, asyncio.Task] = {}

async def name_of(message: Message) -> str:
    return (message.from_user.full_name or str(message.from_user.id))[:80]

def room_keyboard(room_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🎭 پیوستن به بازی', callback_data=f'ma:join:{room_id}')],
        [InlineKeyboardButton(text='▶️ شروع بازی', callback_data=f'ma:start:{room_id}'),
         InlineKeyboardButton(text='📊 وضعیت', callback_data=f'ma:status:{room_id}')],
        [InlineKeyboardButton(text='📜 قوانین', callback_data=f'ma:rules:{room_id}'),
         InlineKeyboardButton(text='❌ لغو', callback_data=f'ma:cancel:{room_id}')],
    ])

def target_keyboard(room_id: int, targets, prefix: str):
    rows=[]
    for p in targets:
        rows.append([InlineKeyboardButton(text=p['display_name'][:50], callback_data=f'ma:{prefix}:{room_id}:{p["telegram_id"]}')])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None

def phase_duration(phase: str) -> int:
    return NIGHT_SECONDS if phase == 'night' else DAY_SECONDS if phase == 'day' else 30

async def arm_timer(bot, room_id: int, chat_id: int, phase: str, remaining: float | None = None):
    old=_timer_tasks.get(room_id)
    if old and not old.done(): old.cancel()
    async def timer():
        try:
            duration = phase_duration(phase) if remaining is None else max(0.0, remaining)
            await asyncio.sleep(duration)
            room=await service.get_room(room_id)
            if not room or room['status'] != phase: return
            if phase == 'intro_day':
                await service.advance_intro(room_id, 'intro_day', 'intro_night')
                await bot.send_message(chat_id, '🌙 روز معارفه تمام شد؛ چالش و رأی‌گیری در این مرحله وجود ندارد. شب معارفه شروع شد؛ اعضای مافیا می‌توانند در خصوصی با هم آشنا شوند. این مرحله ۳۰ ثانیه طول می‌کشد.')
                players = await service.room_players(room_id)
                for p in players:
                    if p['role'] == 'mafia':
                        teammates = [x['display_name'] for x in players if x['role'] == 'mafia' and x['telegram_id'] != p['telegram_id']]
                        try: await bot.send_message(p['telegram_id'], '🌙 شب معارفه. هم‌تیمی‌های مافیا: ' + (', '.join(teammates) if teammates else 'نداری؛ تو تنها مافیایی.'))
                        except Exception: pass
                await arm_timer(bot, room_id, chat_id, 'intro_night')
                return
            if phase == 'intro_night':
                await service.advance_intro(room_id, 'intro_night', 'night')
                await bot.send_message(chat_id, f'🌑 شب اول بازی شروع شد؛ {NIGHT_SECONDS} ثانیه فرصت اقدام دارید.')
                await send_night_prompts(bot, room_id)
                await arm_timer(bot, room_id, chat_id, 'night')
                return
            if phase == 'handshake':
                await bot.send_message(chat_id, '🤝 زمان دست‌دادن به پایان رسید. سازندهٔ اتاق یا مدیر ربات باید /mafia_handshake_done را بزند تا شب ادامه پیدا کند.')
                return
            if phase=='night':
                victim, saved, detective, alive, win = await service.resolve_night(room_id)
                msg='☀️ شب به پایان رسید. '
                if victim is None: msg += 'مافیا هدفی انتخاب نکرد.'
                elif saved: msg += '🩺 پزشک توانست هدف حمله را نجات دهد.'
                else:
                    target=next((p for p in await service.room_players(room_id) if p['telegram_id']==victim),None)
                    msg += f'یک بازیکن حذف شد: {target["display_name"] if target else "بازیکن"}.'
                for actor_id, target_name, is_mafia in detective:
                    try: await bot.send_message(actor_id, f'🔎 نتیجهٔ بررسی «{target_name}»: ' + ('این بازیکن مافیاست.' if is_mafia else 'این بازیکن مافیا نیست.'))
                    except Exception: pass
                if win:
                    msg += '\n🏆 بازی تمام شد: ' + ('مافیا برنده شد.' if win=='mafia' else 'شهروندان برنده شدند.')
                else:
                    msg += f'\n🗳️ روز شروع شد؛ {DAY_SECONDS} ثانیه برای رأی‌گیری فرصت دارید.\nبرای رأی: /mafia_vote شناسه'
                    await arm_timer(bot,room_id,chat_id,'day')
                await bot.send_message(chat_id,msg)
            else:
                eliminated, players, win = await service.resolve_day(room_id)
                if eliminated:
                    target=next((p for p in players if p['telegram_id']==eliminated),None)
                    msg=f'🗳️ نتیجهٔ رأی‌گیری: {target["display_name"] if target else "بازیکن"} حذف شد.'
                else: msg='🗳️ رأی‌ها مساوی شد یا رأیی ثبت نشد؛ کسی حذف نشد.'
                if win: msg += '\n🏆 بازی تمام شد: ' + ('مافیا برنده شد.' if win=='mafia' else 'شهروندان برنده شدند.')
                elif (await service.get_room(room_id))['status'] == 'handshake':
                    msg += '\n🤝 فقط سه بازیکن باقی مانده‌اند؛ مرحلهٔ دست‌دادن آغاز شد. پس از پایان گفت‌وگو، سازنده یا مدیر /mafia_handshake_done را بزند.'
                    await arm_timer(bot,room_id,chat_id,'handshake')
                else:
                    msg += f'\n🌙 شب جدید شروع شد؛ {NIGHT_SECONDS} ثانیه فرصت اقدام دارید. نقش‌دارها از /mafia_night در خصوصی استفاده کنند.'
                    await send_night_prompts(bot,room_id)
                    await arm_timer(bot,room_id,chat_id,'night')
                await bot.send_message(chat_id,msg)
        except asyncio.CancelledError: pass
        except Exception as exc:
            try: await bot.send_message(chat_id,f'خطا در تایمر بازی: {exc}')
            except Exception: pass
    _timer_tasks[room_id]=asyncio.create_task(timer())

async def restore_active_timers(bot):
    """Re-arm phase timers from PostgreSQL after bot startup."""
    from datetime import datetime, timezone
    rooms = await service.active_rooms()
    restored = 0
    for room in rooms:
        phase = room['status']
        state = service.decode_state(room['state'])
        raw_started = state.get('phase_started_at')
        elapsed = 0.0
        if raw_started:
            try:
                started = datetime.fromisoformat(raw_started)
                if started.tzinfo is None:
                    started = started.replace(tzinfo=timezone.utc)
                elapsed = max(0.0, (datetime.now(timezone.utc) - started).total_seconds())
            except (TypeError, ValueError):
                elapsed = 0.0
        remaining = max(0.0, phase_duration(phase) - elapsed)
        await arm_timer(bot, room['id'], room['chat_id'], phase, remaining=remaining)
        restored += 1
    return restored

async def send_night_prompts(bot, room_id: int):
    players=await service.room_players(room_id)
    living=[p for p in players if p['alive']]
    for p in living:
        if p['role'] not in ('mafia','doctor','detective'): continue
        try:
            kb=target_keyboard(room_id,[x for x in living if x['telegram_id']!=p['telegram_id'] or p['role']=='doctor'],'act')
            await bot.send_message(p['telegram_id'],f'🌙 نوبت شب است. نقش تو: {service.ROLE_NAMES[p["role"]]}\nهدف را انتخاب کن:',reply_markup=kb)
        except Exception: pass

@router.message(Command('mafia_create', 'مافیا_بساز'))
@router.message(F.text.in_({'مافیا بساز', 'ساخت مافیا', 'اتاق مافیا'}))
async def create(message: Message):
    if not message.chat or message.chat.type=='private':
        await message.answer('این دستور را داخل گروه بازی بفرست.'); return
    await upsert_user(message.from_user.id,message.from_user.username,await name_of(message))
    try:
        room_id=await service.open_room(message.chat.id,message.from_user.id,await name_of(message))
        await message.answer(f'🎭 اتاق مافیا شمارهٔ {room_id} ساخته شد!\nبرای پیوستن، دکمه را بزنید.\nشروع بازی: /mafia_start',reply_markup=room_keyboard(room_id))
    except ValueError as e: await message.answer(str(e))

@router.callback_query(F.data.startswith('ma:join:'))
async def join_callback(call: CallbackQuery):
    room_id=int(call.data.split(':')[2]); user=call.from_user
    await upsert_user(user.id,user.username,user.full_name or str(user.id))
    try:
        count=await service.join_room(room_id,user.id,user.full_name or str(user.id))
        await call.answer('ثبت‌نام شدی!')
        try: await user.send_message(f'ثبت‌نامت در اتاق مافیای شمارهٔ {room_id} انجام شد. وقتی بازی شروع شود، نقش در همین خصوصی ارسال می‌شود.')
        except Exception: pass
        if call.message: await call.message.reply(f'✅ {user.full_name} ثبت‌نام شد. تعداد: {count}')
    except ValueError as e: await call.answer(str(e),show_alert=True)


@router.callback_query(F.data.startswith('ma:start:'))
async def start_callback(call: CallbackQuery):
    room_id = int(call.data.split(':')[2])
    try:
        assigned, chat_id = await service.start_room(room_id, call.from_user.id)
        failures = []
        for tg_id, role in assigned:
            try:
                await call.bot.send_message(
                    tg_id,
                    f'🎭 بازی شروع شد! نقش مخفی تو: {service.ROLE_NAMES[role]}\n'
                    f'برای اقدام شبانه از «مافیا شب» یا دکمه‌ها استفاده کن. نقش را در گروه فاش نکن.',
                )
            except Exception:
                failures.append(tg_id)
        if failures:
            await service.cancel_room(room_id, call.from_user.id, is_admin=True)
            await call.answer('ارسال نقش ناموفق؛ اتاق لغو شد', show_alert=True)
            if call.message:
                await call.message.answer(
                    '⚠️ نقش خصوصی به همه نرسید. همه باید اول در خصوصی ربات «شروع» بزنند.'
                )
            return
        await call.answer('شروع شد!')
        if call.message:
            await call.message.answer(
                '☀️ روز معارفه شروع شد؛ ۳۰ ثانیه فرصت گفت‌وگو. سپس شب معارفه خودکار آغاز می‌شود.'
            )
            await arm_timer(call.bot, room_id, chat_id, 'intro_day')
    except ValueError as e:
        await call.answer(str(e)[:180], show_alert=True)
    except Exception as e:
        await call.answer(str(e)[:180], show_alert=True)


@router.callback_query(F.data.startswith('ma:status:'))
async def status_callback(call: CallbackQuery):
    room_id = int(call.data.split(':')[2])
    room = await service.get_room(room_id)
    if not room:
        await call.answer('اتاق پیدا نشد', show_alert=True)
        return
    players = await service.room_players(room_id)
    labels = {
        'lobby': 'ثبت‌نام', 'intro_day': 'روز معارفه', 'intro_night': 'شب معارفه',
        'night': 'شب', 'day': 'روز', 'handshake': 'دست‌دادن', 'finished': 'پایان',
    }
    lines = [
        f'🎭 اتاق #{room_id} — {labels.get(room["status"], room["status"])}',
        f'بازیکنان: {len(players)}',
    ]
    lines += [f'{"🟢" if p["alive"] else "⚫"} {p["display_name"]}' for p in players]
    await call.answer()
    if call.message:
        await call.message.answer('\n'.join(lines), reply_markup=room_keyboard(room_id))


@router.callback_query(F.data.startswith('ma:rules:'))
async def rules_callback(call: CallbackQuery):
    await call.answer()
    if call.message:
        await call.message.answer(
            '📜 قوانین مافیا\n'
            '• نقش‌ها: مافیا، پزشک، کارآگاه، شهروند\n'
            '• شب: اقدام نقش‌دارها · روز: بحث و رأی\n'
            '• قبل از شروع همه باید در خصوصی ربات «شروع» زده باشند\n'
            '• نقش مخفی را در گروه فاش نکن'
        )


@router.callback_query(F.data.startswith('ma:cancel:'))
async def cancel_callback(call: CallbackQuery):
    room_id = int(call.data.split(':')[2])
    try:
        await service.cancel_room(room_id, call.from_user.id)
        await call.answer('لغو شد')
        if call.message:
            await call.message.answer(f'❌ اتاق {room_id} لغو شد.')
    except ValueError as e:
        await call.answer(str(e)[:180], show_alert=True)


@router.message(Command('mafia_join', 'مافیا_جوین'))
@router.message(F.text.in_({'مافیا جوین', 'جوین مافیا', 'پیوستن مافیا'}))
async def join_command(message: Message):
    room=await service.get_open_room(message.chat.id)
    if not room: await message.answer('اتاقی برای ثبت‌نام پیدا نشد.'); return
    try:
        count=await service.join_room(room['id'],message.from_user.id,await name_of(message))
        await message.answer(f'✅ ثبت‌نام شدی. تعداد بازیکنان: {count}')
    except ValueError as e: await message.answer(str(e))

@router.message(Command('mafia_status', 'مافیا_وضعیت'))
@router.message(F.text.in_({'مافیا وضعیت', 'وضعیت مافیا'}))
async def status(message: Message):
    room=await service.get_open_room(message.chat.id)
    if not room: await message.answer('در این گروه اتاق فعالی وجود ندارد.'); return
    players=await service.room_players(room['id'])
    labels={'lobby':'ثبت‌نام','intro_day':'روز معارفه','intro_night':'شب معارفه','night':'شب','day':'روز','handshake':'دست‌دادن نهایی','finished':'پایان‌یافته'}
    lines=[f'🎭 اتاق #{room["id"]} — مرحله: {labels.get(room["status"],room["status"])}',f'بازیکنان: {len(players)}']
    lines += [f'{"🟢" if p["alive"] else "⚫"} {p["display_name"]}' for p in players]
    await message.answer('\n'.join(lines))

@router.message(Command('mafia_start', 'مافیا_شروع'))
@router.message(F.text.in_({'مافیا شروع', 'شروع مافیا'}))
async def start(message: Message):
    room=await service.get_open_room(message.chat.id)
    if not room: await message.answer('اول با /mafia_create اتاق بساز.'); return
    try:
        assigned,chat_id=await service.start_room(room['id'],message.from_user.id)
        failures=[]
        players=await service.room_players(room['id'])
        for tg_id,role in assigned:
            try: await message.bot.send_message(tg_id,f'🎭 بازی شروع شد! نقش مخفی تو: {service.ROLE_NAMES[role]}\nبرای اقدام شبانه از /mafia_night استفاده کن. نقش خودت را در گروه فاش نکن.')
            except Exception: failures.append(tg_id)
        if failures:
            await service.cancel_room(room['id'], message.from_user.id, is_admin=True)
            task = _timer_tasks.get(room['id'])
            if task and not task.done(): task.cancel()
            await message.answer('⚠️ ارسال نقش خصوصی برای یک یا چند نفر ناموفق بود؛ برای جلوگیری از ادامهٔ بازی با نقش‌های ناقص، اتاق خودکار لغو شد. همهٔ بازیکنان باید ابتدا در خصوصی ربات /start را بزنند؛ سپس اتاق تازه بسازید.')
        else:
            await message.answer('☀️ روز معارفه شروع شد؛ ۳۰ ثانیه فرصت گفت‌وگو دارید. در این مرحله چالش و رأی‌گیری انجام نمی‌شود. سپس شب معارفه به‌صورت خودکار آغاز می‌شود.')
            await arm_timer(message.bot,room['id'],chat_id,'intro_day')
    except ValueError as e: await message.answer(str(e))

@router.message(Command('mafia_night', 'مافیا_شب'))
@router.message(F.text.in_({'مافیا شب', 'شب مافیا'}))
async def night(message: Message):
    if message.chat.type!='private': await message.answer('برای دیدن انتخاب‌های شب، این دستور را در خصوصی ربات بفرست.'); return
    async with db().acquire() as conn:
        p=await conn.fetchrow("SELECT rp.room_id,rp.role,rp.alive,gr.status FROM room_players rp JOIN game_rooms gr ON gr.id=rp.room_id WHERE rp.telegram_id=$1 AND gr.game_type='mafia' AND gr.status='night' AND rp.alive=TRUE ORDER BY rp.room_id DESC LIMIT 1",message.from_user.id)
        if not p: await message.answer('در حال حاضر اقدام شبانه‌ای برایت فعال نیست.'); return
        players=await service.room_players(p['room_id']); living=[x for x in players if x['alive']]
        if p['role'] not in ('mafia','doctor','detective'): await message.answer('نقش تو اقدام شبانه ندارد.'); return
        kb=target_keyboard(p['room_id'],[x for x in living if x['telegram_id']!=message.from_user.id or p['role']=='doctor'],'act')
        await message.answer(f'🌙 نقش تو: {service.ROLE_NAMES[p["role"]]} — هدف را انتخاب کن:',reply_markup=kb)

@router.callback_query(F.data.startswith('ma:act:'))
async def action_callback(call: CallbackQuery):
    _,_,room_id,target_id=call.data.split(':')
    try:
        role=await service.submit_night_action(int(room_id),call.from_user.id,int(target_id))
        await call.answer('اقدامت ثبت شد!')
        if call.message: await call.message.edit_text('✅ اقدام شبانه ثبت شد. برای تغییر هدف، دوباره /mafia_night را بزن.')
    except ValueError as e: await call.answer(str(e),show_alert=True)

@router.message(Command('mafia_vote'))
async def vote(message: Message):
    parts=(message.text or '').split()
    if len(parts)!=2 or not parts[1].isdigit(): await message.answer('روش رأی: /mafia_vote شناسه_تلگرام'); return
    room=await service.get_open_room(message.chat.id)
    if not room: await message.answer('اتاق فعالی پیدا نشد.'); return
    try:
        await service.submit_vote(room['id'],message.from_user.id,int(parts[1])); await message.answer('✅ رأی تو ثبت شد.')
    except ValueError as e: await message.answer(str(e))

@router.message(Command('mafia_resolve'))
async def resolve(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        room=await service.get_open_room(message.chat.id)
        if not room or room['creator_id'] != message.from_user.id:
            await message.answer('فقط سازندهٔ اتاق یا مدیر ربات می‌تواند این دستور را اجرا کند.'); return
    room=await service.get_open_room(message.chat.id)
    if not room: await message.answer('اتاق فعالی وجود ندارد.'); return
    if room['status']=='night':
        victim,saved,detective,alive,win=await service.resolve_night(room['id'])
        msg='☀️ شب تمام شد. '+('کسی حذف نشد.' if victim is None or saved else 'یک بازیکن حذف شد.')
        if win: msg+='\n🏆 '+('مافیا برنده شد.' if win=='mafia' else 'شهروندان برنده شدند.')
        else: await arm_timer(message.bot,room['id'],message.chat.id,'day')
        await message.answer(msg)
    elif room['status']=='day':
        eliminated,players,win=await service.resolve_day(room['id'])
        msg='🗳️ رأی‌گیری انجام شد. '+('بازیکنی حذف نشد.' if not eliminated else 'یک بازیکن حذف شد.')
        if win: msg+='\n🏆 '+('مافیا برنده شد.' if win=='mafia' else 'شهروندان برنده شدند.')
        else: await send_night_prompts(message.bot,room['id']); await arm_timer(message.bot,room['id'],message.chat.id,'night')
        await message.answer(msg)
    else: await message.answer('اتاق در مرحلهٔ قابل جمع‌بندی نیست.')


@router.message(Command('mafia_handshake_done'))
async def handshake_done(message: Message):
    if message.chat.type == 'private':
        await message.answer('این دستور را در گروه بازی بفرست.')
        return
    room = await service.get_open_room(message.chat.id)
    if not room or room['status'] != 'handshake':
        await message.answer('اتاق در مرحلهٔ دست‌دادن نهایی نیست.')
        return
    try:
        await service.begin_handshake(room['id'], message.from_user.id, message.from_user.id in ADMIN_IDS)
        task = _timer_tasks.get(room['id'])
        if task and not task.done(): task.cancel()
        await message.answer(f'🌙 شب بعدی شروع شد؛ {NIGHT_SECONDS} ثانیه برای اقدام‌ها فرصت دارید.')
        await send_night_prompts(message.bot, room['id'])
        await arm_timer(message.bot, room['id'], message.chat.id, 'night')
    except ValueError as e:
        await message.answer(str(e))

@router.message(F.text == 'چالش')
async def exact_challenge(message: Message):
    if message.chat.type == 'private':
        await message.answer('برای چالش، در گروه بازی روی پیام بازیکن موردنظر Reply کن و دقیقاً «چالش» بفرست.')
        return
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.answer('برای ثبت چالش، روی پیام بازیکن موردنظر Reply کن و فقط «چالش» بفرست.')
        return
    room = await service.get_open_room(message.chat.id)
    if not room:
        await message.answer('در این گروه اتاق فعالی وجود ندارد.')
        return
    try:
        target_name = await service.add_challenge(room['id'], message.from_user.id, message.reply_to_message.from_user.id)
        await message.answer(f'⚖️ {target_name} به چالش کشیده شد. برای اینکه در رأی‌گیری هدف معتبری باشد، بازیکن زندهٔ دیگری باید با Reply به پیام او دقیقاً «پوشش» بفرستد.')
    except ValueError as e:
        await message.answer(str(e))

@router.message(F.text == 'پوشش')
async def exact_cover(message: Message):
    if message.chat.type == 'private':
        await message.answer('برای پوشش، در گروه بازی روی پیام بازیکن چالش‌شده Reply کن و دقیقاً «پوشش» بفرست.')
        return
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.answer('برای ثبت پوشش، روی پیام بازیکن چالش‌شده Reply کن و فقط «پوشش» بفرست.')
        return
    room = await service.get_open_room(message.chat.id)
    if not room:
        await message.answer('در این گروه اتاق فعالی وجود ندارد.')
        return
    try:
        target_name = await service.add_cover(room['id'], message.from_user.id, message.reply_to_message.from_user.id)
        await message.answer(f'🛡️ برای {target_name} پوشش ثبت شد. این بازیکن اکنون می‌تواند هدف رأی‌گیری باشد.')
    except ValueError as e:
        await message.answer(str(e))

@router.message(Command('mafia_ballot'))
async def ballot(message: Message):
    if message.chat.type == 'private':
        await message.answer('این دستور را در گروه بازی بفرست.')
        return
    room = await service.get_open_room(message.chat.id)
    if not room or room['status'] != 'day':
        await message.answer('برگهٔ رأی فقط در مرحلهٔ روز در دسترس است.')
        return
    players = await service.room_players(room['id'])
    living = [p for p in players if p['alive']]
    state = service.decode_state(room['state'])
    eligible_ids = service.eligible_vote_target_ids(state, [p['telegram_id'] for p in living])
    eligible = [p for p in living if p['telegram_id'] in eligible_ids]
    if not eligible:
        await message.answer('هنوز هدفی برای رأی‌گیری معتبر نیست؛ در صورت وجود چالش، هدف باید پوشش بگیرد.')
        return
    await message.answer('🗳️ هدف رأی خود را انتخاب کن:', reply_markup=target_keyboard(room['id'], eligible, 'vote'))

@router.callback_query(F.data.startswith('ma:vote:'))
async def vote_callback(call: CallbackQuery):
    _, _, room_id, target_id = call.data.split(':')
    try:
        await service.submit_vote(int(room_id), call.from_user.id, int(target_id))
        await call.answer('رأی ثبت شد.')
        if call.message:
            await call.message.edit_text('✅ رأی تو ثبت شد. تا پایان زمان رأی‌گیری می‌توانی با /mafia_ballot آن را تغییر بدهی.')
    except ValueError as e:
        await call.answer(str(e), show_alert=True)

@router.message(Command('mafia_report'))
async def report(message: Message):
    details = (message.text or '').partition(' ')[2].strip()
    if len(details) < 5:
        await message.answer('روش استفاده: /mafia_report توضیح تخلف یا مشکل (حداقل ۵ نویسه)')
        return
    room = await service.get_open_room(message.chat.id) if message.chat.type != 'private' else None
    await service.report_violation(room['id'] if room else None, message.from_user.id, message.chat.id, details)
    await message.answer('📨 گزارش ثبت شد و برای بررسی مدیران در فهرست گزارش‌ها قرار گرفت. از ارسال اطلاعات خصوصی دیگران خودداری کن.')

@router.message(Command('mafia_reports'))
async def reports(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer('این دستور مخصوص مدیر ربات است.')
        return
    items = await service.recent_reports(10)
    if not items:
        await message.answer('گزارشی ثبت نشده است.')
        return
    lines = ['📋 آخرین گزارش‌ها:']
    for item in items:
        details = item['details']
        if isinstance(details, str):
            import json
            details = json.loads(details)
        lines.append(f"#{item['id']} | کاربر {item['actor_id']} | اتاق {details.get('room_id')} | {details.get('details','')[:220]}")
    await message.answer('\n'.join(lines))

@router.message(Command('mafia_cancel', 'مافیا_لغو'))
@router.message(F.text.in_({'مافیا لغو', 'لغو مافیا'}))
async def cancel(message: Message):
    if message.chat.type == 'private':
        await message.answer('این دستور را در گروه اتاق بفرست.')
        return
    room = await service.get_open_room(message.chat.id)
    if not room:
        await message.answer('اتاق فعالی وجود ندارد.')
        return
    try:
        await service.cancel_room(room['id'], message.from_user.id, message.from_user.id in ADMIN_IDS)
        task = _timer_tasks.get(room['id'])
        if task and not task.done(): task.cancel()
        await message.answer('🛑 اتاق لغو شد.')
    except ValueError as e:
        await message.answer(str(e))

@router.message(Command('mafia_rules', 'مافیا_قوانین'))
@router.message(F.text.in_({'مافیا قوانین', 'قوانین مافیا'}))
async def rules(message: Message):
    await message.answer(
        '📜 قوانین فعلی مافیای پادشاهان زیرزمین\n'
        '• ثبت‌نام و شروع بازی با دستورهای /mafia_create و /mafia_join و /mafia_start انجام می‌شود.\n'
        '• نقش‌ها خصوصی‌اند؛ فاش‌کردن نقش خود یا دیگری ممنوع است.\n'
        '• اقدام شبانه فقط از خصوصی ربات انجام می‌شود.\n'
        '• روز معارفه ۳۰ ثانیه است و در آن چالش و رأی‌گیری نداریم؛ سپس شب معارفهٔ ۳۰ ثانیه‌ای برگزار می‌شود.\n'
        '• وقتی سه بازیکن زنده باقی بمانند، مرحلهٔ دست‌دادن آغاز می‌شود؛ پایان آن با /mafia_handshake_done ثبت می‌شود.\n'
        '• روزها برای چالش، پوشش و رأی‌گیری استفاده می‌شوند.\n'
        '• برای چالش، روی پیام بازیکن زنده Reply کن و دقیقاً «چالش» بفرست.\n'
        '• هدف چالش‌شده فقط پس از دریافت پوشش از بازیکن زندهٔ دیگری، در رأی‌گیری هدف معتبر می‌شود. برای پوشش، روی پیام همان بازیکن Reply کن و دقیقاً «پوشش» بفرست.\n'
        '• اگر در روز هیچ چالشی ثبت نشود، رأی‌گیری میان تمام بازیکنان زنده انجام می‌شود.\n'
        '• گزارش تخلف: /mafia_report توضیح\n'
        '• این نسخه آزمایشی است؛ تشخیص خودکار همهٔ افشاگری‌ها یا خروج از خصوصی هنوز پیاده‌سازی نشده است.'
    )
