import json, random
from datetime import datetime, timezone
from core.database import db
from config import MIN_PLAYERS, MAX_PLAYERS

ROLE_NAMES = {'mafia':'مافیا', 'doctor':'پزشک', 'detective':'کارآگاه', 'citizen':'شهروند'}

def decode_state(value):
    if isinstance(value, str): return json.loads(value or '{}')
    return value or {}

def choose_mafia_target(actions):
    """Return the unique most-voted night target, or None on no votes/tie."""
    from collections import Counter
    targets = [int(a['target']) for a in actions.values() if a.get('role') == 'mafia' and a.get('target') is not None]
    if not targets:
        return None
    counts = Counter(targets)
    target, count = counts.most_common(1)[0]
    return target if list(counts.values()).count(count) == 1 else None

def eligible_vote_target_ids(state, living_ids):
    """Return the currently vote-eligible IDs according to challenge/cover rules."""
    challenges = state.get('challenges', [])
    if not challenges:
        return set(int(i) for i in living_ids)
    covers = state.get('covers', {})
    return {int(c['target_id']) for c in challenges
            if str(c['target_id']) in covers and int(c['target_id']) in {int(i) for i in living_ids}}

async def open_room(chat_id: int, creator_id: int, name: str) -> int:
    async with db().acquire() as conn:
        async with conn.transaction():
            exists = await conn.fetchval("SELECT id FROM game_rooms WHERE chat_id=$1 AND game_type='mafia' AND status IN ('lobby','intro_day','intro_night','night','day','handshake') FOR UPDATE", chat_id)
            if exists: raise ValueError('در این گروه یک اتاق مافیای فعال وجود دارد.')
            room_id = await conn.fetchval("INSERT INTO game_rooms(game_type,chat_id,creator_id,status,state) VALUES('mafia',$1,$2,'lobby','{}'::jsonb) RETURNING id", chat_id, creator_id)
            await conn.execute("INSERT INTO room_players(room_id,telegram_id,display_name) VALUES($1,$2,$3)", room_id, creator_id, name)
            return room_id

async def get_open_room(chat_id: int):
    async with db().acquire() as conn:
        return await conn.fetchrow("SELECT * FROM game_rooms WHERE chat_id=$1 AND game_type='mafia' AND status IN ('lobby','intro_day','intro_night','night','day','handshake') ORDER BY id DESC LIMIT 1", chat_id)

async def join_room(room_id: int, tg_id: int, name: str):
    async with db().acquire() as conn:
        async with conn.transaction():
            room = await conn.fetchrow('SELECT * FROM game_rooms WHERE id=$1 FOR UPDATE', room_id)
            if not room or room['status'] != 'lobby': raise ValueError('ثبت‌نام این اتاق بسته شده است.')
            count = await conn.fetchval('SELECT COUNT(*) FROM room_players WHERE room_id=$1', room_id)
            if count >= MAX_PLAYERS: raise ValueError(f'ظرفیت اتاق {MAX_PLAYERS} نفر است.')
            try:
                await conn.execute('INSERT INTO room_players(room_id,telegram_id,display_name) VALUES($1,$2,$3)', room_id,tg_id,name)
            except Exception as e:
                if 'unique' in str(e).lower(): raise ValueError('قبلاً در این اتاق ثبت‌نام کرده‌ای.')
                raise
            return count + 1

async def room_players(room_id: int):
    async with db().acquire() as conn:
        return await conn.fetch('SELECT * FROM room_players WHERE room_id=$1 ORDER BY joined_at', room_id)

