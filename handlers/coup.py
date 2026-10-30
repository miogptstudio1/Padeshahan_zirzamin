from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import F
import asyncio, time
from core.database import upsert_user
from games.coup import service
from games.coup.engine import ROLE_FA, ACTION_FA, current_player, living_ids

router = Router()
_claim_tasks: dict[int, asyncio.Task] = {}

async def _claim_timeout(bot, room_id: int, chat_id: int, deadline: float):
    try:
        await asyncio.sleep(max(0, deadline - time.time()))
        room = await service.room(room_id)
        if not room or room['status'] != 'playing': return
        state = service.decode(room['state'])
        claim = state.get('pending_claim') or {}
        if not claim or claim.get('phase') not in {'challenge', 'block', 'block_challenge'}: return
        if float(claim.get('deadline', 0)) > time.time() + 0.5: return
        actor = claim.get('blocker') if claim.get('phase') == 'block_challenge' else claim.get('actor')
        state, result = await service.mutate(room_id, int(actor), 'accept')
        if result.get('blocked'):
            msg = '⏱️ زمان چالش مسدودسازی تمام شد؛ مسدودسازی پذیرفته شد و اقدام انجام نشد.'
        elif result.get('action') == 'assassinate':
            msg = '⏱️ زمان چالش تمام شد؛ ترور انجام شد. هدف باید در خصوصی /coup_lose 1 یا /coup_lose 2 را بزند.'
            if state.get('pending_loss'):
                try: await bot.send_message(int(state['pending_loss']['target']), '⚔️ ترور علیه تو نهایی شد. برای انتخاب کارت ازدست‌رفته /coup_lose 1 یا /coup_lose 2 را بزن.')
                except Exception: pass
        elif result.get('needs_exchange_choice'):
            msg = '⏱️ زمان چالش تمام شد؛ تبادل پذیرفته شد. اعلام‌کننده باید کارت‌های نهایی را در خصوصی انتخاب کند.'
            try: await bot.send_message(int(actor), 'کارت‌های پیشنهادی: ' + '، '.join(ROLE_FA[c] for c in result['offered']) + '\n/coup_exchange role1 role2')
            except Exception: pass
        else:
            msg = '⏱️ زمان چالش تمام شد؛ اقدام پذیرفته و اجرا شد.'
        await bot.send_message(chat_id, msg)
        if state.get('status') == 'finished':
            rows = await service.players(room_id)
            winner = next((p['display_name'] for p in rows if str(p['telegram_id']) == state.get('winner')), 'بازیکن')
            await bot.send_message(chat_id, f'🏆 بازی تمام شد! برنده: {winner}')
    except asyncio.CancelledError:
        raise
    except Exception:
        # A concurrent manual action may have already resolved the claim.
        return
    finally:
        task = _claim_tasks.get(room_id)
        if task is asyncio.current_task(): _claim_tasks.pop(room_id, None)

def arm_claim_timer(bot, room_id: int, chat_id: int, state: dict):
    old = _claim_tasks.pop(room_id, None)
    if old and old is not asyncio.current_task(): old.cancel()
    claim = state.get('pending_claim') or {}
    if claim.get('phase') in {'challenge', 'block', 'block_challenge'}:
        deadline = float(claim.get('deadline') or (time.time() + 20))
        _claim_tasks[room_id] = asyncio.create_task(_claim_timeout(bot, room_id, chat_id, deadline))

async def restore_coup_timers(bot) -> int:
    restored = 0
    for room in await service.active_claim_rooms():
        state = service.decode(room['state'])
        claim = state.get('pending_claim') or {}
        if claim.get('phase') in {'challenge', 'block', 'block_challenge'}:
            arm_claim_timer(bot, room['id'], room['chat_id'], state)
            restored += 1
    return restored

def claim_keyboard(room_id: int, claim: dict):
    buttons = []
    if claim.get('phase') in {'challenge', 'block_challenge'}:
        buttons.append([InlineKeyboardButton(text='⚖️ چالش', callback_data=f'coup:challenge:{room_id}')])
    if claim.get('phase') == 'block_challenge':
        buttons.append([InlineKeyboardButton(text='✅ قبول مسدودسازی', callback_data=f'coup:accept:{room_id}')])
    elif claim.get('phase') in {'challenge', 'block'}:
        buttons.append([InlineKeyboardButton(text='✅ قبول اقدام', callback_data=f'coup:accept:{room_id}')])
        roles = {'foreign_aid':['duke'], 'steal':['captain','ambassador'], 'assassinate':['contessa']}.get(claim.get('action'), [])
        for role in roles:
            buttons.append([InlineKeyboardButton(text=f'🛡️ مسدودسازی با {ROLE_FA[role]}', callback_data=f'coup:block:{room_id}:{role}')])
    return InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None

