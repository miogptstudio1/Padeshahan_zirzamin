import json
from core.database import db
from games.coup.engine import new_game, apply_action, declare_action, accept_action, challenge_action, block_action, lose_influence, current_player, ROLE_FA, ACTION_FA


def decode(value):
    return json.loads(value) if isinstance(value, str) else (value or {})

async def create_room(chat_id: int, creator_id: int, name: str) -> int:
    async with db().acquire() as conn:
        async with conn.transaction():
            exists = await conn.fetchval("SELECT id FROM game_rooms WHERE chat_id=$1 AND game_type='coup' AND status IN ('lobby','playing') FOR UPDATE", chat_id)
            if exists: raise ValueError('در این گروه یک اتاق کودتای فعال وجود دارد.')
            rid = await conn.fetchval("INSERT INTO game_rooms(game_type,chat_id,creator_id,status,state) VALUES('coup',$1,$2,'lobby','{}'::jsonb) RETURNING id", chat_id, creator_id)
            await conn.execute("INSERT INTO room_players(room_id,telegram_id,display_name) VALUES($1,$2,$3)", rid, creator_id, name)
            return rid

async def get_open_room(chat_id: int):
    async with db().acquire() as conn:
        return await conn.fetchrow("SELECT * FROM game_rooms WHERE chat_id=$1 AND game_type='coup' AND status IN ('lobby','playing') ORDER BY id DESC LIMIT 1", chat_id)

async def join_room(room_id: int, user_id: int, name: str):
    async with db().acquire() as conn:
        async with conn.transaction():
            room = await conn.fetchrow('SELECT * FROM game_rooms WHERE id=$1 FOR UPDATE', room_id)
            if not room or room['status'] != 'lobby': raise ValueError('ثبت‌نام این اتاق بسته شده است.')
            count = await conn.fetchval('SELECT COUNT(*) FROM room_players WHERE room_id=$1', room_id)
            if count >= 6: raise ValueError('کودتا حداکثر ۶ بازیکن دارد.')
            try: await conn.execute('INSERT INTO room_players(room_id,telegram_id,display_name) VALUES($1,$2,$3)', room_id,user_id,name)
            except Exception as exc:
                if 'unique' in str(exc).lower(): raise ValueError('قبلاً در این اتاق ثبت‌نام کرده‌ای.')
                raise
            return count + 1

async def players(room_id: int):
    async with db().acquire() as conn:
        return await conn.fetch('SELECT * FROM room_players WHERE room_id=$1 ORDER BY joined_at', room_id)

async def start_room(room_id: int, actor_id: int):
    async with db().acquire() as conn:
        async with conn.transaction():
            room = await conn.fetchrow('SELECT * FROM game_rooms WHERE id=$1 FOR UPDATE', room_id)
            if not room or room['status'] != 'lobby': raise ValueError('اتاق در مرحلهٔ ثبت‌نام نیست.')
            if room['creator_id'] != actor_id: raise ValueError('فقط سازندهٔ اتاق می‌تواند بازی را شروع کند.')
            rows = await conn.fetch('SELECT * FROM room_players WHERE room_id=$1 ORDER BY joined_at', room_id)
            if len(rows) < 2: raise ValueError('برای شروع کودتا حداقل دو بازیکن لازم است.')
            state = new_game([r['telegram_id'] for r in rows])
            for row in rows:
                cards = state['players'][str(row['telegram_id'])]['cards']
                await conn.execute('UPDATE room_players SET role=$3,alive=TRUE WHERE room_id=$1 AND telegram_id=$2', room_id,row['telegram_id'],','.join(cards))
            await conn.execute("UPDATE game_rooms SET status='playing',state=$2::jsonb,updated_at=NOW() WHERE id=$1", room_id,json.dumps(state))
            return room['chat_id'], state

async def room(room_id: int):
    async with db().acquire() as conn: return await conn.fetchrow('SELECT * FROM game_rooms WHERE id=$1', room_id)

