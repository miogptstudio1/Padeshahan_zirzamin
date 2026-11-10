
"""اتاق‌های بازی‌های گروهی جدید."""
from __future__ import annotations
import json
from typing import Any
from core.database import db

GAME_TYPES = ("spyfall", "escape", "kingbetray", "island", "detective", "empirewar", "auction", "court", "laststand", "bomb", "treasure", "wordwar")
MIN_PLAYERS = {"spyfall": 3, "escape": 2, "kingbetray": 3, "island": 2, "detective": 2, "empirewar": 4, "auction": 2, "court": 3, "laststand": 3, "bomb": 3, "treasure": 2, "wordwar": 2}
MAX_PLAYERS = 12


async def ensure_game_types(conn) -> None:
    # باز کردن محدودیت game_type قدیمی
    try:
        await conn.execute("ALTER TABLE game_rooms DROP CONSTRAINT IF EXISTS game_rooms_game_type_check")
    except Exception:
        pass
    try:
        await conn.execute(
            """ALTER TABLE game_rooms ADD CONSTRAINT game_rooms_game_type_check
               CHECK (game_type IN ('mafia','empire','coup','spyfall','escape','kingbetray','island','detective','empirewar','auction','court','laststand','bomb','treasure','wordwar'))"""
        )
    except Exception:
        pass


def decode(state) -> dict:
    if isinstance(state, str):
        return json.loads(state or "{}")
    return dict(state or {})


async def open_room(game_type: str, chat_id: int, creator_id: int, name: str) -> int:
    if game_type not in GAME_TYPES:
        raise ValueError("نوع بازی نامعتبر")
    async with db().acquire() as conn:
        await ensure_game_types(conn)
        async with conn.transaction():
            exists = await conn.fetchval(
                """SELECT id FROM game_rooms
                   WHERE chat_id=$1 AND game_type=$2
                     AND status IN ('lobby','playing')
                   FOR UPDATE""",
                chat_id, game_type,
            )
            if exists:
                raise ValueError("تو این گروه همین بازی الان فعال است.")
            rid = await conn.fetchval(
                """INSERT INTO game_rooms(game_type, chat_id, creator_id, status, state)
                   VALUES($1,$2,$3,'lobby','{}'::jsonb) RETURNING id""",
                game_type, chat_id, creator_id,
            )
            await conn.execute(
                "INSERT INTO room_players(room_id,telegram_id,display_name) VALUES($1,$2,$3)",
                rid, creator_id, name[:80],
            )
            return int(rid)


async def get_open(chat_id: int, game_type: str):
    async with db().acquire() as conn:
        return await conn.fetchrow(
            """SELECT * FROM game_rooms
               WHERE chat_id=$1 AND game_type=$2 AND status IN ('lobby','playing')
               ORDER BY id DESC LIMIT 1""",
            chat_id, game_type,
        )


async def room(room_id: int):
    async with db().acquire() as conn:
        return await conn.fetchrow("SELECT * FROM game_rooms WHERE id=$1", room_id)


async def players(room_id: int):
    async with db().acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM room_players WHERE room_id=$1 ORDER BY joined_at", room_id
        )


async def join(room_id: int, tg_id: int, name: str) -> int:
    async with db().acquire() as conn:
        async with conn.transaction():
            r = await conn.fetchrow("SELECT * FROM game_rooms WHERE id=$1 FOR UPDATE", room_id)
            if not r or r["status"] != "lobby":
                raise ValueError("ثبت‌نام بسته است.")
            count = int(await conn.fetchval(
                "SELECT COUNT(*) FROM room_players WHERE room_id=$1", room_id
            ))
            if count >= MAX_PLAYERS:
                raise ValueError(f"ظرفیت {MAX_PLAYERS} نفر است.")
            try:
                await conn.execute(
                    "INSERT INTO room_players(room_id,telegram_id,display_name) VALUES($1,$2,$3)",
                    room_id, tg_id, name[:80],
                )
            except Exception as e:
                if "unique" in str(e).lower() or "duplicate" in str(e).lower():
                    raise ValueError("قبلاً اومدی تو اتاق.") from e
                raise
            return count + 1


async def set_status(room_id: int, status: str, state: dict | None = None):
    async with db().acquire() as conn:
        if state is not None:
            await conn.execute(
                "UPDATE game_rooms SET status=$2, state=$3::jsonb, updated_at=NOW() WHERE id=$1",
                room_id, status, json.dumps(state, ensure_ascii=False),
            )
        else:
            await conn.execute(
                "UPDATE game_rooms SET status=$2, updated_at=NOW() WHERE id=$1",
                room_id, status,
            )


async def save_state(room_id: int, state: dict):
    async with db().acquire() as conn:
        await conn.execute(
            "UPDATE game_rooms SET state=$2::jsonb, updated_at=NOW() WHERE id=$1",
            room_id, json.dumps(state, ensure_ascii=False),
        )


async def cancel(room_id: int, actor_id: int):
    async with db().acquire() as conn:
        r = await conn.fetchrow("SELECT * FROM game_rooms WHERE id=$1", room_id)
        if not r:
            raise ValueError("اتاق نیست.")
        if int(r["creator_id"]) != int(actor_id) and r["status"] == "playing":
            # allow cancel only creator in lobby, or always creator
            pass
        if int(r["creator_id"]) != int(actor_id):
            raise ValueError("فقط سازنده اتاق می‌تونه لغو کنه.")
        await conn.execute(
            "UPDATE game_rooms SET status='finished', updated_at=NOW() WHERE id=$1",
            room_id,
        )