def action_keyboard(room_id: int, target_ids: list[tuple[str, str]] | None = None):
    rows = [
        [InlineKeyboardButton(text='🪙 درآمد +۱', callback_data=f'coup:act:{room_id}:income'), InlineKeyboardButton(text='💰 کمک خارجی +۲', callback_data=f'coup:act:{room_id}:foreign_aid')],
        [InlineKeyboardButton(text='👑 مالیات +۳', callback_data=f'coup:act:{room_id}:tax'), InlineKeyboardButton(text='🔄 تبادل کارت', callback_data=f'coup:act:{room_id}:exchange')],
    ]
    if target_ids:
        rows += [[InlineKeyboardButton(text=f'🎯 {name}', callback_data=f'coup:target:{room_id}:steal:{pid}')] for pid, name in target_ids]
    rows.append([InlineKeyboardButton(text='⚔️ انتخاب هدف ترور', callback_data=f'coup:targets:{room_id}:assassinate'), InlineKeyboardButton(text='💥 انتخاب هدف کودتا', callback_data=f'coup:targets:{room_id}:coup')])
    return InlineKeyboardMarkup(inline_keyboard=rows)

async def display_name(message: Message):
    return (message.from_user.full_name or str(message.from_user.id))[:80]

@router.message(Command('coup_create', 'کودتا_بساز'))
@router.message(F.text.in_({'کودتا بساز', 'ساخت کودتا', 'اتاق کودتا'}))
async def coup_create(message: Message):
    if not message.chat or message.chat.type == 'private':
        await message.answer('این دستور را داخل گروه بازی اجرا کن.'); return
    try:
        rid = await service.create_room(message.chat.id, message.from_user.id, await display_name(message))
        await message.answer(f'🃏 اتاق کودتا #{rid} ساخته شد!\nبرای پیوستن: /coup_join\nبرای شروع (حداقل ۲ نفر): /coup_start')
    except ValueError as exc: await message.answer(str(exc))

@router.message(Command('coup_join', 'کودتا_جوین'))
@router.message(F.text.in_({'کودتا جوین', 'جوین کودتا', 'پیوستن کودتا'}))
async def coup_join(message: Message):
    if not message.chat or message.chat.type == 'private':
        await message.answer('برای پیوستن، دستور را در گروه بازی اجرا کن.'); return
    room = await service.get_open_room(message.chat.id)
    if not room: await message.answer('اتاق کودتای بازی‌ای پیدا نشد. ابتدا /coup_create را بزن.'); return
    try:
        count = await service.join_room(room['id'], message.from_user.id, await display_name(message))
        await upsert_user(message.from_user.id, message.from_user.username, await display_name(message))
        await message.answer(f'✅ ثبت‌نام شدی؛ تعداد بازیکنان: {count}/6')
    except ValueError as exc: await message.answer(str(exc))

