from __future__ import annotations
import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from aiogram import Bot, Dispatcher
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from config import BOT_TOKEN, WEB_APP_URL, WEBHOOK_SECRET
from core.database import connect_db, close_db, db, upsert_user
from games.empire import service as empire_service
from games.empire.engine import ASSETS, CITIES, hourly_income, army_power_bonus
from api.auth import validate_init_data, TelegramAuthError
from api.schemas import RecruitRequest, DeclareWarRequest, DeclareAllianceWarRequest, EquipmentPurchaseRequest, EquipmentEquipRequest, EquipmentBoxRequest, StaffGrantRequest, StaffRevokeRequest, StaffBanRequest, StaffCoinsRequest, StaffDeleteChatRequest, AllianceMessageRequest
from games.empire import equipment as equipment_service
from membership_core import membership_status, REQUIRED_CHANNELS
from core import staff as staff_service

BASE_DIR = Path(__file__).resolve().parent.parent
logging.basicConfig(level=logging.INFO)


def _build_dispatcher():
    from handlers.main import router as main_router
    from handlers.callbacks import router as callbacks_router
    from handlers.mafia import router as mafia_router, restore_active_timers
    from handlers.coup import router as coup_router, restore_coup_timers
    from handlers.empire import router as empire_router
    from handlers.admin import router as admin_router
    from membership import RequiredMembershipMiddleware
    dp = Dispatcher()
    membership_middleware = RequiredMembershipMiddleware()
    dp.message.outer_middleware(membership_middleware)
    dp.callback_query.outer_middleware(membership_middleware)
    dp.include_router(main_router)
    dp.include_router(admin_router)
    dp.include_router(callbacks_router)
    dp.include_router(mafia_router)
    dp.include_router(coup_router)
    dp.include_router(empire_router)
    return dp, restore_active_timers, restore_coup_timers


async def _war_scheduler(bot: Bot):
    while True:
        try:
            results = await empire_service.resolve_expired_wars(limit=20)
            for result in results:
                from games.empire.engine import war_result_message
                message = war_result_message(result)
                for user_id in {result["attacker_id"], result["defender_id"]}:
                    try:
                        await bot.send_message(user_id, message)
                    except Exception as exc:
                        logging.info("Could not notify user %s about war %s: %s", user_id, result["id"], exc)
            from games.empire import alliance_wars as alliance_war_service
            alliance_results = await alliance_war_service.resolve_expired_alliance_wars(limit=20)
            for result in alliance_results:
                if result.get("cancelled"):
                    message = f"⚠️ جنگ اتحادها #{result['id']} لغو شد؛ وضعیت قلمرو هدف تغییر کرده بود."
                elif result.get("won"):
                    message = f"🏆 جنگ اتحادها #{result['id']}: پیروزی مهاجم! قلمرو «{result['target_name']}» به رهبر اتحاد مهاجم واگذار شد.\nغنیمت واریزی به خزانهٔ اتحاد: {result.get('loot', 0)} سکه\nقدرت حمله: {result['attack_power']} | قدرت دفاع: {result['defense_power']}"
                else:
                    message = f"🛡️ جنگ اتحادها #{result['id']}: اتحاد مدافع قلمرو «{result['target_name']}» را حفظ کرد.\nقدرت حمله: {result['attack_power']} | قدرت دفاع: {result['defense_power']}"
                for user_id in {result["attacker_leader_id"], result["defender_leader_id"]}:
                    try: await bot.send_message(user_id, message)
                    except Exception as exc: logging.info("Could not notify alliance war leaders: %s", exc)
                try:
                    for key, title in (("attacker_alliance_id", "نتیجهٔ جنگ اتحاد"), ("defender_alliance_id", "نتیجهٔ جنگ اتحاد")):
                        if result.get(key):
                            await alliance_notification_service.notify_alliance_members(bot, int(result[key]), "war", title, message)
                except Exception:
                    logging.exception("Could not persist alliance war notifications")
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.exception("Empire war scheduler failed; will retry")
        await asyncio.sleep(15)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN باید در Environment سرویس Render تنظیم شود.")
    await connect_db()
    bot = Bot(BOT_TOKEN)
    dp, restore_mafia_timers, restore_coup_timers = _build_dispatcher()
    try:
        restored = await restore_mafia_timers(bot)
        logging.info("Restored %s Mafia timers", restored)
        restored_coup = await restore_coup_timers(bot)
        logging.info("Restored %s Coup timers", restored_coup)
        app.state.bot = bot
        app.state.dispatcher = dp
        app.state.webhook_secret = WEBHOOK_SECRET or secrets.token_urlsafe(32)
        external_url = WEB_APP_URL.rstrip("/")
        if external_url:
            webhook_url = external_url + "/telegram/webhook"
            await bot.set_webhook(
                url=webhook_url,
                secret_token=app.state.webhook_secret,
                allowed_updates=dp.resolve_used_update_types(),
                drop_pending_updates=False,
            )
            logging.info("Telegram webhook configured at %s", webhook_url)
            app.state.polling_task = None
        else:
            logging.warning("WEB_APP_URL/RENDER_EXTERNAL_URL not set; using long polling for local development")
            app.state.polling_task = asyncio.create_task(dp.start_polling(bot, close_bot_session=False), name="telegram-polling")
        war_task = asyncio.create_task(_war_scheduler(bot), name="empire-war-scheduler")
        app.state.war_task = war_task
        yield
    finally:
        for task in (getattr(app.state, "polling_task", None), getattr(app.state, "war_task", None)):
            if task:
                task.cancel()
        for task in (getattr(app.state, "polling_task", None), getattr(app.state, "war_task", None)):
            if task:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    logging.exception("Background task stopped with an error")
        await bot.session.close()
        await close_db()


