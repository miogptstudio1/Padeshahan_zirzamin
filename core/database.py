import asyncpg
from config import DATABASE_URL

pool: asyncpg.Pool | None = None

SCHEMA = [
"""CREATE TABLE IF NOT EXISTS users (
 telegram_id BIGINT PRIMARY KEY, username TEXT, display_name TEXT NOT NULL DEFAULT '',
 coins BIGINT NOT NULL DEFAULT 0, daily_claimed_at TIMESTAMPTZ, work_claimed_at TIMESTAMPTZ,
 games_played INTEGER NOT NULL DEFAULT 0, wins INTEGER NOT NULL DEFAULT 0, xp BIGINT NOT NULL DEFAULT 0 CHECK(xp >= 0),
 is_banned BOOLEAN NOT NULL DEFAULT FALSE, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)""",
"""ALTER TABLE users ADD COLUMN IF NOT EXISTS work_claimed_at TIMESTAMPTZ""",
"""ALTER TABLE users ADD COLUMN IF NOT EXISTS xp BIGINT NOT NULL DEFAULT 0 CHECK(xp >= 0)""",
"""CREATE TABLE IF NOT EXISTS empire_mission_claims (
 telegram_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
 mission_key TEXT NOT NULL, period_key TEXT NOT NULL, claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(telegram_id,mission_key,period_key)
)""",
"""CREATE TABLE IF NOT EXISTS empire_achievement_claims (
 telegram_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
 achievement_key TEXT NOT NULL, claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(telegram_id,achievement_key)
)""",
"""CREATE TABLE IF NOT EXISTS empire_assets (
 telegram_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
 asset_key TEXT NOT NULL CHECK (asset_key IN ('workshop','club','factory')),
 level INTEGER NOT NULL DEFAULT 1 CHECK (level BETWEEN 1 AND 5),
 last_collected_at TIMESTAMPTZ,
 purchased_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(telegram_id, asset_key)
)""",
"""CREATE TABLE IF NOT EXISTS game_rooms (
 id BIGSERIAL PRIMARY KEY, game_type TEXT NOT NULL CHECK (game_type IN ('mafia','empire','coup')),
 chat_id BIGINT NOT NULL, creator_id BIGINT NOT NULL, status TEXT NOT NULL DEFAULT 'lobby',
 state JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)""",
"""DROP INDEX IF EXISTS one_open_room_per_group""",
"""CREATE UNIQUE INDEX IF NOT EXISTS one_open_room_per_group ON game_rooms(chat_id, game_type) WHERE status IN ('lobby','intro_day','intro_night','night','day','handshake','playing')""",
"""CREATE TABLE IF NOT EXISTS room_players (
 room_id BIGINT NOT NULL REFERENCES game_rooms(id) ON DELETE CASCADE,
 telegram_id BIGINT NOT NULL, display_name TEXT NOT NULL, role TEXT,
 alive BOOLEAN NOT NULL DEFAULT TRUE, joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(room_id, telegram_id)
)""",
"""CREATE TABLE IF NOT EXISTS audit_log (
 id BIGSERIAL PRIMARY KEY, actor_id BIGINT, action TEXT NOT NULL, details JSONB NOT NULL DEFAULT '{}'::jsonb,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)""",
"""CREATE TABLE IF NOT EXISTS empire_transactions (
 id BIGSERIAL PRIMARY KEY, telegram_id BIGINT NOT NULL, amount BIGINT NOT NULL,
 reason TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)""",
"""CREATE TABLE IF NOT EXISTS empire_armies (
 telegram_id BIGINT PRIMARY KEY REFERENCES users(telegram_id) ON DELETE CASCADE,
 soldiers INTEGER NOT NULL DEFAULT 0 CHECK(soldiers BETWEEN 0 AND 500),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)""",
"""CREATE TABLE IF NOT EXISTS empire_cities (
 city_key TEXT PRIMARY KEY, name TEXT NOT NULL, price BIGINT NOT NULL CHECK(price > 0),
 tax_income BIGINT NOT NULL CHECK(tax_income >= 0), description TEXT NOT NULL DEFAULT '',
 owner_id BIGINT REFERENCES users(telegram_id) ON DELETE SET NULL,
 defense_level INTEGER NOT NULL DEFAULT 0 CHECK(defense_level BETWEEN 0 AND 5),
 last_tax_at TIMESTAMPTZ, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)""",
"""CREATE TABLE IF NOT EXISTS empire_wars (
 id BIGSERIAL PRIMARY KEY, attacker_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
 defender_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
 attack_city_key TEXT NOT NULL REFERENCES empire_cities(city_key),
 target_city_key TEXT NOT NULL REFERENCES empire_cities(city_key),
 attack_power INTEGER NOT NULL CHECK(attack_power >= 0), status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','attacker_won','defender_won','cancelled')),
 fee BIGINT NOT NULL CHECK(fee >= 0), created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 resolves_at TIMESTAMPTZ NOT NULL, resolved_at TIMESTAMPTZ, defense_power INTEGER,
 CHECK(attacker_id <> defender_id), CHECK(attack_city_key <> target_city_key)
)""",
"""CREATE UNIQUE INDEX IF NOT EXISTS one_pending_war_per_target ON empire_wars(target_city_key) WHERE status = 'pending'""",
"""CREATE INDEX IF NOT EXISTS empire_wars_users_status ON empire_wars(attacker_id, defender_id, status)""",
"""CREATE TABLE IF NOT EXISTS empire_alliances (
 id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, tag TEXT NOT NULL, leader_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)""",
"""CREATE UNIQUE INDEX IF NOT EXISTS empire_alliances_name_lower ON empire_alliances(LOWER(name))""",
"""CREATE UNIQUE INDEX IF NOT EXISTS empire_alliances_tag_upper ON empire_alliances(UPPER(tag))""",
"""CREATE TABLE IF NOT EXISTS empire_alliance_members (
 alliance_id BIGINT NOT NULL REFERENCES empire_alliances(id) ON DELETE CASCADE,
 telegram_id BIGINT NOT NULL UNIQUE REFERENCES users(telegram_id) ON DELETE CASCADE,
 role TEXT NOT NULL DEFAULT 'member' CHECK(role IN ('leader','member')),
 rank TEXT NOT NULL DEFAULT 'member' CHECK(rank IN ('leader','commander','treasurer','officer','member')),
 joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), PRIMARY KEY(alliance_id,telegram_id)
)""",
"""ALTER TABLE empire_alliance_members ADD COLUMN IF NOT EXISTS rank TEXT NOT NULL DEFAULT 'member' CHECK(rank IN ('leader','commander','treasurer','officer','member'))""",
"""UPDATE empire_alliance_members SET rank='leader' WHERE role='leader' AND rank<>'leader'""",
"""CREATE TABLE IF NOT EXISTS empire_alliance_requests (
 id BIGSERIAL PRIMARY KEY, alliance_id BIGINT NOT NULL REFERENCES empire_alliances(id) ON DELETE CASCADE,
 requester_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','accepted','rejected')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), resolved_at TIMESTAMPTZ
)""",
"""CREATE UNIQUE INDEX IF NOT EXISTS empire_alliance_one_pending_request ON empire_alliance_requests(alliance_id,requester_id) WHERE status='pending'""",
"""CREATE INDEX IF NOT EXISTS empire_alliance_requests_by_alliance ON empire_alliance_requests(alliance_id,status,created_at)""",
"""CREATE TABLE IF NOT EXISTS empire_alliance_messages (
 id BIGSERIAL PRIMARY KEY, alliance_id BIGINT NOT NULL REFERENCES empire_alliances(id) ON DELETE CASCADE,
 sender_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
 message TEXT NOT NULL CHECK(char_length(message) BETWEEN 1 AND 500), created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)""",
"""CREATE INDEX IF NOT EXISTS empire_alliance_messages_recent ON empire_alliance_messages(alliance_id,id DESC)""",
"""CREATE TABLE IF NOT EXISTS global_chat_messages (
 id BIGSERIAL PRIMARY KEY,
 sender_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
 message TEXT NOT NULL CHECK(char_length(message) BETWEEN 1 AND 300),
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)""",
"""CREATE INDEX IF NOT EXISTS global_chat_messages_recent ON global_chat_messages(id DESC)""",
"""CREATE TABLE IF NOT EXISTS empire_alliance_pacts (
 id BIGSERIAL PRIMARY KEY, alliance_a BIGINT NOT NULL REFERENCES empire_alliances(id) ON DELETE CASCADE,
 alliance_b BIGINT NOT NULL REFERENCES empire_alliances(id) ON DELETE CASCADE,
 initiated_by BIGINT NOT NULL REFERENCES empire_alliances(id) ON DELETE CASCADE,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','active','rejected','expired')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '7 days'),
 CHECK(alliance_a < alliance_b), CHECK(alliance_a <> alliance_b)
)""",
"""CREATE UNIQUE INDEX IF NOT EXISTS empire_alliance_pact_open_pair ON empire_alliance_pacts(alliance_a,alliance_b) WHERE status IN ('pending','active')""",
"""CREATE INDEX IF NOT EXISTS empire_alliance_pacts_expiry ON empire_alliance_pacts(status,expires_at)""",
"""CREATE TABLE IF NOT EXISTS empire_alliance_wars (
 id BIGSERIAL PRIMARY KEY,
 attacker_alliance_id BIGINT NOT NULL REFERENCES empire_alliances(id) ON DELETE CASCADE,
 defender_alliance_id BIGINT NOT NULL REFERENCES empire_alliances(id) ON DELETE CASCADE,
 attacker_leader_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
 defender_leader_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
 target_city_key TEXT NOT NULL REFERENCES empire_cities(city_key),
 attack_power INTEGER NOT NULL CHECK(attack_power >= 0),
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','attacker_won','defender_won','cancelled')),
 fee BIGINT NOT NULL CHECK(fee >= 0), defense_power INTEGER,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), resolves_at TIMESTAMPTZ NOT NULL,
 resolved_at TIMESTAMPTZ, CHECK(attacker_alliance_id <> defender_alliance_id)
)""",
"""CREATE UNIQUE INDEX IF NOT EXISTS empire_alliance_war_one_pending_target ON empire_alliance_wars(target_city_key) WHERE status='pending'""",
"""CREATE INDEX IF NOT EXISTS empire_alliance_wars_pending ON empire_alliance_wars(status,resolves_at)""",
"""CREATE TABLE IF NOT EXISTS empire_alliance_war_support (
 war_id BIGINT NOT NULL REFERENCES empire_alliance_wars(id) ON DELETE CASCADE,
 contributor_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
 coins BIGINT NOT NULL CHECK(coins BETWEEN 10 AND 1000),
 defense_bonus INTEGER NOT NULL CHECK(defense_bonus BETWEEN 1 AND 100),
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(war_id,contributor_id)
)""",
"""CREATE TABLE IF NOT EXISTS empire_alliance_season_points (
 season_key TEXT NOT NULL, alliance_id BIGINT NOT NULL REFERENCES empire_alliances(id) ON DELETE CASCADE,
 points INTEGER NOT NULL DEFAULT 0 CHECK(points >= 0), wins INTEGER NOT NULL DEFAULT 0 CHECK(wins >= 0),
 losses INTEGER NOT NULL DEFAULT 0 CHECK(losses >= 0), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(season_key,alliance_id)
)""",
"""CREATE INDEX IF NOT EXISTS empire_alliance_season_ranking ON empire_alliance_season_points(season_key,points DESC,wins DESC)""",
"""CREATE TABLE IF NOT EXISTS empire_alliance_treasuries (
 alliance_id BIGINT PRIMARY KEY REFERENCES empire_alliances(id) ON DELETE CASCADE,
 balance BIGINT NOT NULL DEFAULT 0 CHECK(balance >= 0), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)""",
"""CREATE TABLE IF NOT EXISTS empire_alliance_treasury_transactions (
 id BIGSERIAL PRIMARY KEY, alliance_id BIGINT NOT NULL REFERENCES empire_alliances(id) ON DELETE CASCADE,
 actor_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
 amount BIGINT NOT NULL CHECK(amount <> 0), reason TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)""",
"""CREATE INDEX IF NOT EXISTS empire_alliance_treasury_transactions_recent ON empire_alliance_treasury_transactions(alliance_id,id DESC)""",
"""CREATE TABLE IF NOT EXISTS empire_alliance_daily_claims (
 telegram_id BIGINT PRIMARY KEY REFERENCES users(telegram_id) ON DELETE CASCADE,
 alliance_id BIGINT NOT NULL REFERENCES empire_alliances(id) ON DELETE CASCADE,
 claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)""",
"""CREATE TABLE IF NOT EXISTS empire_alliance_rank_log (
 id BIGSERIAL PRIMARY KEY, alliance_id BIGINT NOT NULL REFERENCES empire_alliances(id) ON DELETE CASCADE,
 actor_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
 target_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
 new_rank TEXT NOT NULL CHECK(new_rank IN ('commander','treasurer','officer','member')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)""",
"""CREATE TABLE IF NOT EXISTS empire_alliance_buildings (
 alliance_id BIGINT PRIMARY KEY REFERENCES empire_alliances(id) ON DELETE CASCADE,
 fortress_level INTEGER NOT NULL DEFAULT 0 CHECK(fortress_level BETWEEN 0 AND 5),
 academy_level INTEGER NOT NULL DEFAULT 0 CHECK(academy_level BETWEEN 0 AND 5),
 shield_until TIMESTAMPTZ, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)""",
"""CREATE TABLE IF NOT EXISTS empire_alliance_notification_settings (
 telegram_id BIGINT PRIMARY KEY REFERENCES users(telegram_id) ON DELETE CASCADE,
 telegram_enabled BOOLEAN NOT NULL DEFAULT TRUE, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)""",
"""CREATE TABLE IF NOT EXISTS empire_alliance_notification_preferences (
 telegram_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
 category TEXT NOT NULL CHECK(category IN ('treasury','rank','war','buildings','general')),
 enabled BOOLEAN NOT NULL DEFAULT TRUE, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), PRIMARY KEY(telegram_id,category)
)""",
"""CREATE TABLE IF NOT EXISTS empire_alliance_notifications (
 id BIGSERIAL PRIMARY KEY, alliance_id BIGINT NOT NULL REFERENCES empire_alliances(id) ON DELETE CASCADE,
 telegram_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
 category TEXT NOT NULL CHECK(category IN ('treasury','rank','war','buildings','general')),
 title TEXT NOT NULL, message TEXT NOT NULL, actor_id BIGINT REFERENCES users(telegram_id) ON DELETE SET NULL,
 is_read BOOLEAN NOT NULL DEFAULT FALSE, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)""",
"""CREATE INDEX IF NOT EXISTS empire_alliance_notifications_inbox ON empire_alliance_notifications(telegram_id,is_read,id DESC)""",
"""CREATE TABLE IF NOT EXISTS empire_alliance_history (
 id BIGSERIAL PRIMARY KEY, alliance_id BIGINT NOT NULL REFERENCES empire_alliances(id) ON DELETE CASCADE,
 event_type TEXT NOT NULL, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
 actor_id BIGINT REFERENCES users(telegram_id) ON DELETE SET NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)""",
"""CREATE INDEX IF NOT EXISTS empire_alliance_history_recent ON empire_alliance_history(alliance_id,id DESC)""",
"""CREATE TABLE IF NOT EXISTS empire_alliance_proposals (
 id BIGSERIAL PRIMARY KEY, alliance_id BIGINT NOT NULL REFERENCES empire_alliances(id) ON DELETE CASCADE,
 creator_id BIGINT REFERENCES users(telegram_id) ON DELETE SET NULL, title TEXT NOT NULL CHECK(char_length(title) BETWEEN 5 AND 100),
 description TEXT NOT NULL CHECK(char_length(description) BETWEEN 10 AND 1000),
 status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','passed','rejected')),
 yes_votes INTEGER NOT NULL DEFAULT 0 CHECK(yes_votes>=0), no_votes INTEGER NOT NULL DEFAULT 0 CHECK(no_votes>=0),
 expires_at TIMESTAMPTZ NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)""",
"""CREATE INDEX IF NOT EXISTS empire_alliance_proposals_recent ON empire_alliance_proposals(alliance_id,id DESC)""",
"""CREATE TABLE IF NOT EXISTS empire_alliance_votes (
 proposal_id BIGINT NOT NULL REFERENCES empire_alliance_proposals(id) ON DELETE CASCADE,
 voter_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
 choice TEXT NOT NULL CHECK(choice IN ('yes','no')), created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(proposal_id,voter_id)
)""",
"""CREATE TABLE IF NOT EXISTS empire_equipment_inventory (
 telegram_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
 item_key TEXT NOT NULL, quantity INTEGER NOT NULL DEFAULT 0 CHECK(quantity >= 0),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), PRIMARY KEY(telegram_id,item_key)
)""",
"""CREATE TABLE IF NOT EXISTS empire_equipment_loadouts (
 telegram_id BIGINT PRIMARY KEY REFERENCES users(telegram_id) ON DELETE CASCADE,
 weapon_key TEXT, armor_key TEXT, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)""",
"""CREATE TABLE IF NOT EXISTS empire_equipment_box_claims (
 telegram_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
 request_id TEXT NOT NULL, reward_key TEXT NOT NULL, reward_amount BIGINT NOT NULL DEFAULT 0,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), PRIMARY KEY(telegram_id,request_id)
)""",
"""CREATE TABLE IF NOT EXISTS empire_equipment_transactions (
 id BIGSERIAL PRIMARY KEY, telegram_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
 item_key TEXT NOT NULL, quantity INTEGER NOT NULL, total_cost BIGINT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('purchase','box')), created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)""",
"""CREATE TABLE IF NOT EXISTS staff_members (
 telegram_id BIGINT PRIMARY KEY REFERENCES users(telegram_id) ON DELETE CASCADE,
 role TEXT NOT NULL CHECK(role IN ('moderator','support','economy','operator')),
 granted_by BIGINT REFERENCES users(telegram_id) ON DELETE SET NULL,
 note TEXT NOT NULL DEFAULT '',
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)""",
"""CREATE INDEX IF NOT EXISTS staff_members_role ON staff_members(role)""",
"""CREATE TABLE IF NOT EXISTS staff_audit_log (
 id BIGSERIAL PRIMARY KEY,
 actor_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
 action TEXT NOT NULL,
 target_id BIGINT,
 detail TEXT NOT NULL DEFAULT '',
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)""",
"""CREATE INDEX IF NOT EXISTS staff_audit_log_recent ON staff_audit_log(id DESC)"""
]