async def start_room(room_id: int, actor_id: int):
    async with db().acquire() as conn:
        async with conn.transaction():
            room = await conn.fetchrow('SELECT * FROM game_rooms WHERE id=$1 FOR UPDATE', room_id)
            if not room or room['status'] != 'lobby': raise ValueError('این اتاق در مرحلهٔ ثبت‌نام نیست.')
            if room['creator_id'] != actor_id: raise ValueError('فقط سازندهٔ اتاق می‌تواند بازی را شروع کند.')
            players = await conn.fetch('SELECT * FROM room_players WHERE room_id=$1', room_id)
            if len(players) < MIN_PLAYERS: raise ValueError(f'برای شروع حداقل {MIN_PLAYERS} بازیکن لازم است.')
            ids = [p['telegram_id'] for p in players]; random.shuffle(ids)
            roles = ['mafia']
            if len(ids) >= 7: roles += ['mafia']
            roles += ['doctor','detective']
            roles += ['citizen'] * (len(ids)-len(roles))
            random.shuffle(roles)
            for tg_id, role in zip(ids, roles):
                await conn.execute('UPDATE room_players SET role=$3, alive=TRUE WHERE room_id=$1 AND telegram_id=$2', room_id,tg_id,role)
            state = {'round':1,'phase_started_at':datetime.now(timezone.utc).isoformat(),'night_actions':{},'votes':{},'challenges':[],'covers':{},'last_healed':None,'last_attacked':None,'intro_day_done':False,'intro_night_done':False}
            await conn.execute("UPDATE game_rooms SET status='intro_day',state=$2::jsonb,updated_at=NOW() WHERE id=$1", room_id,json.dumps(state))
            return list(zip(ids, roles)), room['chat_id']

async def get_room(room_id: int):
    async with db().acquire() as conn: return await conn.fetchrow('SELECT * FROM game_rooms WHERE id=$1', room_id)

async def active_rooms():
    """Return active Mafia rooms so in-memory phase timers can be rebuilt after restart."""
    async with db().acquire() as conn:
        return await conn.fetch("SELECT * FROM game_rooms WHERE game_type='mafia' AND status IN ('intro_day','intro_night','night','day','handshake') ORDER BY id")

async def advance_intro(room_id: int, expected: str, next_status: str):
    """Advance a timed introduction stage atomically."""
    allowed = {('intro_day', 'intro_night'), ('intro_night', 'night'), ('handshake', 'night')}
    if (expected, next_status) not in allowed:
        raise ValueError('انتقال مرحله معتبر نیست.')
    async with db().acquire() as conn:
        async with conn.transaction():
            room = await conn.fetchrow('SELECT * FROM game_rooms WHERE id=$1 FOR UPDATE', room_id)
            if not room or room['status'] != expected:
                return None
            state = decode_state(room['state'])
            state['phase_started_at'] = datetime.now(timezone.utc).isoformat()
            if expected == 'intro_day': state['intro_day_done'] = True
            if expected == 'intro_night': state['intro_night_done'] = True
            if next_status == 'night':
                state['night_actions'] = {}
                state['votes'] = {}
            await conn.execute('UPDATE game_rooms SET status=$2,state=$3::jsonb,updated_at=NOW() WHERE id=$1', room_id, next_status, json.dumps(state))
            return room['chat_id']

async def begin_handshake(room_id: int, actor_id: int, is_admin: bool = False):
    async with db().acquire() as conn:
        async with conn.transaction():
            room = await conn.fetchrow('SELECT * FROM game_rooms WHERE id=$1 FOR UPDATE', room_id)
            if not room or room['status'] != 'handshake': raise ValueError('اتاق در مرحلهٔ دست‌دادن نیست.')
            if not is_admin and room['creator_id'] != actor_id: raise ValueError('فقط سازنده یا مدیر می‌تواند پایان دست‌دادن را ثبت کند.')
            state = decode_state(room['state']); state['phase_started_at'] = datetime.now(timezone.utc).isoformat()
            state['night_actions'] = {}; state['votes'] = {}; state['handshake_completed'] = True
            await conn.execute("UPDATE game_rooms SET status='night',state=$2::jsonb,updated_at=NOW() WHERE id=$1", room_id, json.dumps(state))
            return room['chat_id']