@router.message(Command('coup_start', 'کودتا_شروع'))
@router.message(F.text.in_({'کودتا شروع', 'شروع کودتا'}))
async def coup_start(message: Message):
    if not message.chat or message.chat.type == 'private':
        await message.answer('این دستور را داخل گروه اتاق اجرا کن.'); return
    room = await service.get_open_room(message.chat.id)
    if not room: await message.answer('اتاق کودتای فعالی وجود ندارد.'); return
    if room['creator_id'] != message.from_user.id:
        await message.answer('فقط سازندهٔ اتاق می‌تواند بازی را شروع کند.'); return
    rows = await service.players(room['id'])
    # Preflight private delivery so a player who has not opened the bot cannot be stranded without cards.
    failed = []
    for p in rows:
        try:
            await message.bot.send_message(p['telegram_id'], 'آماده‌سازی بازی کودتا انجام شد؛ کارت‌های مخفی پس از شروع ارسال می‌شوند.')
        except Exception:
            failed.append(p['display_name'])
    if failed:
        await message.answer('بازی شروع نشد؛ این بازیکنان باید ابتدا در خصوصی ربات /start را بزنند: ' + '، '.join(failed))
        return
    try:
        chat_id, state = await service.start_room(room['id'], message.from_user.id)
    except ValueError as exc: await message.answer(str(exc)); return
    rows = await service.players(room['id'])
    delivered = 0
    for p in rows:
        pdata = state['players'][str(p['telegram_id'])]
        try:
            await message.bot.send_message(p['telegram_id'], '🃏 بازی کودتا شروع شد!\nکارت‌های مخفی تو: ' + '، '.join(ROLE_FA[c] for c in pdata['cards']) + '\nبرای دیدن کارت‌ها: /coup_hand')
            delivered += 1
        except Exception: pass
    turn = current_player(state)
    turn_name = next((p['display_name'] for p in rows if str(p['telegram_id']) == turn), 'بازیکن اول')
    await message.answer(f'🃏 بازی کودتا شروع شد!\nهر بازیکن با ۲ سکه و ۲ کارت نفوذ آغاز می‌کند.\nنوبت اول: {turn_name}\nبرای اقدامات: /coup_help\nکارت خصوصی ارسال‌شده به {delivered} نفر از {len(rows)} نفر.')

@router.message(Command('coup_help', 'کودتا_کمک'))
@router.message(F.text.in_({'کودتا کمک', 'کمک کودتا', 'راهنما کودتا'}))
async def coup_help(message: Message):
    await message.answer('🃏 راهنمای کودتا\n/coup_action income — درآمد +۱\n/coup_action foreign_aid — کمک خارجی +۲\n/coup_action tax — مالیات +۳ (ادعای دوک)\n/coup_action steal شناسه — سرقت تا ۲ سکه (ادعای کاپیتان)\n/coup_action exchange — تبادل کارت (ادعای سفیر)\n/coup_action assassinate شناسه — ترور با ۳ سکه (ادعای آدم‌کش)\n/coup_action coup شناسه — کودتا با ۷ سکه\n/coup_accept — تأیید اقدام یا نهایی‌کردن مسدودسازی\n/coup_challenge — چالش ادعای نقش\n/coup_block duke|captain|ambassador|contessa — ادعای مسدودسازی\n/coup_lose 1 یا /coup_lose 2 — انتخاب کارت ازدست‌رفته در خصوصی\n/coup_exchange role1 role2 — انتخاب کارت‌های تبادل در خصوصی\n/coup_hand — دیدن کارت‌ها در خصوصی\n/coup_status — وضعیت بازی\n/coup_menu — منوی دکمه‌ای اقدامات\n\nپنجرهٔ چالش ۲۰ ثانیه است و پس از پایان، اقدام به‌صورت خودکار نهایی می‌شود.\nترتیب پیشنهادی: اعلام اقدام ← چالش یا مسدودسازی ← /coup_accept برای نهایی‌کردن. چالش‌شده باید کارت ازدست‌رفته را در خصوصی انتخاب کند.')

@router.message(Command('coup_hand', 'کودتا_دست'))
@router.message(F.text.in_({'کودتا دست', 'دست کودتا', 'کارت کودتا'}))
async def coup_hand(message: Message):
    if message.chat.type != 'private':
        await message.answer('برای حفظ محرمانگی، /coup_hand را در خصوصی ربات بزن.'); return
    room = await service.get_open_room_for_player(message.from_user.id)
    if not room: await message.answer('بازی کودتای فعالی برایت پیدا نشد.'); return
    state = service.decode(room['state']); player = state.get('players', {}).get(str(message.from_user.id))
    if not player: await message.answer('در این بازی عضو نیستی.'); return
    await message.answer('🃏 کارت‌ها: ' + ('، '.join(ROLE_FA[c] for c in player['cards']) if player['cards'] else 'هیچ کارت زنده‌ای نداری') + f'\n🪙 سکه: {player["coins"]}\nوضعیت: {"زنده" if player["alive"] else "حذف‌شده"}')

