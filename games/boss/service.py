"""World Boss — آسیب جمعی، رتبه، جایزه."""
from __future__ import annotations
import random
from datetime import datetime, timezone, timedelta
from typing import Any

from core.database import db
from games.empire import army_advanced
from games.events import service as event_service
from games.daily import service as daily_service
from games.reputation import service as rep_service

BOSS_PRESETS = [
    {"boss_key": "shadow_colossus", "name": "غول سایه", "max_hp": 50000, "reward_pool": 8000},
    {"boss_key": "iron_wraith", "name": "شبح آهنین", "max_hp": 35000, "reward_pool": 5500},
    {"boss_key": "ash_dragon", "name": "اژدهای خاکستر", "max_hp": 80000, "reward_pool": 12000},
]


async def ensure_boss() -> dict[str, Any]:
    async with db().acquire() as conn:
        row = await conn.fetchrow(
            """SELECT * FROM world_bosses
               WHERE status='active' AND (ends_at IS NULL OR ends_at > NOW())
               ORDER BY id DESC LIMIT 1"""
        )
        if row:
            return dict(row)
        # expire old
        await conn.execute(
            "UPDATE world_bosses SET status='defeated' WHERE status='active' AND ends_at IS NOT NULL AND ends_at <= NOW()"
        )
        preset = random.choice(BOSS_PRESETS)
        ends = datetime.now(timezone.utc) + timedelta(days=3)
        rid = await conn.fetchval(
            """INSERT INTO world_bosses(boss_key, name, max_hp, hp, reward_pool, status, ends_at)
               VALUES($1,$2,$3,$3,$4,'active',$5) RETURNING id""",
            preset["boss_key"],
            preset["name"],
            preset["max_hp"],
            preset["reward_pool"],
            ends,
        )
        row = await conn.fetchrow("SELECT * FROM world_bosses WHERE id=$1", rid)
    return dict(row)


async def boss_status(user_id: int | None = None) -> dict[str, Any]:
    boss = await ensure_boss()
    async with db().acquire() as conn:
        top = await conn.fetch(
            """SELECT d.telegram_id, d.damage, d.hits,
                      COALESCE(u.display_name, u.username, '') AS name
               FROM world_boss_damage d
               LEFT JOIN users u ON u.telegram_id = d.telegram_id
               WHERE d.boss_id=$1
               ORDER BY d.damage DESC LIMIT 10""",
            boss["id"],
        )
        mine = None
        if user_id:
            mine = await conn.fetchrow(
                "SELECT damage, hits FROM world_boss_damage WHERE boss_id=$1 AND telegram_id=$2",
                boss["id"],
                int(user_id),
            )
    return {
        "boss": boss,
        "top": [
            {
                "rank": i,
                "name": r["name"] or r["telegram_id"],
                "damage": int(r["damage"]),
                "hits": int(r["hits"]),
            }
            for i, r in enumerate(top, 1)
        ],
        "mine": {"damage": int(mine["damage"]), "hits": int(mine["hits"])} if mine else None,
    }


async def attack_boss(user_id: int) -> dict[str, Any]:
    user_id = int(user_id)
    boss = await ensure_boss()
    if boss["status"] != "active" or int(boss["hp"]) <= 0:
        raise ValueError("این باس تموم شده. یکی جدید میاد.")

    try:
        power = await army_advanced.total_army_power(user_id)
        atk = max(15, int(power.get("total") or 20) // 2 + random.randint(5, 25))
    except Exception:
        atk = random.randint(20, 60)

    async with db().acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT * FROM world_bosses WHERE id=$1 FOR UPDATE", boss["id"]
            )
            if not row or row["status"] != "active" or int(row["hp"]) <= 0:
                raise ValueError("باس دیگر زنده نیست.")
            new_hp = max(0, int(row["hp"]) - atk)
            await conn.execute(
                "UPDATE world_bosses SET hp=$2 WHERE id=$1", row["id"], new_hp
            )
            await conn.execute(
                """INSERT INTO world_boss_damage(boss_id, telegram_id, damage, hits)
                   VALUES($1,$2,$3,1)
                   ON CONFLICT(boss_id, telegram_id)
                   DO UPDATE SET damage = world_boss_damage.damage + EXCLUDED.damage,
                                 hits = world_boss_damage.hits + 1""",
                row["id"],
                user_id,
                atk,
            )
            defeated = new_hp <= 0
            rewards = []
            if defeated:
                await conn.execute(
                    "UPDATE world_bosses SET status='defeated', defeated_at=NOW() WHERE id=$1",
                    row["id"],
                )
                pool = int(row["reward_pool"])
                top = await conn.fetch(
                    """SELECT telegram_id, damage FROM world_boss_damage
                       WHERE boss_id=$1 ORDER BY damage DESC LIMIT 5""",
                    row["id"],
                )
                shares = [0.35, 0.25, 0.15, 0.15, 0.10]
                for i, r in enumerate(top):
                    pay = int(pool * shares[i]) if i < len(shares) else 0
                    if pay > 0:
                        await conn.execute(
                            "UPDATE users SET coins = coins + $2 WHERE telegram_id=$1",
                            r["telegram_id"],
                            pay,
                        )
                        rewards.append({"telegram_id": int(r["telegram_id"]), "coins": pay, "rank": i + 1})
            my = await conn.fetchrow(
                "SELECT damage, hits FROM world_boss_damage WHERE boss_id=$1 AND telegram_id=$2",
                row["id"],
                user_id,
            )
    try:
        await event_service.add_score(user_id, max(5, atk // 20), "combat")
    except Exception:
        pass
    try:
        await daily_service.progress(user_id, "boss", 1)
    except Exception:
        pass
    try:
        await rep_service.add(user_id, 1)
    except Exception:
        pass
    return {
        "damage": atk,
        "boss_hp": new_hp,
        "boss_max": int(row["max_hp"]),
        "boss_name": row["name"],
        "defeated": defeated,
        "rewards": rewards,
        "my_damage": int(my["damage"]) if my else atk,
        "my_hits": int(my["hits"]) if my else 1,
    }
