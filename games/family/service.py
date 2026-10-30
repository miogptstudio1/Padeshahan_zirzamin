"""سیستم خاندان / خانواده."""
from __future__ import annotations
import re
from typing import Any

from core.database import db

ROLE_LABELS = {
    "leader": "سرپرست",
    "elder": "ریش‌سفید",
    "member": "عضو",
}
CREATE_COST = 500
MAX_MEMBERS = 20
TAG_RE = re.compile(r"^[A-Za-z0-9آ-ی]{2,6}$")


async def get_membership(user_id: int) -> dict[str, Any] | None:
    async with db().acquire() as conn:
        row = await conn.fetchrow(
            """SELECT f.*, m.role AS member_role, m.joined_at
               FROM family_members m
               JOIN families f ON f.id = m.family_id
               WHERE m.telegram_id=$1""",
            int(user_id),
        )
    return dict(row) if row else None


async def create_family(user_id: int, name: str, tag: str, motto: str = "") -> dict[str, Any]:
    name = (name or "").strip()[:40]
    tag = (tag or "").strip().upper()[:6]
    motto = (motto or "").strip()[:80]
    if len(name) < 2:
        raise ValueError("نام خاندان حداقل ۲ حرف باشد.")
    if not TAG_RE.match(tag):
        raise ValueError("تگ باید ۲ تا ۶ حرف/عدد باشد.")
    existing = await get_membership(user_id)
    if existing:
        raise ValueError("قبلاً عضو یک خاندان هستی. اول خارج شو.")
    async with db().acquire() as conn:
        async with conn.transaction():
            coins = await conn.fetchval(
                "SELECT coins FROM users WHERE telegram_id=$1 FOR UPDATE", int(user_id)
            )
            if coins is None:
                raise ValueError("اول با «شروع» وارد ربات شو.")
            if int(coins) < CREATE_COST:
                raise ValueError(f"برای تشکیل خاندان {CREATE_COST} سکه لازم است.")
            taken = await conn.fetchval(
                "SELECT 1 FROM families WHERE lower(name)=lower($1) OR upper(tag)=upper($2)",
                name,
                tag,
            )
            if taken:
                raise ValueError("نام یا تگ تکراری است.")
            await conn.execute(
                "UPDATE users SET coins = coins - $2 WHERE telegram_id=$1",
                int(user_id),
                CREATE_COST,
            )
            fid = await conn.fetchval(
                """INSERT INTO families(name, tag, leader_id, motto)
                   VALUES($1,$2,$3,$4) RETURNING id""",
                name,
                tag,
                int(user_id),
                motto,
            )
            await conn.execute(
                """INSERT INTO family_members(family_id, telegram_id, role)
                   VALUES($1,$2,'leader')""",
                fid,
                int(user_id),
            )
    return await family_info(int(fid))


async def family_info(family_id: int) -> dict[str, Any]:
    async with db().acquire() as conn:
        fam = await conn.fetchrow("SELECT * FROM families WHERE id=$1", int(family_id))
        if not fam:
            raise ValueError("خاندان پیدا نشد.")
        members = await conn.fetch(
            """SELECT m.telegram_id, m.role, m.joined_at,
                      COALESCE(u.display_name, u.username, '') AS name, u.coins
               FROM family_members m
               LEFT JOIN users u ON u.telegram_id = m.telegram_id
               WHERE m.family_id=$1
               ORDER BY CASE m.role WHEN 'leader' THEN 0 WHEN 'elder' THEN 1 ELSE 2 END, m.joined_at""",
            int(family_id),
        )
    return {
        **dict(fam),
        "members": [
            {
                "telegram_id": int(r["telegram_id"]),
                "role": r["role"],
                "role_label": ROLE_LABELS.get(r["role"], r["role"]),
                "name": r["name"],
                "coins": int(r["coins"] or 0),
            }
            for r in members
        ],
        "member_count": len(members),
    }


async def invite(actor_id: int, target_id: int) -> None:
    actor_id, target_id = int(actor_id), int(target_id)
    if actor_id == target_id:
        raise ValueError("نمی‌تونی خودت را دعوت کنی.")
    mem = await get_membership(actor_id)
    if not mem or mem["member_role"] not in {"leader", "elder"}:
        raise ValueError("فقط سرپرست یا ریش‌سفید می‌تواند دعوت کند.")
    if await get_membership(target_id):
        raise ValueError("این بازیکن عضو خاندان دیگری است.")
    async with db().acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM family_members WHERE family_id=$1", mem["id"]
        )
        if int(count) >= MAX_MEMBERS:
            raise ValueError(f"ظرفیت خاندان پر است (حداکثر {MAX_MEMBERS}).")
        exists_user = await conn.fetchval(
            "SELECT 1 FROM users WHERE telegram_id=$1", target_id
        )
        if not exists_user:
            raise ValueError("بازیکن هدف پیدا نشد؛ اول باید /start زده باشد.")
        await conn.execute(
            """DELETE FROM family_invites
               WHERE family_id=$1 AND invitee_id=$2 AND status='pending'""",
            mem["id"],
            target_id,
        )
        await conn.execute(
            """INSERT INTO family_invites(family_id, inviter_id, invitee_id, status)
               VALUES($1,$2,$3,'pending')""",
            mem["id"],
            actor_id,
            target_id,
        )