@router.message(Command('coup_status', 'کودتا_وضعیت'))
@router.message(F.text.in_({'کودتا وضعیت', 'وضعیت کودتا'}))
async def coup_status(message: Message):
    if message.chat.type == 'private':
        room = await service.get_open_room_for_player(message.from_user.id)
    else: room = await service.get_open_room(message.chat.id)
    if not room: await message.answer('بازی کودتای فعالی پیدا نشد.'); return
    state = service.decode(room['state']); rows = await service.players(room['id'])
    lines=[]
    for p in rows:
        pdata=state['players'][str(p['telegram_id'])]
        lines.append(f'{"🟢" if pdata["alive"] else "❌"} {p["display_name"]}: {pdata["coins"]} سکه، {len(pdata["cards"])} کارت')
    cur=current_player(state); current=next((p['display_name'] for p in rows if str(p['telegram_id'])==cur),'—')
    await message.answer('📊 وضعیت کودتا\n'+'\n'.join(lines)+f'\n\nنوبت: {current}\nوضعیت: {state.get("status")}')

@router.message(Command('coup_action'))
async def coup_action(message: Message):
    if message.chat.type == 'private':
        await message.answer('اقدام را داخل گروه بازی بفرست تا نتیجه برای همه اعلام شود.'); return
    if not message.text:
        await message.answer('فرمت: /coup_action income'); return
    args=message.text.split()
    if len(args)<2: await message.answer('فرمت: /coup_action income'); return
    action=args[1].lower()
    aliases={'درآمد':'income','کمک':'foreign_aid','مالیات':'tax','سرقت':'steal','تبادل':'exchange','ترور':'assassinate','کودتا':'coup'}
    action=aliases.get(action,action)
    target=None
    if action in {'steal','assassinate','coup'}:
        if len(args)<3 or not args[2].isdigit(): await message.answer('شناسهٔ عددی هدف را هم وارد کن.'); return
        target=int(args[2])
    room=await service.get_open_room(message.chat.id)
    if not room: await message.answer('بازی کودتای فعالی پیدا نشد.'); return
    try:
        state, result=await service.mutate(room['id'],message.from_user.id,action,target)
        arm_claim_timer(message.bot, room['id'], message.chat.id, state)
    except ValueError as exc: await message.answer(str(exc)); return
    if result.get('needs_exchange_choice'):
        await message.answer('🃏 کارت‌های پیشنهادی برای تبادل (در خصوصی): '+', '.join(ROLE_FA[c] for c in result['offered'])+'\nبرای انتخاب دو کارت نهایی از /coup_exchange role1 role2 استفاده کن.')
        try: await message.bot.send_message(message.from_user.id,'کارت‌های پیشنهادی: '+', '.join(ROLE_FA[c] for c in result['offered'])+'\nفرمت: /coup_exchange duke captain')
        except Exception: pass
        return
    actor=next((p['display_name'] for p in await service.players(room['id']) if p['telegram_id']==message.from_user.id),'بازیکن')
    desc=ACTION_FA.get(action,action)
    msg=f'🃏 {actor} اقدام «{desc}» را اعلام کرد.'
    if result.get('pending'):
        claim_role = result.get('claim_role')
        if claim_role: msg += f' ادعای نقش: {ROLE_FA.get(claim_role, claim_role)}.'
        msg += ' اگر کسی چالش ندارد، بازیکن اعلام‌کننده /coup_accept بزند.'
        await message.answer(msg, reply_markup=claim_keyboard(room['id'], state.get('pending_claim') or {})); return
    if action=='income': msg+=' یک سکه گرفت.'
    elif action=='foreign_aid': msg+=' دو سکه گرفت.'
    elif action=='tax': msg+=' سه سکه گرفت.'
    elif action=='steal': msg+=' سرقت انجام شد.'
    elif action in {'assassinate','coup'}: msg+=' هدف باید کارت ازدست‌رفته‌اش را با /coup_lose 1 یا /coup_lose 2 انتخاب کند.'
    await message.answer(msg)
    if action == 'coup' and state.get('pending_loss'):
        try: await message.bot.send_message(int(state['pending_loss']['target']), '💥 هدف کودتا قرار گرفتی. برای انتخاب کارت ازدست‌رفته /coup_lose 1 یا /coup_lose 2 را بزن.')
        except Exception: pass
    if state.get('status')=='finished':
        winner=next((p['display_name'] for p in await service.players(room['id']) if str(p['telegram_id'])==state.get('winner')),'بازیکن')
        await message.answer(f'🏆 بازی تمام شد! برنده: {winner}')

