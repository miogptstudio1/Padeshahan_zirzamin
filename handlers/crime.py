"""حمله، جیب‌بری، قاچاق، باج‌گیری — با ریپلای یا آیدی."""
from __future__ import annotations
import re

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from games.empire import crime as crime_service

router = Router()


def _target_id(message: Message) -> int | None:
    if message.reply_to_message and message.reply_to_message.from_user:
        return int(message.reply_to_message.from_user.id)
    text = message.text or ""
    # last number in message
    nums = re.findall(r"\d{5,15}", text)
    if nums:
        return int(nums[-1])
    return None


@router.message(Command("attack", "حمله"))
@router.message(F.text.regexp(r"^(?:حمله|/attack)\b"))
async def cmd_attack(message: Message):
    tid = _target_id(message)
    if not tid:
        await message.answer(
            "⚔️ برای حمله:\n"
            "• ریپلای روی پیام بازیکن + <code>حمله</code>\n"
            "• یا: <code>حمله 123456789</code>\n\n"
            "کول‌داون ۱۵ دقیقه · سکه از پناهگاه هدف دزدیده می‌شه.",
            parse_mode="HTML",
        )
        return
    try:
        r = await crime_service.attack_player(message.from_user.id, tid)
        if r["won"]:
            await message.answer(
                f"💥 حمله موفق به <b>{r['defender_name']}</b>!\n"
                f"⚔️ قدرت تو {r['attacker_power']} vs {r['defender_power']}\n"
                f"🪙 غنیمت: +{r['stolen']:,}\n"
                f"❤️ آسیب: −{r.get('hp_damage', 0)} (جان هدف: {r.get('defender_hp', '?')})\n"
                f"موجودی: {r['balance']:,}",
                parse_mode="HTML",
            )
            try:
                await message.bot.send_message(
                    tid,
                    f"⚠️ به پناهگاهت حمله شد!\n"
                    f"مهاجم: {message.from_user.full_name or message.from_user.id}\n"
                    f"ضرر: −{r['stolen']:,} سکه",
                )
            except Exception:
                pass
        else:
            await message.answer(
                f"🛡️ حمله به <b>{r['defender_name']}</b> شکست خورد.\n"
                f"قدرت: {r['attacker_power']} vs {r['defender_power']}\n"
                f"جریمه: −{r['fee']:,} سکه\nموجودی: {r['balance']:,}",
                parse_mode="HTML",
            )
    except ValueError as e:
        await message.answer(f"❌ {e}")


@router.message(Command("steal", "جیب‌بری", "دزدی"))
@router.message(F.text.regexp(r"^(?:جیب‌بری|جیب بری|دزدی|/steal)\b"))
async def cmd_steal(message: Message):
    tid = _target_id(message)
    if not tid:
        await message.answer("ریپلای کن یا بنویس: <code>جیب‌بری 123456</code>", parse_mode="HTML")
        return
    try:
        r = await crime_service.pickpocket(message.from_user.id, tid)
        if r["success"]:
            await message.answer(
                f"🧤 جیب‌بری از {r['target_name']}: +{r['amount']:,} سکه\nموجودی: {r['balance']:,}"
            )
        else:
            await message.answer(
                f"🚨 گیر افتادی! جریمه −{r['fine']:,}\nموجودی: {r['balance']:,}"
            )
    except ValueError as e:
        await message.answer(f"❌ {e}")


@router.message(Command("smuggle", "قاچاق"))
@router.message(F.text.in_({"قاچاق", "قاچاق کالا", "smuggle"}))
async def cmd_smuggle(message: Message):
    try:
        r = await crime_service.smuggle(message.from_user.id)
        if r["success"]:
            await message.answer(f"🕶️ قاچاق موفق! +{r['amount']:,} سکه\nموجودی: {r['balance']:,}")
        else:
            await message.answer(
                f"🚔 محموله ضبط شد! −{abs(r['amount']):,} سکه\nموجودی: {r['balance']:,}"
            )
    except ValueError as e:
        await message.answer(f"❌ {e}")


