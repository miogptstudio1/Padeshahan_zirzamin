import asyncio, logging
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN
from core.database import connect_db, close_db
from handlers.main import router as main_router
from handlers.callbacks import router as callbacks_router
from handlers.mafia import router as mafia_router, restore_active_timers
from handlers.coup import router as coup_router, restore_coup_timers
from handlers.empire import router as empire_router
from handlers.admin import router as admin_router
from handlers.shop import router as shop_router
from handlers.events import router as events_router
from handlers.family import router as family_router
from handlers.crime import router as crime_router
from games.empire import service as empire_service
from games.empire.engine import war_result_message
from membership import RequiredMembershipMiddleware

async def empire_war_scheduler(bot):
 """Poll PostgreSQL for expired wars and notify both sides automatically."""
 while True:
  try:
   results = await empire_service.resolve_expired_wars(limit=20)
   for result in results:
    message = war_result_message(result)
    for user_id in {result['attacker_id'], result['defender_id']}:
     try:
      await bot.send_message(user_id, message)
     except Exception as exc:
      logging.info('Could not notify user %s about war %s: %s', user_id, result['id'], exc)
  except asyncio.CancelledError:
   raise
  except Exception:
   logging.exception('Empire war scheduler failed; will retry')
  await asyncio.sleep(15)

async def main():
 if not BOT_TOKEN: raise RuntimeError('BOT_TOKEN در فایل .env تنظیم نشده است.')
 logging.basicConfig(level=logging.INFO)
 await connect_db()
 bot=Bot(BOT_TOKEN)
 restored = await restore_active_timers(bot)
 logging.info('Restored %s active Mafia phase timer(s)', restored)
 restored_coup = await restore_coup_timers(bot)
 logging.info('Restored %s active Coup claim timer(s)', restored_coup)
 dp=Dispatcher()
 membership_middleware = RequiredMembershipMiddleware()
 dp.message.outer_middleware(membership_middleware)
 dp.callback_query.outer_middleware(membership_middleware)
 war_task = asyncio.create_task(empire_war_scheduler(bot))
 dp.include_router(main_router)
 dp.include_router(admin_router)
 dp.include_router(shop_router)
 dp.include_router(events_router)
 dp.include_router(family_router)
 dp.include_router(crime_router)
 dp.include_router(callbacks_router)
 dp.include_router(mafia_router)
 dp.include_router(coup_router)
 dp.include_router(empire_router)
 try:
  await dp.start_polling(bot)
 finally:
  war_task.cancel()
  try:
   await war_task
  except asyncio.CancelledError:
   pass
  await bot.session.close()
  await close_db()
if __name__=='__main__': asyncio.run(main())