@router.message(Command('coup_accept'))
async def coup_accept(message: Message):
    if message.chat.type == 'private':
        await message.answer('این دستور را در گروه بازی بفرست.'); return
    room = await service.get_open_room(message.chat.id)
    if not room: await message.answer('بازی فعالی پیدا نشد.'); return
    try:
        state, result = await service.mutate(room['id'], message.from_user.id, 'accept')
        arm_claim_timer(message.bot, room['id'], message.chat.id, state)
    except ValueError as exc:
        await message.answer(str(exc)); return
    if result.get('needs_exchange_choice'):
        await message.answer('تبادل اعلام شد؛ کارت‌های پیشنهادی در خصوصی ارسال می‌شوند.')
        try: await message.bot.send_message(message.from_user.id, 'کارت‌های پیشنهادی: ' + '، '.join(ROLE_FA[c] for c in result['offered']) + '\n/coup_exchange role1 role2')
        except Exception: pass
        return
    if result.get('blocked'):
        await message.answer('🛡️ مسدودسازی نهایی شد؛ اقدام اصلی انجام نمی‌شود.')
    elif result.get('action') == 'assassinate':
        await message.answer('⚔️ ترور نهایی شد؛ هدف باید در خصوصی با /coup_lose 1 یا /coup_lose 2 کارت ازدست‌رفته را انتخاب کند.')
        if state.get('pending_loss'):
            try: await message.bot.send_message(int(state['pending_loss']['target']), '⚔️ ترور علیه تو نهایی شد. برای انتخاب کارت ازدست‌رفته /coup_lose 1 یا /coup_lose 2 را بزن.')
            except Exception: pass
    else:
        await message.answer('✅ اقدام نهایی شد.')
    if state.get('status') == 'finished':
        rows = await service.players(room['id']); winner = next((p['display_name'] for p in rows if str(p['telegram_id']) == state.get('winner')), 'بازیکن')
        await message.answer(f'🏆 بازی تمام شد! برنده: {winner}')
    else:
        rows = await service.players(room['id']); cur = current_player(state); name = next((p['display_name'] for p in rows if str(p['telegram_id']) == cur), 'بازیکن')
        if not state.get('pending_loss') and not (state.get('last_action') or {}).get('needs_exchange_choice'):
            await message.answer(f'➡️ نوبت {name} است.')

@router.message(Command('coup_challenge'))
async def coup_challenge(message: Message):
    if message.chat.type == 'private': await message.answer('چالش را در گروه بازی بفرست.'); return
    room = await service.get_open_room(message.chat.id)
    if not room: await message.answer('بازی فعالی پیدا نشد.'); return
    try: state, result = await service.mutate(room['id'], message.from_user.id, 'challenge')
    except ValueError as exc: await message.answer(str(exc)); return
    arm_claim_timer(message.bot, room['id'], message.chat.id, state)
    target = result.get('target')
    await message.answer(f'⚖️ چالش ثبت شد. {target} باید در خصوصی با /coup_lose 1 یا /coup_lose 2 کارت ازدست‌رفته را انتخاب کند.')
    try: await message.bot.send_message(int(target), '⚖️ ادعای نقش تو چالش شده است. در خصوصی /coup_lose 1 یا /coup_lose 2 را بزن.')
    except Exception: pass

@router.message(Command('coup_block'))
async def coup_block(message: Message):
    if message.chat.type == 'private': await message.answer('مسدودسازی را در گروه بازی بفرست.'); return
    args = (message.text or '').split()
    if len(args) != 2: await message.answer('فرمت: /coup_block duke|captain|ambassador|contessa'); return
    role = args[1].lower()
    if role not in {'duke', 'captain', 'ambassador', 'contessa'}:
        await message.answer('نقش معتبر: duke, captain, ambassador, contessa'); return
    room = await service.get_open_room(message.chat.id)
    if not room: await message.answer('بازی فعالی پیدا نشد.'); return
    try: state, _ = await service.mutate(room['id'], message.from_user.id, 'block', exchange_cards=[role])
    except ValueError as exc: await message.answer(str(exc)); return
    arm_claim_timer(message.bot, room['id'], message.chat.id, state)
    await message.answer(f'🛡️ ادعای مسدودسازی با نقش {ROLE_FA[role]} ثبت شد. پنجرهٔ چالش ۲۰ ثانیه است.', reply_markup=claim_keyboard(room['id'], state.get('pending_claim') or {}))