async def submit_night_action(room_id: int, actor_id: int, target_id: int):
    async with db().acquire() as conn:
        async with conn.transaction():
            room = await conn.fetchrow('SELECT * FROM game_rooms WHERE id=$1 FOR UPDATE', room_id)
            if not room or room['status'] != 'night': raise ValueError('الان زمان اقدام شبانه نیست.')
            player = await conn.fetchrow('SELECT * FROM room_players WHERE room_id=$1 AND telegram_id=$2',room_id,actor_id)
            target = await conn.fetchrow('SELECT * FROM room_players WHERE room_id=$1 AND telegram_id=$2',room_id,target_id)
            if not player or not player['alive'] or player['role'] not in ('mafia','doctor','detective'): raise ValueError('نقش تو اجازهٔ اقدام شبانه ندارد یا حذف شده‌ای.')
            if not target or not target['alive']: raise ValueError('هدف انتخابی معتبر نیست.')
            if player['role'] == 'mafia':
                if actor_id == target_id:
                    raise ValueError('نمی‌توانی خودت را هدف بگیری.')
                teammate = await conn.fetchval("SELECT EXISTS(SELECT 1 FROM room_players WHERE room_id=$1 AND telegram_id=$2 AND role='mafia' AND alive=TRUE)", room_id, target_id)
                if teammate:
                    raise ValueError('مافیا نمی‌تواند هم‌تیمی زندهٔ خودش را هدف قرار دهد.')
            if player['role'] == 'detective' and actor_id == target_id:
                raise ValueError('کارآگاه نمی‌تواند خودش را بررسی کند.')
            state = decode_state(room['state']); actions = state.setdefault('night_actions',{})
            actions[str(actor_id)] = {'role':player['role'],'target':target_id}
            await conn.execute('UPDATE game_rooms SET state=$2::jsonb,updated_at=NOW() WHERE id=$1',room_id,json.dumps(state))
            return player['role']

async def submit_vote(room_id: int, actor_id: int, target_id: int):
    async with db().acquire() as conn:
        async with conn.transaction():
            room = await conn.fetchrow('SELECT * FROM game_rooms WHERE id=$1 FOR UPDATE',room_id)
            if not room or room['status'] != 'day': raise ValueError('الان مرحلهٔ رأی‌گیری نیست.')
            player = await conn.fetchrow('SELECT * FROM room_players WHERE room_id=$1 AND telegram_id=$2',room_id,actor_id)
            target = await conn.fetchrow('SELECT * FROM room_players WHERE room_id=$1 AND telegram_id=$2',room_id,target_id)
            if not player or not player['alive']: raise ValueError('بازیکن حذف‌شده نمی‌تواند رأی بدهد.')
            if not target or not target['alive']: raise ValueError('هدف رأی‌گیری زنده نیست.')
            state = decode_state(room['state']); challenges = state.get('challenges', [])
            if challenges:
                eligible = {int(c['target_id']) for c in challenges if str(c['target_id']) in state.get('covers', {})}
                if target_id not in eligible:
                    raise ValueError('در این روز فقط می‌توانی به هدفی رأی بدهی که چالش شده و پوشش معتبر دارد.')
            state.setdefault('votes',{})[str(actor_id)] = target_id
            await conn.execute('UPDATE game_rooms SET state=$2::jsonb,updated_at=NOW() WHERE id=$1',room_id,json.dumps(state))

async def resolve_night(room_id: int):
    async with db().acquire() as conn:
        async with conn.transaction():
            room = await conn.fetchrow('SELECT * FROM game_rooms WHERE id=$1 FOR UPDATE',room_id)
            if not room or room['status'] != 'night': raise ValueError('اتاق در مرحلهٔ شب نیست.')
            state=decode_state(room['state']); actions=state.get('night_actions',{})
            doctor_targets=[int(a['target']) for a in actions.values() if a.get('role')=='doctor']
            victim=choose_mafia_target(actions)
            if victim and victim not in doctor_targets:
                await conn.execute('UPDATE room_players SET alive=FALSE WHERE room_id=$1 AND telegram_id=$2',room_id,victim)
            detective_result=[]
            for actor, action in actions.items():
                if action.get('role')=='detective':
                    target=await conn.fetchrow('SELECT display_name,role,alive FROM room_players WHERE room_id=$1 AND telegram_id=$2',room_id,action['target'])
                    detective_result.append((int(actor), target['display_name'] if target else 'بازیکن', target['role']=='mafia' if target else False))
            await conn.execute("UPDATE game_rooms SET status='day',state=$2::jsonb,updated_at=NOW() WHERE id=$1",room_id,json.dumps({'round':state.get('round',1),'phase_started_at':datetime.now(timezone.utc).isoformat(),'night_actions':{},'votes':{},'challenges':[],'covers':{},'last_attacked':victim,'last_healed':doctor_targets,'handshake_completed':bool(state.get('handshake_completed', False))}))
            alive=await conn.fetch('SELECT telegram_id,display_name,role FROM room_players WHERE room_id=$1 AND alive=TRUE',room_id)
            all_players=await conn.fetch('SELECT role,alive FROM room_players WHERE room_id=$1',room_id)
            win=winner(all_players)
            if win: await conn.execute("UPDATE game_rooms SET status='finished',updated_at=NOW() WHERE id=$1",room_id)
            return victim, bool(victim and victim in doctor_targets), detective_result, alive, win