async def connect_db():
    global pool
    if not DATABASE_URL:
        raise RuntimeError('DATABASE_URL در فایل .env تنظیم نشده است.')
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5, command_timeout=30)
    async with pool.acquire() as conn:
        for statement in SCHEMA:
            await conn.execute(statement)
        cities = [
            ('market', 'بازار مرکزی', 500, 30, 'قلب تجارت شهر'),
            ('port', 'بندر قدیمی', 1000, 60, 'مسیر بازرگانی و واردات'),
            ('citadel', 'ارگ سلطنتی', 2000, 120, 'مرکز نفوذ سیاسی'),
            ('industrial', 'منطقه صنعتی', 4000, 250, 'کارگاه‌ها و کارخانه‌ها'),
            ('capital', 'پایتخت زیرزمین', 8000, 500, 'گران‌ترین و پردرآمدترین قلمرو'),
        ]
        await conn.executemany("""INSERT INTO empire_cities(city_key,name,price,tax_income,description)
            VALUES($1,$2,$3,$4,$5) ON CONFLICT(city_key) DO NOTHING""", cities)

async def close_db():
    global pool
    if pool:
        await pool.close()
        pool = None

def db() -> asyncpg.Pool:
    if pool is None:
        raise RuntimeError('Database pool is not initialized')
    return pool

async def upsert_user(tg_id: int, username: str | None, name: str):
    async with db().acquire() as conn:
        await conn.execute("""INSERT INTO users(telegram_id, username, display_name) VALUES($1,$2,$3)
        ON CONFLICT(telegram_id) DO UPDATE SET username=EXCLUDED.username, display_name=EXCLUDED.display_name""", tg_id, username, name)
