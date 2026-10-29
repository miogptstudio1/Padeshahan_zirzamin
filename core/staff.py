"""Staff / admin role helpers.

Super-admins come from ADMIN_IDS env and cannot be removed via the app.
Granted roles (moderator, support, economy, operator) inherit subsets of power.
"""
from __future__ import annotations

from typing import Any

from config import ADMIN_IDS
from core.database import db

# role -> permission flags
ROLE_PERMS: dict[str, set[str]] = {
    "moderator": {
        "view_players",
        "ban_user",
        "unban_user",
        "delete_global_chat",
        "view_audit",
    },
    "support": {
        "view_players",
        "grant_coins_small",  # up to 5_000
        "view_audit",
    },
    "economy": {
        "view_players",
        "grant_coins_small",
        "grant_coins_large",  # up to 50_000
        "set_coins",
        "view_audit",
    },
    "operator": {
        "view_players",
        "ban_user",
        "unban_user",
        "delete_global_chat",
        "grant_coins_small",
        "grant_coins_large",
        "set_coins",
        "manage_staff",  # can grant/revoke non-super roles
        "view_audit",
    },
}

ROLE_LABELS = {
    "moderator": "ناظر",
    "support": "پشتیبانی",
    "economy": "مدیر اقتصاد",
    "operator": "اپراتور",
    "superadmin": "ابرادمین",
}

VALID_ROLES = set(ROLE_PERMS.keys())


def is_superadmin(telegram_id: int) -> bool:
    return int(telegram_id) in ADMIN_IDS


async def get_staff_row(telegram_id: int) -> dict[str, Any] | None:
    async with db().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT telegram_id, role, granted_by, note, created_at, updated_at FROM staff_members WHERE telegram_id=$1",
            int(telegram_id),
        )
    return dict(row) if row else None


async def permissions_for(telegram_id: int) -> set[str]:
    tid = int(telegram_id)
    if is_superadmin(tid):
        # everything including manage_staff
        all_perms: set[str] = set()
        for p in ROLE_PERMS.values():
            all_perms |= p
        all_perms.add("manage_staff")
        all_perms.add("superadmin")
        return all_perms
    row = await get_staff_row(tid)
    if not row:
        return set()
    return set(ROLE_PERMS.get(row["role"], set()))


async def has_perm(telegram_id: int, perm: str) -> bool:
    return perm in await permissions_for(telegram_id)


async def require_perm(telegram_id: int, perm: str) -> set[str]:
    perms = await permissions_for(telegram_id)
    if perm not in perms and "superadmin" not in perms:
        raise ValueError("دسترسی کافی نداری.")
    return perms


async def staff_profile(telegram_id: int) -> dict[str, Any]:
    tid = int(telegram_id)
    super_ = is_superadmin(tid)
    row = await get_staff_row(tid)
    role = "superadmin" if super_ else (row["role"] if row else None)
    perms = sorted(await permissions_for(tid))
    return {
        "is_staff": bool(role),
        "is_superadmin": super_,
        "role": role,
        "role_label": ROLE_LABELS.get(role or "", role or ""),
        "permissions": perms,
        "note": (row or {}).get("note") or "",
    }