async def accept_invite(user_id: int, family_id: int | None = None) -> dict[str, Any]:
    user_id = int(user_id)
    if await get_membership(user_id):
        raise ValueError("الان عضو یک خاندان هستی.")
    async with db().acquire() as conn:
        if family_id:
            inv = await conn.fetchrow(
                """SELECT * FROM family_invites
                   WHERE invitee_id=$1 AND family_id=$2 AND status='pending'
                   ORDER BY id DESC LIMIT 1""",
                user_id,
                int(family_id),
            )
        else:
            inv = await conn.fetchrow(
                """SELECT * FROM family_invites
                   WHERE invitee_id=$1 AND status='pending'
                   ORDER BY id DESC LIMIT 1""",
                user_id,
            )
        if not inv:
            raise ValueError("دعوت فعالی نداری.")
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM family_members WHERE family_id=$1", inv["family_id"]
        )
        if int(count) >= MAX_MEMBERS:
            raise ValueError("ظرفیت خاندان پر شده.")
        await conn.execute(
            """INSERT INTO family_members(family_id, telegram_id, role)
               VALUES($1,$2,'member')""",
            inv["family_id"],
            user_id,
        )
        await conn.execute(
            "UPDATE family_invites SET status='accepted' WHERE id=$1", inv["id"]
        )
    return await family_info(int(inv["family_id"]))


async def leave(user_id: int) -> None:
    user_id = int(user_id)
    mem = await get_membership(user_id)
    if not mem:
        raise ValueError("عضو هیچ خاندانی نیستی.")
    async with db().acquire() as conn:
        if mem["member_role"] == "leader":
            others = await conn.fetch(
                """SELECT telegram_id FROM family_members
                   WHERE family_id=$1 AND telegram_id<>$2 ORDER BY joined_at LIMIT 1""",
                mem["id"],
                user_id,
            )
            if others:
                await conn.execute(
                    "UPDATE family_members SET role='leader' WHERE family_id=$1 AND telegram_id=$2",
                    mem["id"],
                    others[0]["telegram_id"],
                )
                await conn.execute(
                    "UPDATE families SET leader_id=$2 WHERE id=$1",
                    mem["id"],
                    others[0]["telegram_id"],
                )
            else:
                await conn.execute("DELETE FROM families WHERE id=$1", mem["id"])
                return
        await conn.execute(
            "DELETE FROM family_members WHERE family_id=$1 AND telegram_id=$2",
            mem["id"],
            user_id,
        )


async def kick(actor_id: int, target_id: int) -> None:
    actor_id, target_id = int(actor_id), int(target_id)
    mem = await get_membership(actor_id)
    if not mem or mem["member_role"] != "leader":
        raise ValueError("فقط سرپرست می‌تواند اخراج کند.")
    if target_id == actor_id:
        raise ValueError("برای ترک از «خروج خاندان» استفاده کن.")
    tmem = await get_membership(target_id)
    if not tmem or int(tmem["id"]) != int(mem["id"]):
        raise ValueError("این بازیکن عضو خاندان تو نیست.")
    async with db().acquire() as conn:
        await conn.execute(
            "DELETE FROM family_members WHERE family_id=$1 AND telegram_id=$2",
            mem["id"],
            target_id,
        )


async def deposit(user_id: int, amount: int) -> dict[str, Any]:
    user_id = int(user_id)
    amount = int(amount)
    if amount < 10 or amount > 100_000:
        raise ValueError("مبلغ باید بین ۱۰ تا ۱۰۰٬۰۰۰ باشد.")
    mem = await get_membership(user_id)
    if not mem:
        raise ValueError("عضو خاندان نیستی.")
    async with db().acquire() as conn:
        async with conn.transaction():
            coins = await conn.fetchval(
                "SELECT coins FROM users WHERE telegram_id=$1 FOR UPDATE", user_id
            )
            if int(coins) < amount:
                raise ValueError("سکه کافی نداری.")
            await conn.execute(
                "UPDATE users SET coins = coins - $2 WHERE telegram_id=$1", user_id, amount
            )
            await conn.execute(
                "UPDATE families SET treasury = treasury + $2 WHERE id=$1", mem["id"], amount
            )
            bal = await conn.fetchval("SELECT treasury FROM families WHERE id=$1", mem["id"])
    return {"treasury": int(bal), "paid": amount}


async def top_families(limit: int = 10) -> list[dict[str, Any]]:
    async with db().acquire() as conn:
        rows = await conn.fetch(
            """SELECT f.id, f.name, f.tag, f.level, f.treasury, f.leader_id,
                      (SELECT COUNT(*) FROM family_members m WHERE m.family_id=f.id) AS members
               FROM families f
               ORDER BY f.level DESC, f.treasury DESC, f.id ASC
               LIMIT $1""",
            limit,
        )
    return [dict(r) for r in rows]