@router.message(Command('coup_lose'))
async def coup_lose(message: Message):
    if not message.text: return
    args=message.text.split()
    if len(args)<2 or args[1] not in {'1','2'}:
        await message.answer('فرمت: /coup_lose 1 یا /coup_lose 2'); return
    if message.chat.type != 'private':
        await message.answer('برای محرمانگی، کارت ازدست‌رفته را در خصوصی ربات انتخاب کن.'); return
    room=await service.get_open_room_for_player(message.from_user.id)
    if not room: await message.answer('بازی فعالی پیدا نشد.'); return
    try:
        state,result=await service.mutate(room['id'],message.from_user.id,'lose',card_index=int(args[1])-1)
        arm_claim_timer(message.bot, room['id'], room['chat_id'], state)
    except ValueError as exc: await message.answer(str(exc)); return
    await message.answer('کارت نفوذت ثبت شد: '+ROLE_FA[result['lost']])
    if state.get('status')=='finished':
        winner=next((p['display_name'] for p in await service.players(room['id']) if str(p['telegram_id'])==state.get('winner')),'بازیکن')
        try: await message.bot.send_message(room['chat_id'],f'🏆 بازی تمام شد! برنده: {winner}')
        except Exception: pass
    else:
        cur=current_player(state); rows=await service.players(room['id']); name=next((p['display_name'] for p in rows if str(p['telegram_id'])==cur),'بازیکن')
        try: await message.bot.send_message(room['chat_id'],f'➡️ کارت ازدست‌رفته ثبت شد. نوبت {name} است.')
        except Exception: pass

@router.message(Command('coup_exchange'))
async def coup_exchange(message: Message):
    if message.chat.type!='private': await message.answer('این دستور را در خصوصی بفرست.'); return
    args=(message.text or '').split()
    if len(args)!=3: await message.answer('فرمت: /coup_exchange duke captain'); return
    mapping={k:k for k in ROLE_FA}
    picks=[mapping.get(args[1].lower()),mapping.get(args[2].lower())]
    if any(not p for p in picks): await message.answer('نام نقش‌ها را انگلیسی وارد کن: duke, assassin, captain, ambassador, contessa'); return
    room=await service.get_open_room_for_player(message.from_user.id)
    if not room: await message.answer('بازی فعالی پیدا نشد.'); return
    try:
        state,result=await service.mutate(room['id'],message.from_user.id,'exchange_choice',exchange_cards=picks)
        arm_claim_timer(message.bot, room['id'], room['chat_id'], state)
    except ValueError as exc: await message.answer(str(exc)); return
    await message.answer('کارت‌های نهایی: '+', '.join(ROLE_FA[c] for c in result['exchange']))
    try:
        cur=current_player(state); rows=await service.players(room['id']); name=next((p['display_name'] for p in rows if str(p['telegram_id'])==cur),'بازیکن')
        await message.bot.send_message(room['chat_id'],f'🔄 تبادل کارت انجام شد. نوبت {name} است.')
    except Exception: pass


@router.message(Command('coup_menu', 'کودتا_منو'))
@router.message(F.text.in_({'کودتا منو', 'منو کودتا'}))
async def coup_menu(message: Message):
    if message.chat.type == 'private':
        room = await service.get_open_room_for_player(message.from_user.id)
        if not room:
            await message.answer('بازی کودتای فعالی برایت پیدا نشد.'); return
        await message.answer('برای اقدامات، این منو را در گروه بازی باز کن تا دکمه‌ها همان‌جا نمایش داده شوند.')
        return
    room = await service.get_open_room(message.chat.id)
    if not room or room['status'] != 'playing':
        await message.answer('بازی فعالی برای نمایش منو پیدا نشد.'); return
    state = service.decode(room['state'])
    players = await service.players(room['id'])
    targets = [(str(p['telegram_id']), p['display_name']) for p in players if str(p['telegram_id']) != str(message.from_user.id) and state.get('players', {}).get(str(p['telegram_id']), {}).get('alive')]
    await message.answer('🃏 منوی تعاملی کودتا — اقدام فقط در نوبت خودت پذیرفته می‌شود.', reply_markup=action_keyboard(room['id'], targets))