async def list_staff() -> list[dict[str, Any]]:
    async with db().acquire() as conn:
        rows = await conn.fetch(
            """SELECT s.telegram_id, s.role, s.granted_by, s.note, s.created_at, s.updated_at,
                      COALESCE(u.display_name, u.username, '') AS display_name,
                      u.username
               FROM staff_members s
               JOIN users u ON u.telegram_id = s.telegram_id
               ORDER BY s.role, s.telegram_id"""
        )
    out = [
        {
            "telegram_id": int(r["telegram_id"]),
            "role": r["role"],
            "role_label": ROLE_LABELS.get(r["role"], r["role"]),
            "display_name": r["display_name"],
            "username": r["username"],
            "granted_by": int(r["granted_by"]) if r["granted_by"] is not None else None,
            "note": r["note"] or "",
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]
    # include superadmins from env even if not in table
    async with db().acquire() as conn:
        for aid in sorted(ADMIN_IDS):
            if any(x["telegram_id"] == aid for x in out):
                continue
            u = await conn.fetchrow(
                "SELECT display_name, username FROM users WHERE telegram_id=$1", aid
            )
            out.insert(
                0,
                {
                    "telegram_id": aid,
                    "role": "superadmin",
                    "role_label": ROLE_LABELS["superadmin"],
                    "display_name": (u["display_name"] if u else "") or "ابرادمین",
                    "username": u["username"] if u else None,
                    "granted_by": None,
                    "note": "از متغیر محیطی ADMIN_IDS",
                    "created_at": None,
                },
            )
    return out


async def grant_role(actor_id: int, target_id: int, role: str, note: str = "") -> dict[str, Any]:
    actor_id, target_id = int(actor_id), int(target_id)
    role = (role or "").strip().lower()
    if role not in VALID_ROLES:
        raise ValueError("مقام نامعتبر است. یکی از: moderator, support, economy, operator")
    if is_superadmin(target_id):
        raise ValueError("ابرادمین از طریق پنل قابل تغییر نیست.")
    await require_perm(actor_id, "manage_staff")
    # only superadmin can grant operator
    if role == "operator" and not is_superadmin(actor_id):
        raise ValueError("فقط ابرادمین می‌تواند مقام اپراتور بدهد.")
    note = (note or "").strip()[:200]
    async with db().acquire() as conn:
        exists = await conn.fetchval("SELECT 1 FROM users WHERE telegram_id=$1", target_id)
        if not exists:
            raise ValueError("بازیکن هدف پیدا نشد. اول باید حداقل یک‌بار وارد بازی شده باشد.")
        await conn.execute(
            """INSERT INTO staff_members(telegram_id, role, granted_by, note, updated_at)
               VALUES($1,$2,$3,$4,NOW())
               ON CONFLICT(telegram_id) DO UPDATE
               SET role=EXCLUDED.role, granted_by=EXCLUDED.granted_by, note=EXCLUDED.note, updated_at=NOW()""",
            target_id, role, actor_id, note,
        )
        await conn.execute(
            """INSERT INTO staff_audit_log(actor_id, action, target_id, detail)
               VALUES($1,'grant_role',$2,$3)""",
            actor_id, target_id, f"role={role}; note={note}",
        )
    return await staff_profile(target_id)


async def revoke_role(actor_id: int, target_id: int) -> None:
    actor_id, target_id = int(actor_id), int(target_id)
    if is_superadmin(target_id):
        raise ValueError("ابرادمین قابل حذف از پنل نیست.")
    await require_perm(actor_id, "manage_staff")
    row = await get_staff_row(target_id)
    if not row:
        raise ValueError("این کاربر مقام ستادی ندارد.")
    if row["role"] == "operator" and not is_superadmin(actor_id):
        raise ValueError("فقط ابرادمین می‌تواند اپراتور را حذف کند.")
    async with db().acquire() as conn:
        await conn.execute("DELETE FROM staff_members WHERE telegram_id=$1", target_id)
        await conn.execute(
            """INSERT INTO staff_audit_log(actor_id, action, target_id, detail)
               VALUES($1,'revoke_role',$2,$3)""",
            actor_id, target_id, f"was={row['role']}",
        )


async def ban_user(actor_id: int, target_id: int, banned: bool) -> None:
    actor_id, target_id = int(actor_id), int(target_id)
    perm = "ban_user" if banned else "unban_user"
    await require_perm(actor_id, perm)
    if is_superadmin(target_id):
        raise ValueError("نمی‌توان ابرادمین را مسدود کرد.")
    if target_id == actor_id:
        raise ValueError("نمی‌توانی خودت را مسدود کنی.")
    async with db().acquire() as conn:
        r = await conn.execute(
            "UPDATE users SET is_banned=$2 WHERE telegram_id=$1", target_id, banned
        )
        if r == "UPDATE 0":
            raise ValueError("بازیکن پیدا نشد.")
        await conn.execute(
            """INSERT INTO staff_audit_log(actor_id, action, target_id, detail)
               VALUES($1,$2,$3,$4)""",
            actor_id, "ban" if banned else "unban", target_id, "",
        )


async def adjust_coins(actor_id: int, target_id: int, amount: int, mode: str = "add") -> dict[str, Any]:
    """mode: add | set. amount can be negative for add."""
    actor_id, target_id = int(actor_id), int(target_id)
    amount = int(amount)
    mode = (mode or "add").lower()
    if mode == "set":
        await require_perm(actor_id, "set_coins")
        if amount < 0 or amount > 10_000_000:
            raise ValueError("مقدار set باید بین ۰ تا ۱۰٬۰۰۰٬۰۰۰ باشد.")
    else:
        if abs(amount) <= 5000:
            await require_perm(actor_id, "grant_coins_small")
        else:
            await require_perm(actor_id, "grant_coins_large")
        if abs(amount) > 50_000:
            raise ValueError("حداکثر تغییر در هر بار ۵۰٬۰۰۰ سکه است.")
    async with db().acquire() as conn:
        row = await conn.fetchrow("SELECT coins, is_banned FROM users WHERE telegram_id=$1", target_id)
        if not row:
            raise ValueError("بازیکن پیدا نشد.")
        if mode == "set":
            new_coins = amount
        else:
            new_coins = int(row["coins"]) + amount
            if new_coins < 0:
                raise ValueError("موجودی نمی‌تواند منفی شود.")
        await conn.execute("UPDATE users SET coins=$2 WHERE telegram_id=$1", target_id, new_coins)
        await conn.execute(
            """INSERT INTO staff_audit_log(actor_id, action, target_id, detail)
               VALUES($1,'coins',$2,$3)""",
            actor_id, target_id, f"mode={mode}; amount={amount}; result={new_coins}",
        )
    return {"telegram_id": target_id, "coins": new_coins}


async def delete_global_message(actor_id: int, message_id: int) -> None:
    await require_perm(int(actor_id), "delete_global_chat")
    async with db().acquire() as conn:
        r = await conn.execute("DELETE FROM global_chat_messages WHERE id=$1", int(message_id))
        if r == "DELETE 0":
            raise ValueError("پیام پیدا نشد.")
        await conn.execute(
            """INSERT INTO staff_audit_log(actor_id, action, target_id, detail)
               VALUES($1,'delete_chat',NULL,$2)""",
            int(actor_id), f"message_id={message_id}",
        )


async def lookup_player(actor_id: int, query: str) -> list[dict[str, Any]]:
    await require_perm(int(actor_id), "view_players")
    q = (query or "").strip()
    if not q:
        raise ValueError("عبارت جستجو خالی است.")
    async with db().acquire() as conn:
        if q.isdigit():
            rows = await conn.fetch(
                """SELECT telegram_id, username, display_name, coins, is_banned, games_played, wins
                   FROM users WHERE telegram_id=$1 LIMIT 1""",
                int(q),
            )
        else:
            rows = await conn.fetch(
                """SELECT telegram_id, username, display_name, coins, is_banned, games_played, wins
                   FROM users
                   WHERE username ILIKE $1 OR display_name ILIKE $1
                   ORDER BY coins DESC LIMIT 20""",
                f"%{q}%",
            )
    return [
        {
            "telegram_id": int(r["telegram_id"]),
            "username": r["username"],
            "display_name": r["display_name"],
            "coins": int(r["coins"]),
            "is_banned": bool(r["is_banned"]),
            "games_played": int(r["games_played"]),
            "wins": int(r["wins"]),
        }
        for r in rows
    ]


async def recent_audit(actor_id: int, limit: int = 30) -> list[dict[str, Any]]:
    await require_perm(int(actor_id), "view_audit")
    limit = max(1, min(100, int(limit)))
    async with db().acquire() as conn:
        rows = await conn.fetch(
            """SELECT a.id, a.actor_id, a.action, a.target_id, a.detail, a.created_at,
                      COALESCE(u.display_name, u.username, '') AS actor_name
               FROM staff_audit_log a
               LEFT JOIN users u ON u.telegram_id = a.actor_id
               ORDER BY a.id DESC LIMIT $1""",
            limit,
        )
    return [
        {
            "id": int(r["id"]),
            "actor_id": int(r["actor_id"]),
            "actor_name": r["actor_name"],
            "action": r["action"],
            "target_id": int(r["target_id"]) if r["target_id"] is not None else None,
            "detail": r["detail"],
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]