app = FastAPI(title="پادشاهان زیرزمین API", version="0.31.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-Telegram-Init-Data"])


async def current_user(x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")) -> dict:
    try:
        validated = validate_init_data(x_telegram_init_data or "", BOT_TOKEN)
    except TelegramAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    user = validated["user"]
    bot = getattr(app.state, "bot", None)
    if bot is None:
        raise HTTPException(status_code=503, detail="سرویس عضویت فعلاً در دسترس نیست")
    joined, _missing, verification_error = await membership_status(bot, int(user["id"]))
    if verification_error:
        raise HTTPException(status_code=503, detail="بررسی عضویت کانال‌ها ممکن نیست؛ مدیر باید دسترسی ربات به کانال‌ها را بررسی کند")
    if not joined:
        raise HTTPException(status_code=403, detail={
            "message": "برای ورود به پادشاهان زیرزمین باید عضو هر دو کانال باشی 👑",
            "channels": [
                {"username": channel, "title": label, "url": url}
                for channel, label, url in REQUIRED_CHANNELS
            ],
        })
    name = " ".join(x for x in (user.get("first_name", ""), user.get("last_name", "")) if x).strip() or str(user["id"])
    await upsert_user(int(user["id"]), user.get("username"), name)
    async with db().acquire() as conn:
        banned = await conn.fetchval("SELECT is_banned FROM users WHERE telegram_id=$1", int(user["id"]))
    if banned:
        raise HTTPException(status_code=403, detail="حساب شما مسدود شده است. با پشتیبانی تماس بگیر.")
    return user


@app.post("/telegram/webhook", include_in_schema=False)
async def telegram_webhook(request: Request, x_telegram_bot_api_secret_token: str | None = Header(default=None)):
    expected = getattr(app.state, "webhook_secret", None)
    if not expected or not x_telegram_bot_api_secret_token or not secrets.compare_digest(expected, x_telegram_bot_api_secret_token):
        raise HTTPException(status_code=403, detail="invalid webhook secret")
    try:
        from aiogram.types import Update
        payload = await request.json()
        update = Update.model_validate(payload, context={"bot": app.state.bot})
        await app.state.dispatcher.feed_update(app.state.bot, update)
    except HTTPException:
        raise
    except Exception as exc:
        logging.exception("Telegram webhook update failed")
        raise HTTPException(status_code=500, detail="update processing failed") from exc
    return {"ok": True}




# ─── Staff / Admin panel ─────────────────────────────────────────────
@app.get("/api/staff/me")
async def staff_me(user: dict = Depends(current_user)):
    return await staff_service.staff_profile(int(user["id"]))


@app.get("/api/staff/list")
async def staff_list(user: dict = Depends(current_user)):
    try:
        await staff_service.require_perm(int(user["id"]), "manage_staff")
    except ValueError:
        await staff_service.require_perm(int(user["id"]), "view_players")
    return await staff_service.list_staff()


@app.post("/api/staff/grant")
async def staff_grant(body: StaffGrantRequest, user: dict = Depends(current_user)):
    try:
        profile = await staff_service.grant_role(int(user["id"]), body.telegram_id, body.role, body.note)
        return {"ok": True, "message": "مقام اعطا شد.", "profile": profile}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/staff/revoke")
async def staff_revoke(body: StaffRevokeRequest, user: dict = Depends(current_user)):
    try:
        await staff_service.revoke_role(int(user["id"]), body.telegram_id)
        return {"ok": True, "message": "مقام لغو شد."}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/staff/ban")
async def staff_ban(body: StaffBanRequest, user: dict = Depends(current_user)):
    try:
        await staff_service.ban_user(int(user["id"]), body.telegram_id, body.banned)
        return {"ok": True, "message": "مسدود شد." if body.banned else "رفع مسدودیت انجام شد."}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/staff/coins")
async def staff_coins(body: StaffCoinsRequest, user: dict = Depends(current_user)):
    try:
        result = await staff_service.adjust_coins(int(user["id"]), body.telegram_id, body.amount, body.mode)
        return {"ok": True, "message": f"موجودی جدید: {result['coins']}", **result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/staff/players")
async def staff_players(q: str = "", user: dict = Depends(current_user)):
    try:
        return await staff_service.lookup_player(int(user["id"]), q)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/staff/chat/delete")
async def staff_delete_chat(body: StaffDeleteChatRequest, user: dict = Depends(current_user)):
    try:
        await staff_service.delete_global_message(int(user["id"]), body.message_id)
        return {"ok": True, "message": "پیام حذف شد."}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/staff/audit")
async def staff_audit(limit: int = 30, user: dict = Depends(current_user)):
    try:
        return await staff_service.recent_audit(int(user["id"]), limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.get("/api/health")
async def health():
    # A successful DB check helps Render detect a broken deployment.
    try:
        async with db().acquire() as conn:
            await conn.fetchval("SELECT 1")
    except Exception as exc:
        logging.exception("Health check failed")
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {"status": "ok", "version": "0.31.0"}


@app.get("/api/me")
async def me(user: dict = Depends(current_user)):
    user_id = int(user["id"])
    async with db().acquire() as conn:
        row = await conn.fetchrow("SELECT telegram_id,display_name,coins,games_played,wins FROM users WHERE telegram_id=$1", user_id)
    army = await empire_service.army_for(user_id)
    cities = await empire_service.my_cities(user_id)
    staff = await staff_service.staff_profile(user_id)
    return {
        "telegram_id": user_id,
        "name": row["display_name"],
        "display_name": row["display_name"],
        "coins": int(row["coins"]),
        "games_played": int(row["games_played"]),
        "wins": int(row["wins"]),
        "soldiers": army["soldiers"],
        "army_power": army_power_bonus(army["soldiers"]),
        "cities_owned": len(cities),
        "staff": staff,
    }


@app.get("/api/empire/equipment")
async def get_equipment(user: dict = Depends(current_user)):
    return await equipment_service.dashboard(int(user["id"]))


@app.post("/api/empire/equipment/buy")
async def buy_equipment(body: EquipmentPurchaseRequest, user: dict = Depends(current_user)):
    try:
        return await equipment_service.buy(int(user["id"]), body.item_key, body.quantity)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/empire/equipment/equip")
async def equip_equipment(body: EquipmentEquipRequest, user: dict = Depends(current_user)):
    try:
        return await equipment_service.equip(int(user["id"]), body.item_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/empire/equipment/box")
async def open_equipment_box(body: EquipmentBoxRequest, user: dict = Depends(current_user)):
    try:
        return await equipment_service.open_box(int(user["id"]), body.request_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/empire/cities")
async def cities(_: dict = Depends(current_user)):
    rows = await empire_service.cities_list()
    return [{
        "key": r["city_key"], "name": r["name"], "price": int(r["price"]),
        "tax_income": int(r["tax_income"]), "description": r["description"],
        "owner_id": r["owner_id"], "owner_name": r["owner_name"],
        "defense_level": int(r["defense_level"]),
    } for r in rows]


@app.get("/api/empire/assets")
async def assets(user: dict = Depends(current_user)):
    rows = await empire_service.assets_for(int(user["id"]))
    return [{"key": r["asset_key"], "name": ASSETS[r["asset_key"]]["name"], "level": int(r["level"]), "hourly_income": hourly_income(r["asset_key"], int(r["level"]))} for r in rows]


@app.post("/api/empire/daily")
async def daily(user: dict = Depends(current_user)):
    try:
        reward, balance = await empire_service.claim_daily(int(user["id"]))
        return {"ok": True, "reward": reward, "coins": balance}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/empire/work")
async def work(user: dict = Depends(current_user)):
    try:
        reward, balance = await empire_service.work(int(user["id"]))
        return {"ok": True, "reward": reward, "coins": balance}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/empire/recruit")
async def recruit(body: RecruitRequest, user: dict = Depends(current_user)):
    try:
        count, cost, balance = await empire_service.recruit_soldiers(int(user["id"]), body.count)
        army = await empire_service.army_for(int(user["id"]))
        return {"ok": True, "recruited": count, "cost": cost, "coins": balance, "soldiers": army["soldiers"]}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/empire/cities/{city_key}/buy")
async def buy_city(city_key: str, user: dict = Depends(current_user)):
    try:
        name, cost, balance = await empire_service.city_buy(int(user["id"]), city_key)
        return {"ok": True, "name": name, "cost": cost, "coins": balance}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/empire/cities/{city_key}/tax")
async def collect_tax(city_key: str, user: dict = Depends(current_user)):
    try:
        name, amount, balance = await empire_service.collect_tax(int(user["id"]), city_key)
        return {"ok": True, "name": name, "tax": amount, "coins": balance}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/empire/wars")
async def empire_wars(user: dict = Depends(current_user)):
    rows = await empire_service.war_history(int(user["id"]), limit=20)
    return [{
        "id": int(r["id"]),
        "attacker_id": int(r["attacker_id"]),
        "defender_id": int(r["defender_id"]),
        "attacker_name": r["attacker_name"],
        "defender_name": r["defender_name"],
        "attack_city_key": r["attack_city_key"],
        "target_city_key": r["target_city_key"],
        "attack_city_name": r["attack_city_name"],
        "target_city_name": r["target_city_name"],
        "attack_power": int(r["attack_power"]),
        "defense_power": int(r["defense_power"]) if r["defense_power"] is not None else None,
        "status": r["status"],
        "fee": int(r["fee"]),
        "created_at": r["created_at"].isoformat(),
        "resolves_at": r["resolves_at"].isoformat(),
        "resolved_at": r["resolved_at"].isoformat() if r["resolved_at"] else None,
    } for r in rows]


@app.post("/api/empire/wars")
async def declare_empire_war(body: DeclareWarRequest, user: dict = Depends(current_user)):
    user_id = int(user["id"])
    try:
        war_id, attack_name, target_name, fee, balance, resolves_at, defender_id, power = await empire_service.declare_war(
            user_id, body.attack_city_key, body.target_city_key
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        await app.state.bot.send_message(
            defender_id,
            f"⚔️ علیه قلمرو «{target_name}» جنگ اعلام شد!\n"
            f"مبدأ حمله: {attack_name}\nقدرت اولیهٔ مهاجم: {power}\n"
            f"نتیجه پس از آماده‌سازی ۱۰ دقیقه‌ای مشخص می‌شود. جنگ شمارهٔ {war_id}."
        )
    except Exception as exc:
        logging.info("Could not notify war defender %s: %s", defender_id, exc)
    return {
        "ok": True, "war_id": war_id, "attack_city": attack_name, "target_city": target_name,
        "fee": fee, "coins": balance, "attack_power": power, "resolves_at": resolves_at.isoformat(),
    }


# Alliance warfare (v0.22)
from games.empire import alliance_wars as alliance_war_service

@app.get("/api/empire/alliance/wars")
async def list_alliance_wars(user: dict = Depends(current_user)):
    rows = await alliance_war_service.alliance_war_history(int(user["id"]), limit=20)
    return [{"id": int(r["id"]), "attacker_name": r["attacker_name"], "defender_name": r["defender_name"],
        "target_name": r["target_name"], "target_city_key": r["target_city_key"], "attack_power": int(r["attack_power"]),
        "defense_power": int(r["defense_power"]) if r["defense_power"] is not None else None, "status": r["status"],
        "fee": int(r["fee"]), "created_at": r["created_at"].isoformat(), "resolves_at": r["resolves_at"].isoformat(),
        "resolved_at": r["resolved_at"].isoformat() if r["resolved_at"] else None} for r in rows]

@app.post("/api/empire/alliance/wars")
async def declare_alliance_war(body: DeclareAllianceWarRequest, user: dict = Depends(current_user)):
    try:
        result = await alliance_war_service.declare_alliance_war(int(user["id"]), body.target_city_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    war_message = f"⚔️ اتحاد «{result['attacker_alliance']}» به قلمرو «{result['target_name']}» حمله کرده است!\nقدرت اولیهٔ حمله: {result['attack_power']}\nنتیجه پس از ۱۰ دقیقه مشخص می‌شود. جنگ شمارهٔ {result['id']}."
    for user_id in {result["defender_leader_id"]}:
        try: await app.state.bot.send_message(user_id, war_message)
        except Exception as exc: logging.info("Could not notify defender alliance leader: %s", exc)
    await alliance_notification_service.notify_alliance_members(app.state.bot, int(result["defender_alliance_id"]) if "defender_alliance_id" in result else int(await db().fetchval("SELECT alliance_id FROM empire_alliance_members WHERE telegram_id=$1", result["defender_leader_id"])), "war", "حمله به اتحاد", war_message, actor_id=int(user["id"]))
    await alliance_notification_service.notify_alliance_members(app.state.bot, int(await db().fetchval("SELECT alliance_id FROM empire_alliance_members WHERE telegram_id=$1", int(user["id"]))), "war", "اعلام جنگ اتحاد", f"جنگ با هدف «{result['target_name']}» آغاز شد و نتیجه پس از ۱۰ دقیقه مشخص می‌شود.", actor_id=int(user["id"]), exclude_actor=True)
    return {"ok": True, **{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k,v in result.items() if k not in ("defender_leader_id", "attacker_leader_id")}}

# Alliance economy: shared treasury, daily rewards, and transparent contribution stats (v0.25)
from games.empire import alliance_economy as alliance_economy_service
from api.schemas import AllianceTreasuryTransferRequest

@app.get("/api/empire/alliance/treasury")
async def get_alliance_treasury(user: dict = Depends(current_user)):
    try:
        result = await alliance_economy_service.treasury_summary(int(user["id"]))
        result["last_daily_claim"] = result["last_daily_claim"].isoformat() if result["last_daily_claim"] else None
        result["transactions"] = [{**r, "id": int(r["id"]), "amount": int(r["amount"]), "created_at": r["created_at"].isoformat()} for r in result["transactions"]]
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.post("/api/empire/alliance/treasury/deposit")
async def deposit_alliance_treasury(body: AllianceTreasuryTransferRequest, user: dict = Depends(current_user)):
    try:
        result = await alliance_economy_service.deposit(int(user["id"]), body.amount)
        await alliance_notification_service.notify_user_alliance(app.state.bot, int(user["id"]), "treasury", "واریز به خزانه", f"{body.amount} سکه به خزانهٔ اتحاد واریز شد.", exclude_actor=True)
        return {"ok": True, **result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.post("/api/empire/alliance/treasury/withdraw")
async def withdraw_alliance_treasury(body: AllianceTreasuryTransferRequest, user: dict = Depends(current_user)):
    try:
        result = await alliance_economy_service.withdraw(int(user["id"]), body.amount)
        await alliance_notification_service.notify_user_alliance(app.state.bot, int(user["id"]), "treasury", "برداشت از خزانه", f"{body.amount} سکه از خزانهٔ اتحاد برداشت شد.", exclude_actor=True)
        return {"ok": True, **result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.post("/api/empire/alliance/daily-bonus")
async def claim_alliance_daily_bonus(user: dict = Depends(current_user)):
    try:
        result = await alliance_economy_service.claim_daily_bonus(int(user["id"]))
        result["claimed_at"] = result["claimed_at"].isoformat()
        return {"ok": True, **result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.get("/api/empire/alliance/contributions")
async def get_alliance_contributions(user: dict = Depends(current_user)):
    try:
        rows = await alliance_economy_service.member_contributions(int(user["id"]))
        return [{**r, "telegram_id": int(r["telegram_id"]), "support_coins": int(r["support_coins"]),
                 "support_count": int(r["support_count"]), "treasury_deposits": int(r["treasury_deposits"]),
                 "cities_owned": int(r["cities_owned"]), "soldiers": int(r["soldiers"])} for r in rows]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# Alliance buildings and defensive shield (v0.26)
from games.empire import alliance_buildings as alliance_buildings_service
from api.schemas import AllianceBuildingUpgradeRequest

@app.get("/api/empire/alliance/buildings")
async def get_alliance_buildings(user: dict = Depends(current_user)):
    try: return await alliance_buildings_service.overview(int(user["id"]))
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.post("/api/empire/alliance/buildings/upgrade")
async def upgrade_alliance_building(body: AllianceBuildingUpgradeRequest, user: dict = Depends(current_user)):
    try:
        result = await alliance_buildings_service.upgrade(int(user["id"]), body.building)
        await alliance_notification_service.notify_user_alliance(app.state.bot, int(user["id"]), "buildings", "ارتقای ساختمان اتحاد", f"ساختمان «{result['name']}» به سطح {result['level']} ارتقا یافت؛ هزینه: {result['cost']} سکه.", exclude_actor=True)
        return result
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.post("/api/empire/alliance/shield")
async def activate_alliance_shield(user: dict = Depends(current_user)):
    try:
        result = await alliance_buildings_service.activate_shield(int(user["id"]))
        await alliance_notification_service.notify_user_alliance(app.state.bot, int(user["id"]), "buildings", "سپر دفاعی فعال شد", "سپر دفاعی اتحاد برای ۶ ساعت فعال شد.", exclude_actor=True)
        return result
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.get("/", include_in_schema=False)
async def web_app():
    return FileResponse(BASE_DIR / "web" / "index.html")


# Alliance and public leaderboard endpoints (v0.20)
from games.empire import alliances as alliance_service
from api.schemas import (CreateAllianceRequest, JoinAllianceRequest, ManageAllianceRequest,
    TransferLeadershipRequest, KickAllianceMemberRequest, AllianceMessageRequest,
    AlliancePactRequest, DecideAlliancePactRequest)


@app.get("/api/empire/alliances")
async def list_empire_alliances(search: str = "", user: dict = Depends(current_user)):
    rows = await alliance_service.list_alliances(limit=30, search=search)
    return [{**r, "id": int(r["id"]), "leader_id": int(r["leader_id"]), "member_count": int(r["member_count"]), "cities_owned": int(r["cities_owned"])} for r in rows]


@app.get("/api/empire/alliance/me")
async def get_my_alliance(user: dict = Depends(current_user)):
    row = await alliance_service.my_alliance(int(user["id"]))
    if not row:
        return {"alliance": None, "requests": []}
    result = dict(row)
    result["id"] = int(result["id"])
    result["leader_id"] = int(result["leader_id"])
    result["member_count"] = int(result["member_count"])
    result["created_at"] = result["created_at"].isoformat()
    result["is_leader"] = int(user["id"]) == result["leader_id"]
    requests = await alliance_service.incoming_requests(int(user["id"])) if result["is_leader"] else []
    result_requests = [{**r, "id": int(r["id"]), "alliance_id": int(r["alliance_id"]), "requester_id": int(r["requester_id"]), "created_at": r["created_at"].isoformat()} for r in requests]
    return {"alliance": result, "requests": result_requests}


@app.post("/api/empire/alliances")
async def create_empire_alliance(body: CreateAllianceRequest, user: dict = Depends(current_user)):
    try:
        row = await alliance_service.create_alliance(int(user["id"]), body.name, body.tag)
        row["id"] = int(row["id"])
        row["leader_id"] = int(row["leader_id"])
        row["created_at"] = row["created_at"].isoformat()
        return {"ok": True, "alliance": row}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/empire/alliances/request")
async def request_empire_alliance(body: JoinAllianceRequest, user: dict = Depends(current_user)):
    try:
        return {"ok": True, **await alliance_service.request_to_join(int(user["id"]), body.alliance_id)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/empire/alliance/requests")
async def list_empire_alliance_requests(user: dict = Depends(current_user)):
    rows = await alliance_service.incoming_requests(int(user["id"]))
    return [{**r, "id": int(r["id"]), "alliance_id": int(r["alliance_id"]), "requester_id": int(r["requester_id"]), "created_at": r["created_at"].isoformat()} for r in rows]


@app.post("/api/empire/alliance/requests/{request_id}")
async def decide_empire_alliance_request(request_id: int, body: ManageAllianceRequest, user: dict = Depends(current_user)):
    try:
        return {"ok": True, **await alliance_service.manage_request(int(user["id"]), request_id, body.accept)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/empire/alliance/leave")
async def leave_empire_alliance(user: dict = Depends(current_user)):
    try:
        name = await alliance_service.leave_alliance(int(user["id"]))
        return {"ok": True, "name": name}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/empire/alliances/top")
async def top_empire_alliances(user: dict = Depends(current_user)):
    rows = await alliance_service.alliance_leaderboard()
    return [{**r, "id": int(r["id"]), "member_count": int(r["member_count"]), "cities_owned": int(r["cities_owned"]), "territory_value": int(r["territory_value"])} for r in rows]


@app.get("/api/leaderboard")
async def top_empire_players(user: dict = Depends(current_user)):
    rows = await alliance_service.player_leaderboard()
    return [{**r, "telegram_id": int(r["telegram_id"]), "games_played": int(r["games_played"]), "wins": int(r["wins"]), "coins": int(r["coins"]), "cities_owned": int(r["cities_owned"]), "territory_value": int(r["territory_value"]), "soldiers": int(r["soldiers"])} for r in rows]


# Alliance leadership, private member chat, and seven-day non-aggression pacts (v0.21)
@app.get("/api/empire/alliance/members")
async def get_alliance_members(user: dict = Depends(current_user)):
    try:
        rows = await alliance_service.alliance_members(int(user["id"]))
        return [{**r, "telegram_id": int(r["telegram_id"]), "cities_owned": int(r["cities_owned"]), "joined_at": r["joined_at"].isoformat(), "is_me": int(r["telegram_id"]) == int(user["id"])} for r in rows]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/empire/alliance/transfer")
async def transfer_alliance_leadership(body: TransferLeadershipRequest, user: dict = Depends(current_user)):
    try:
        name = await alliance_service.transfer_leadership(int(user["id"]), body.new_leader_id)
        return {"ok": True, "name": name}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/empire/alliance/kick")
async def kick_alliance_member(body: KickAllianceMemberRequest, user: dict = Depends(current_user)):
    try:
        name = await alliance_service.kick_member(int(user["id"]), body.telegram_id)
        return {"ok": True, "name": name}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/empire/alliance/messages")
async def get_alliance_messages(after_id: int = 0, user: dict = Depends(current_user)):
    try:
        rows = await alliance_service.alliance_messages(int(user["id"]), after_id=max(0, after_id))
        return [{**r, "id": int(r["id"]), "sender_id": int(r["sender_id"]), "created_at": r["created_at"].isoformat(), "is_me": int(r["sender_id"]) == int(user["id"])} for r in rows]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/empire/alliance/messages")
async def post_alliance_message(body: AllianceMessageRequest, user: dict = Depends(current_user)):
    try:
        row = await alliance_service.send_alliance_message(int(user["id"]), body.message)
        return {"ok": True, "id": row["id"], "created_at": row["created_at"].isoformat()}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc




@app.get("/api/chat/messages")
async def get_global_chat(after_id: int = 0, limit: int = 50, user: dict = Depends(current_user)):
    """Global public chat for all players."""
    limit = max(1, min(100, limit))
    after_id = max(0, after_id)
    async with db().acquire() as conn:
        if after_id > 0:
            rows = await conn.fetch(
                """SELECT m.id, m.sender_id, m.message, m.created_at,
                          COALESCE(u.display_name, u.username, 'بازیکن') AS display_name
                   FROM global_chat_messages m
                   JOIN users u ON u.telegram_id = m.sender_id
                   WHERE m.id > $1
                   ORDER BY m.id ASC
                   LIMIT $2""",
                after_id, limit,
            )
        else:
            rows = await conn.fetch(
                """SELECT m.id, m.sender_id, m.message, m.created_at,
                          COALESCE(u.display_name, u.username, 'بازیکن') AS display_name
                   FROM global_chat_messages m
                   JOIN users u ON u.telegram_id = m.sender_id
                   ORDER BY m.id DESC
                   LIMIT $1""",
                limit,
            )
            rows = list(reversed(rows))
    uid = int(user["id"])
    return [
        {
            "id": int(r["id"]),
            "sender_id": int(r["sender_id"]),
            "message": r["message"],
            "display_name": r["display_name"],
            "created_at": r["created_at"].isoformat(),
            "is_me": int(r["sender_id"]) == uid,
        }
        for r in rows
    ]


@app.post("/api/chat/messages")
async def post_global_chat(body: AllianceMessageRequest, user: dict = Depends(current_user)):
    """Post a message to global chat (reuses message length validation from alliance schema)."""
    message = " ".join((body.message or "").split()).strip()
    if not 1 <= len(message) <= 300:
        raise HTTPException(status_code=400, detail="پیام باید بین ۱ تا ۳۰۰ نویسه باشد.")
    async with db().acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO global_chat_messages(sender_id, message)
               VALUES($1, $2)
               RETURNING id, created_at""",
            int(user["id"]), message,
        )
    return {"ok": True, "id": int(row["id"]), "created_at": row["created_at"].isoformat()}

@app.get("/api/empire/alliance/pacts")
async def get_alliance_pacts(user: dict = Depends(current_user)):
    rows = await alliance_service.list_pacts(int(user["id"]))
    return [{**r, "id": int(r["id"]), "other_id": int(r["other_id"]), "initiated_by": int(r["initiated_by"]), "created_at": r["created_at"].isoformat(), "expires_at": r["expires_at"].isoformat()} for r in rows]


@app.post("/api/empire/alliance/pacts")
async def create_alliance_pact(body: AlliancePactRequest, user: dict = Depends(current_user)):
    try:
        row = await alliance_service.offer_pact(int(user["id"]), body.alliance_id)
        return {"ok": True, **row, "expires_at": row["expires_at"].isoformat()}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/empire/alliance/pacts/{pact_id}")
async def decide_alliance_pact(pact_id: int, body: DecideAlliancePactRequest, user: dict = Depends(current_user)):
    try:
        return {"ok": True, **await alliance_service.decide_pact(int(user["id"]), pact_id, body.accept)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

# Defensive reinforcements and quarterly alliance ranking (v0.24)
from api.schemas import SupportAllianceWarRequest

@app.post("/api/empire/alliance/wars/{war_id}/support")
async def support_empire_alliance_war(war_id: int, body: SupportAllianceWarRequest, user: dict = Depends(current_user)):
    from games.empire import alliance_wars as alliance_war_service
    try:
        result = await alliance_war_service.support_alliance_war(int(user["id"]), war_id, body.coins)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, **result}

@app.get("/api/empire/alliance/season")
async def empire_alliance_season(user: dict = Depends(current_user)):
    from games.empire import alliance_wars as alliance_war_service
    season, rows = await alliance_war_service.alliance_season_leaderboard(limit=20)
    return {"season": season, "alliances": [{
        "alliance_id": int(r["alliance_id"]), "name": r["name"], "tag": r["tag"],
        "points": int(r["points"]), "wins": int(r["wins"]), "losses": int(r["losses"]),
        "member_count": int(r["member_count"]),
    } for r in rows]}


# Internal alliance ranks and treasury audit history (v0.27)
from api.schemas import AllianceRankRequest
from games.empire import alliance_ranks as alliance_rank_service

@app.post("/api/empire/alliance/rank")
async def set_empire_alliance_rank(body: AllianceRankRequest, user: dict = Depends(current_user)):
    try:
        result = await alliance_rank_service.set_member_rank(int(user["id"]), body.telegram_id, body.rank)
        await alliance_notification_service.notify_user_alliance(app.state.bot, int(user["id"]), "rank", "تغییر رتبهٔ عضو", f"رتبهٔ یک عضو به «{result['rank_name']}» تغییر یافت.", exclude_actor=True)
        return {"ok": True, **result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.get("/api/empire/alliance/finance-history")
async def get_empire_alliance_finance_history(limit: int = 30, user: dict = Depends(current_user)):
    try:
        rows = await alliance_rank_service.finance_history(int(user["id"]), limit=limit)
        return [{**r, "id": int(r["id"]), "actor_id": int(r["actor_id"]), "amount": int(r["amount"]), "created_at": r["created_at"].isoformat()} for r in rows]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# Alliance event inbox and per-category notification settings (v0.28)
from games.empire import alliance_notifications as alliance_notification_service
from api.schemas import AllianceNotificationPreferencesRequest, MarkAllianceNotificationReadRequest

@app.get("/api/empire/alliance/notifications")
async def get_alliance_notifications(limit: int = 30, user: dict = Depends(current_user)):
    rows = await alliance_notification_service.list_notifications(int(user["id"]), limit)
    return [{**r, "id": int(r["id"]), "is_read": bool(r["is_read"]), "created_at": r["created_at"].isoformat()} for r in rows]

@app.post("/api/empire/alliance/notifications/read")
async def mark_alliance_notifications_read(body: MarkAllianceNotificationReadRequest, user: dict = Depends(current_user)):
    count = await alliance_notification_service.mark_read(int(user["id"]), body.notification_id)
    return {"ok": True, "updated": count}

@app.get("/api/empire/alliance/notification-preferences")
async def get_alliance_notification_preferences(user: dict = Depends(current_user)):
    return await alliance_notification_service.get_preferences(int(user["id"]))

@app.post("/api/empire/alliance/notification-preferences")
async def update_alliance_notification_preferences(body: AllianceNotificationPreferencesRequest, user: dict = Depends(current_user)):
    try:
        return await alliance_notification_service.update_preferences(int(user["id"]), body.telegram_enabled, body.categories)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# Alliance history and internal voting (v0.29)
from api.schemas import AllianceProposalRequest, AllianceVoteRequest
from games.empire import alliance_governance as alliance_governance_service

@app.get("/api/empire/alliance/history")
async def get_alliance_history(limit: int = 50, user: dict = Depends(current_user)):
    try:
        rows = await alliance_governance_service.history(int(user["id"]), limit)
        return [{**r, "id": int(r["id"]), "actor_id": int(r["actor_id"]) if r["actor_id"] is not None else None, "created_at": r["created_at"].isoformat()} for r in rows]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.get("/api/empire/alliance/proposals")
async def get_alliance_proposals(limit: int = 30, user: dict = Depends(current_user)):
    try:
        rows = await alliance_governance_service.list_proposals(int(user["id"]), limit)
        return [{**r, "id": int(r["id"]), "creator_id": int(r["creator_id"]) if r["creator_id"] is not None else None, "yes_votes": int(r["yes_votes"]), "no_votes": int(r["no_votes"]), "eligible_voters": int(r["eligible_voters"]), "my_vote": r["my_vote"], "expires_at": r["expires_at"].isoformat(), "created_at": r["created_at"].isoformat()} for r in rows]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.post("/api/empire/alliance/proposals")
async def create_alliance_proposal(body: AllianceProposalRequest, user: dict = Depends(current_user)):
    try:
        row = await alliance_governance_service.create_proposal(int(user["id"]), body.title, body.description, body.duration_hours)
        row["expires_at"] = row["expires_at"].isoformat(); row["created_at"] = row["created_at"].isoformat()
        await alliance_notification_service.notify_user_alliance(app.state.bot, int(user["id"]), "general", "رأی‌گیری جدید اتحاد", row["title"], exclude_actor=True)
        return {"ok": True, **row}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.post("/api/empire/alliance/proposals/{proposal_id}/vote")
async def vote_alliance_proposal(proposal_id: int, body: AllianceVoteRequest, user: dict = Depends(current_user)):
    try:
        return {"ok": True, **await alliance_governance_service.cast_vote(int(user["id"]), proposal_id, body.choice)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# Player progression, daily/weekly missions and achievements (v0.30)
from games.empire import progression as progression_service
from pydantic import BaseModel, Field

class MissionClaimRequest(BaseModel):
    mission_key: str = Field(min_length=1, max_length=64)
    kind: str = Field(pattern=r"^(daily|weekly)$")

class AchievementClaimRequest(BaseModel):
    achievement_key: str = Field(min_length=1, max_length=64)

@app.get("/api/progression")
async def get_progression(user: dict = Depends(current_user)):
    return await progression_service.dashboard(int(user["id"]))

@app.post("/api/progression/missions/claim")
async def claim_progression_mission(body: MissionClaimRequest, user: dict = Depends(current_user)):
    try:
        return await progression_service.claim_mission(int(user["id"]), body.mission_key, body.kind)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.post("/api/progression/achievements/claim")
async def claim_progression_achievement(body: AchievementClaimRequest, user: dict = Depends(current_user)):
    try:
        return await progression_service.claim_achievement(int(user["id"]), body.achievement_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