@router.message(Command("extort", "باج", "باج‌گیری"))
@router.message(F.text.regexp(r"^(?:باج|باج‌گیری|باج گیری|/extort)\b"))
async def cmd_extort(message: Message):
    tid = _target_id(message)
    if not tid:
        await message.answer("ریپلای یا: <code>باج 123456</code>", parse_mode="HTML")
        return
    try:
        r = await crime_service.extort(message.from_user.id, tid)
        if r["success"]:
            await message.answer(
                f"💰 باج از {r['target_name']}: +{r['amount']:,}\nموجودی: {r['balance']:,}"
            )
        else:
            await message.answer(f"هدف زیر بار نرفت. موجودی: {r['balance']:,}")
    except ValueError as e:
        await message.answer(f"❌ {e}")


@router.message(Command("hideout", "پناهگاه"))
@router.message(F.text.in_({"پناهگاه", "خانه", "hideout"}))
async def cmd_hideout(message: Message):
    try:
        st = await crime_service.hideout_status(message.from_user.id)
        h = st["hideout"]
        await message.answer(
            f"🏚️ <b>{h.get('name', 'پناهگاه')}</b>\n"
            f"⭐ سطح: {h.get('level', 1)}\n"
            f"🛡️ دفاع: {h.get('defense', 0)}\n"
            f"❤️ جان: {h.get('hp', 100)}/{h.get('max_hp', 100)}\n"
            f"⚔️ قدرت کل تو: <b>{st['power']}</b>\n\n"
            f"هیل: <code>هیل</code> · ارتقا: <code>ارتقا پناهگاه</code>",
            parse_mode="HTML",
        )
    except ValueError as e:
        await message.answer(f"❌ {e}")


@router.message(Command("upgrade_hideout", "ارتقا_پناهگاه"))
@router.message(F.text.in_({"ارتقا پناهگاه", "ارتقای پناهگاه", "آپگرید پناهگاه"}))
async def cmd_upgrade_hideout(message: Message):
    try:
        r = await crime_service.upgrade_hideout(message.from_user.id)
        h = r["hideout"]
        await message.answer(
            f"✅ پناهگاه سطح {h['level']} شد (دفاع {h['defense']})\n"
            f"هزینه: {r['cost']:,} · موجودی: {r['balance']:,}"
        )
    except ValueError as e:
        await message.answer(f"❌ {e}")




@router.message(Command("heal", "هیل", "درمان"))
@router.message(F.text.in_({"هیل", "درمان", "heal", "شفا"}))
async def cmd_heal(message: Message):
    try:
        r = await crime_service.heal_self(message.from_user.id)
        await message.answer(
            f"💚 هیل کامل\n❤️ {r['hp']}/{r['max_hp']} (+{r['healed']})"
        )
    except ValueError as e:
        await message.answer(f"❌ {e}")


@router.message(Command("hp", "جان"))
@router.message(F.text.in_({"جان", "خون", "hp"}))
async def cmd_hp(message: Message):
    try:
        r = await crime_service.hp_status(message.from_user.id)
        await message.answer(
            f"❤️ جان: <b>{r['hp']}/{r['max_hp']}</b>\n"
            f"⚔️ قدرت: {r['power']}\n"
            f"برای بازیابی: <code>هیل</code>",
            parse_mode="HTML",
        )
    except ValueError as e:
        await message.answer(f"❌ {e}")

@router.message(Command("crime", "خلاف", "جرم"))
@router.message(F.text.in_({"خلاف", "جرم", "کارهای خلاف", "crime"}))
async def cmd_crime_help(message: Message):
    await message.answer(
        "🕶️ <b>دنیای زیرزمینی</b>\n\n"
        "⚔️ <code>حمله</code> — ریپلای یا حمله [آیدی]\n"
        "🧤 <code>جیب‌بری</code> — دزدی سبک\n"
        "💰 <code>باج</code> — باج‌گیری (قدرت بالاتر لازم)\n"
        "🕶️ <code>قاچاق</code> — محموله پرریسک\n"
        "🏚️ <code>پناهگاه</code> · <code>ارتقا پناهگاه</code>\n❤️ <code>جان</code> · <code>هیل</code>\n\n"
        "هر بازیکن از اول یک <b>پناهگاه کوچک</b> داره.",
        parse_mode="HTML",
    )