async def mutate(room_id: int, actor_id: int, action: str, target_id=None, card_index=None, exchange_cards=None):
    async with db().acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow("SELECT * FROM game_rooms WHERE id=$1 AND game_type='coup' FOR UPDATE", room_id)
            if not row: raise ValueError('اتاق کودتا پیدا نشد.')
            state = decode(row['state'])
            if action == 'lose':
                pending = state.get('pending_loss')
                if not pending or str(pending.get('target')) != str(actor_id):
                    raise ValueError('الان از تو خواسته نشده کارت نفوذی را از دست بدهی.')
                lost = lose_influence(state, actor_id, int(card_index))
                for pid, pdata in state['players'].items():
                    await conn.execute('UPDATE room_players SET alive=$3,role=$4 WHERE room_id=$1 AND telegram_id=$2', room_id,int(pid),pdata['alive'],','.join(pdata['cards']))
                await conn.execute('UPDATE game_rooms SET status=$2,state=$3::jsonb,updated_at=NOW() WHERE id=$1', room_id,state['status'],json.dumps(state))
                return state, {'lost':lost}
            if action == 'exchange_choice':
                last=state.get('last_action') or {}
                if last.get('actor') != str(actor_id) or not last.get('needs_exchange_choice'): raise ValueError('انتخاب تبادل فعالی برای تو وجود ندارد.')
                offered=last['offered']; picks=list(exchange_cards or [])
                from collections import Counter
                if len(picks)!=2 or any(count > Counter(offered)[card] for card, count in Counter(picks).items()):
                    raise ValueError('دو کارت معتبر انتخاب کن.')
                state['players'][str(actor_id)]['cards']=picks
                remaining = Counter(offered) - Counter(picks)
                state['deck'] = state.get('deck', []) + [card for card, count in remaining.items() for _ in range(count)]
                last['needs_exchange_choice']=False
                state['last_action']=last
                # Finish turn after choosing the two cards.
                from games.coup.engine import _next_turn
                _next_turn(state)
                await conn.execute('UPDATE room_players SET role=$3 WHERE room_id=$1 AND telegram_id=$2', room_id,actor_id,','.join(picks))
                await conn.execute('UPDATE game_rooms SET status=$2,state=$3::jsonb,updated_at=NOW() WHERE id=$1', room_id,state['status'],json.dumps(state))
                return state, {'exchange':picks}
            if action == 'challenge':
                result = challenge_action(state, actor_id)
            elif action == 'block':
                result = block_action(state, actor_id, (exchange_cards or [None])[0])
            elif action == 'accept':
                result = accept_action(state, actor_id)
            elif action == 'block_done':
                result = accept_action(state, actor_id)
            else:
                result = declare_action(state, actor_id, action, target_id)
            # Keep role cards private in room_players; state is authoritative.
            for pid, pdata in state['players'].items():
                await conn.execute('UPDATE room_players SET alive=$3,role=$4 WHERE room_id=$1 AND telegram_id=$2', room_id,int(pid),pdata['alive'],','.join(pdata['cards']))
            await conn.execute('UPDATE game_rooms SET status=$2,state=$3::jsonb,updated_at=NOW() WHERE id=$1', room_id,state['status'],json.dumps(state))
            return state, result

async def get_open_room_for_player(user_id: int):
    async with db().acquire() as conn:
        return await conn.fetchrow("""SELECT gr.* FROM game_rooms gr JOIN room_players rp ON rp.room_id=gr.id
            WHERE gr.game_type='coup' AND gr.status IN ('playing') AND rp.telegram_id=$1
            ORDER BY gr.id DESC LIMIT 1""", user_id)


async def active_claim_rooms():
    """Return active Coup rooms with a pending claim so timers can be restored."""
    async with db().acquire() as conn:
        return await conn.fetch("SELECT id, chat_id, state FROM game_rooms WHERE game_type='coup' AND status='playing'")