async def resolve_day(room_id: int):
    async with db().acquire() as conn:
        async with conn.transaction():
            room=await conn.fetchrow('SELECT * FROM game_rooms WHERE id=$1 FOR UPDATE',room_id)
            if not room or room['status']!='day': raise ValueError('اتاق در مرحلهٔ روز نیست.')
            state=decode_state(room['state']); votes=state.get('votes',{})
            from collections import Counter
            counts=Counter(votes.values()); eliminated=None
            if counts:
                target, n=counts.most_common(1)[0]
                if list(counts.values()).count(n)==1: eliminated=int(target)
            if eliminated:
                await conn.execute('UPDATE room_players SET alive=FALSE WHERE room_id=$1 AND telegram_id=$2 AND alive=TRUE',room_id,eliminated)
            players=await conn.fetch('SELECT telegram_id,display_name,role,alive FROM room_players WHERE room_id=$1',room_id)
            win=winner(players)
            alive_count=sum(1 for p in players if p['alive'])
            if win:
                await conn.execute("UPDATE game_rooms SET status='finished',updated_at=NOW() WHERE id=$1",room_id)
            elif alive_count == 3 and not state.get('handshake_completed', False):
                new_state={'round':int(state.get('round',1))+1,'phase_started_at':datetime.now(timezone.utc).isoformat(),'night_actions':{},'votes':{},'challenges':[],'covers':{},'handshake_round':int(state.get('round',1))+1}
                await conn.execute("UPDATE game_rooms SET status='handshake',state=$2::jsonb,updated_at=NOW() WHERE id=$1",room_id,json.dumps(new_state))
            else:
                new_state={'round':int(state.get('round',1))+1,'phase_started_at':datetime.now(timezone.utc).isoformat(),'night_actions':{},'votes':{},'challenges':[],'covers':{}}
                await conn.execute("UPDATE game_rooms SET status='night',state=$2::jsonb,updated_at=NOW() WHERE id=$1",room_id,json.dumps(new_state))
            return eliminated, players, win

def winner(players):
    alive=[p for p in players if p['alive']]
    mafia=sum(1 for p in alive if p['role']=='mafia')
    town=len(alive)-mafia
    if mafia==0: return 'town'
    if mafia>=town: return 'mafia'
    return None


async def add_challenge(room_id: int, actor_id: int, target_id: int):
    """Register a daytime challenge. A challenge must be followed by a cover to be vote-eligible."""
    async with db().acquire() as conn:
        async with conn.transaction():
            room = await conn.fetchrow('SELECT * FROM game_rooms WHERE id=$1 FOR UPDATE', room_id)
            if not room or room['status'] != 'day':
                raise ValueError('چالش فقط در مرحلهٔ روز مجاز است.')
            actor = await conn.fetchrow('SELECT alive FROM room_players WHERE room_id=$1 AND telegram_id=$2', room_id, actor_id)
            target = await conn.fetchrow('SELECT alive, display_name FROM room_players WHERE room_id=$1 AND telegram_id=$2', room_id, target_id)
            if not actor or not actor['alive']:
                raise ValueError('بازیکن حذف‌شده نمی‌تواند چالش کند.')
            if not target or not target['alive']:
                raise ValueError('هدف باید بازیکن زندهٔ همین اتاق باشد.')
            if actor_id == target_id:
                raise ValueError('نمی‌توانی خودت را به چالش بکشی.')
            state = decode_state(room['state'])
            challenges = state.setdefault('challenges', [])
            if any(int(c['challenger_id']) == actor_id for c in challenges):
                raise ValueError('در هر روز فقط یک چالش می‌توانی ثبت کنی.')
            if any(int(c['target_id']) == target_id for c in challenges):
                raise ValueError('این بازیکن قبلاً در این روز به چالش کشیده شده است.')
            challenges.append({'challenger_id': actor_id, 'target_id': target_id, 'created_at': datetime.now(timezone.utc).isoformat()})
            await conn.execute('UPDATE game_rooms SET state=$2::jsonb,updated_at=NOW() WHERE id=$1', room_id, json.dumps(state))
            return target['display_name']