@router.callback_query(F.data.startswith('coup:'))
async def coup_buttons(call: CallbackQuery):
    if not call.message or call.message.chat.type == 'private':
        await call.answer('این دکمه را در گروه بازی استفاده کن.', show_alert=True); return
    parts = call.data.split(':')
    try: room_id = int(parts[2])
    except (ValueError, IndexError):
        await call.answer('دکمه نامعتبر است.', show_alert=True); return
    room = await service.room(room_id)
    if not room or room['chat_id'] != call.message.chat.id or room['status'] != 'playing':
        await call.answer('این اتاق دیگر فعال نیست.', show_alert=True); return
    state = service.decode(room['state'])
    try:
        if parts[1] == 'act':
            action = parts[3]
            if action in {'steal', 'assassinate', 'coup'}:
                rows = await service.players(room_id)
                buttons = [[InlineKeyboardButton(text=p['display_name'], callback_data=f'coup:target:{room_id}:{action}:{p["telegram_id"]}')] for p in rows if str(p['telegram_id']) != str(call.from_user.id) and state.get('players', {}).get(str(p['telegram_id']), {}).get('alive')]
                await call.message.answer('هدف را انتخاب کن:', reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)); await call.answer(); return
            state, result = await service.mutate(room_id, call.from_user.id, action)
        elif parts[1] == 'targets':
            action = parts[3]
            rows = await service.players(room_id)
            buttons = [[InlineKeyboardButton(text=p['display_name'], callback_data=f'coup:target:{room_id}:{action}:{p["telegram_id"]}')] for p in rows if str(p['telegram_id']) != str(call.from_user.id) and state.get('players', {}).get(str(p['telegram_id']), {}).get('alive')]
            await call.message.answer('هدف را انتخاب کن:', reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)); await call.answer(); return
        elif parts[1] == 'target':
            action, target = parts[3], int(parts[4])
            state, result = await service.mutate(room_id, call.from_user.id, action, target)
        elif parts[1] == 'challenge':
            state, result = await service.mutate(room_id, call.from_user.id, 'challenge')
        elif parts[1] == 'accept':
            state, result = await service.mutate(room_id, call.from_user.id, 'accept')
        elif parts[1] == 'block':
            state, result = await service.mutate(room_id, call.from_user.id, 'block', exchange_cards=[parts[3]])
        else:
            await call.answer('دکمه ناشناخته است.', show_alert=True); return
        arm_claim_timer(call.bot, room_id, room['chat_id'], state)
        await call.answer('انجام شد.')
        if result.get('pending'):
            text = '⏳ اقدام در انتظار پاسخ است. پنجرهٔ چالش ۲۰ ثانیه است.'
            await call.message.answer(text, reply_markup=claim_keyboard(room_id, state.get('pending_claim') or {}))
        else:
            if result.get('action') == 'challenge' and state.get('pending_loss'):
                loser = int(state['pending_loss']['target'])
                await call.message.answer(f'⚖️ نتیجهٔ چالش مشخص شد؛ بازیکن {loser} باید یک کارت نفوذ از دست بدهد و در خصوصی /coup_lose 1 یا /coup_lose 2 را بزند.')
                try: await call.bot.send_message(loser, '⚖️ چالش انجام شد. برای انتخاب کارت ازدست‌رفته /coup_lose 1 یا /coup_lose 2 را بزن.')
                except Exception: pass
            elif result.get('needs_exchange_choice'):
                await call.message.answer('تبادل شروع شد؛ کارت‌های پیشنهادی در خصوصی برایت ارسال می‌شوند.')
                try: await call.bot.send_message(call.from_user.id, 'کارت‌های پیشنهادی: ' + '، '.join(ROLE_FA[c] for c in result['offered']) + '\n/coup_exchange role1 role2')
                except Exception: pass
            elif result.get('blocked'):
                await call.message.answer('🛡️ مسدودسازی پذیرفته شد؛ اقدام اصلی اجرا نشد.')
            elif state.get('pending_loss') and result.get('action') in {'assassinate', 'coup'}:
                target = int(state['pending_loss']['target'])
                await call.message.answer('⚔️ هدف باید کارت ازدست‌رفته را در خصوصی انتخاب کند.')
                try: await call.bot.send_message(target, 'برای انتخاب کارت ازدست‌رفته /coup_lose 1 یا /coup_lose 2 را بزن.')
                except Exception: pass
            else:
                await call.message.answer('✅ اقدام اجرا شد. برای وضعیت جدید /coup_status را بزن.')
    except ValueError as exc:
        await call.answer(str(exc), show_alert=True)