async def add_cover(room_id: int, actor_id: int, target_id: int):
    async with db().acquire() as conn:
        async with conn.transaction():
            room = await conn.fetchrow('SELECT * FROM game_rooms WHERE id=$1 FOR UPDATE', room_id)
            if not room or room['status'] != 'day':
                raise ValueError('پوشش فقط در مرحلهٔ روز مجاز است.')
            actor = await conn.fetchrow('SELECT alive FROM room_players WHERE room_id=$1 AND telegram_id=$2', room_id, actor_id)
            target = await conn.fetchrow('SELECT alive, display_name FROM room_players WHERE room_id=$1 AND telegram_id=$2', room_id, target_id)
            if not actor or not actor['alive']:
                raise ValueError('بازیکن حذف‌شده نمی‌تواند پوشش بدهد.')
            if not target or not target['alive']:
                raise ValueError('هدف باید بازیکن زندهٔ همین اتاق باشد.')
            if actor_id == target_id:
                raise ValueError('هیچ‌کس نمی‌تواند خودش را پوشش بدهد.')
            state = decode_state(room['state'])
            challenges = state.get('challenges', [])
            if not any(int(c['target_id']) == target_id for c in challenges):
                raise ValueError('این بازیکن هنوز چالش نشده است.')
            covers = state.setdefault('covers', {})
            if str(target_id) in covers:
                raise ValueError('این هدف قبلاً پوشش گرفته است.')
            covers[str(target_id)] = actor_id
            await conn.execute('UPDATE game_rooms SET state=$2::jsonb,updated_at=NOW() WHERE id=$1', room_id, json.dumps(state))
            return target['display_name']

async def report_violation(room_id: int | None, actor_id: int, chat_id: int, details: str):
    async with db().acquire() as conn:
        await conn.execute(
            "INSERT INTO audit_log(actor_id,action,details) VALUES($1,'mafia_report',$2::jsonb)",
            actor_id, json.dumps({'room_id': room_id, 'chat_id': chat_id, 'details': details[:500]})
        )

async def recent_reports(limit: int = 10):
    async with db().acquire() as conn:
        return await conn.fetch("SELECT id,actor_id,details,created_at FROM audit_log WHERE action='mafia_report' ORDER BY id DESC LIMIT $1", limit)

async def cancel_room(room_id: int, actor_id: int, is_admin: bool = False):
    async with db().acquire() as conn:
        async with conn.transaction():
            room = await conn.fetchrow('SELECT * FROM game_rooms WHERE id=$1 FOR UPDATE', room_id)
            if not room or room['status'] not in ('lobby','intro_day','intro_night','night','day','handshake'):
                raise ValueError('اتاق فعالی برای لغو وجود ندارد.')
            if not is_admin and (room['creator_id'] != actor_id or room['status'] != 'lobby'):
                raise ValueError('سازنده فقط می‌تواند اتاق را پیش از شروع بازی لغو کند؛ لغو بازی فعال مخصوص مدیر است.')
            await conn.execute("UPDATE game_rooms SET status='finished',updated_at=NOW() WHERE id=$1", room_id)
            await conn.execute("INSERT INTO audit_log(actor_id,action,details) VALUES($1,'mafia_cancel',$2::jsonb)", actor_id, json.dumps({'room_id': room_id, 'chat_id': room['chat_id']}))
            return room['chat_id']
