"""بازی‌های گروهی جدید: جاسوس ناشناس · اتاق فرار · پادشاه خیانت."""
from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from handlers.panel_ui import panel_update
from games.minigames import rooms as R
from games.minigames import spyfall, escape, king
from games.minigames import island, detective, empirewar, auction, court, laststand
from games.minigames import bomb, treasure, wordwar
from games.minigames import solo as solo_games

router = Router()


async def _reward(uid: int, amount: int) -> None:
    if amount <= 0:
        return
    try:
        from core.database import db
        async with db().acquire() as conn:
            await conn.execute(
                "UPDATE users SET coins = coins + $2 WHERE telegram_id=$1",
                int(uid), int(amount),
            )
    except Exception:
        pass


LABELS = {
    "spyfall": "🕵️ جاسوس ناشناس",
    "escape": "🔐 اتاق فرار",
    "kingbetray": "👑 پادشاه خیانت",
    "island": "🏝️ جزیره گمشده",
    "detective": "🔎 کارآگاه خصوصی",
    "empirewar": "⚔️ نبرد امپراتوری‌ها",
    "auction": "💰 مزایده مرگبار",
    "court": "⚖️ دادگاه سلطنتی",
    "laststand": "🏁 آخرین بازمانده",
    "bomb": "💣 بمب ساعتی",
    "treasure": "🗺️ شکار گنج",
    "wordwar": "📝 نبرد کلمات",
}


def _name(message: Message) -> str:
    return (message.from_user.full_name or str(message.from_user.id))[:80]


def lobby_kb(game: str, room_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ پیوستن", callback_data=f"mg:{game}:join:{room_id}")],
        [
            InlineKeyboardButton(text="▶️ شروع", callback_data=f"mg:{game}:start:{room_id}"),
            InlineKeyboardButton(text="📊 وضعیت", callback_data=f"mg:{game}:status:{room_id}"),
        ],
        [InlineKeyboardButton(text="❌ لغو", callback_data=f"mg:{game}:cancel:{room_id}")],
    ])


async def lobby_text(game: str, room_id: int) -> str:
    pl = await R.players(room_id)
    lines = [
        f"{LABELS.get(game, game)} — اتاق #{room_id}",
        f"بازیکنان ({len(pl)}):",
    ]
    for i, p in enumerate(pl, 1):
        lines.append(f"{i}. {p['display_name']}")
    need = R.MIN_PLAYERS.get(game, 3)
    lines.append(f"\nحداقل {need} نفر · پیوستن / شروع")
    tips = {
        "spyfall": "یکی جاسوسه و مکان رو نمی‌دونه.",
        "escape": "با هم معما حل کنین قبل از تموم شدن وقت.",
        "kingbetray": "۳ دور تاج؛ یک خائن مخفی.",
        "island": "غذا محدوده. جمع · استراحت · دزدی",
        "detective": "سرنخ بگیرین و قاتل رو حدس بزنین.",
        "empirewar": "دو تیم قرمز/آبی — حمله یا دفاع.",
        "auction": "بودجه ۱۰۰؛ روی آیتم‌ها پیشنهاد بدین.",
        "court": "یکی متهمه؛ گناهکار یا بیگناه رأی بدین.",
        "laststand": "هر دور یکی با رأی حذف می‌شه تا یکی بمونه.",
        "bomb": "بمب رو پاس بده قبل از انفجار.",
        "treasure": "با سرنخ جای گنج رو پیدا کن.",
        "wordwar": "کلمه با حرف آخر قبلی.",
    }
    if game in tips:
        lines.append(tips[game])
    return "\n".join(lines)


async def _create(message: Message, game: str):
    if message.chat.type not in {"group", "supergroup"}:
        await message.answer("این بازی فقط تو گروه کار می‌کنه.")
        return
    try:
        from games.world_pulse import service as _pulse
        await _pulse.register_chat(message.chat.id, getattr(message.chat, "title", None))
    except Exception:
        pass
    try:
        rid = await R.open_room(game, message.chat.id, message.from_user.id, _name(message))
    except ValueError as e:
        await message.answer(str(e))
        return
    await message.answer(
        await lobby_text(game, rid),
        reply_markup=lobby_kb(game, rid),
    )


# ——— create commands ———
@router.message(Command("spyfall", "جاسوس_ناشناس"))
@router.message(F.text.in_({"جاسوس ناشناس", "بازی جاسوس", "spyfall"}))
async def create_spy(message: Message):
    await _create(message, "spyfall")


@router.message(Command("escape", "اتاق_فرار"))
@router.message(F.text.in_({"اتاق فرار", "فرار", "escape room", "escape"}))
async def create_escape(message: Message):
    await _create(message, "escape")


@router.message(Command("kingbetray", "پادشاه_خیانت"))
@router.message(F.text.in_({"پادشاه خیانت", "خیانت تاج", "kingbetray"}))
async def create_king(message: Message):
    await _create(message, "kingbetray")


@router.message(Command("island", "جزیره_گمشده"))
@router.message(F.text.in_({"جزیره گمشده", "جزیره", "island"}))
async def create_island(message: Message):
    await _create(message, "island")


@router.message(Command("detective", "کاراگاه", "کارآگاه"))
@router.message(F.text.in_({"کارآگاه خصوصی", "کاراگاه خصوصی", "پرونده", "detective"}))
async def create_detective(message: Message):
    await _create(message, "detective")


@router.message(Command("empirewar", "نبرد_امپراتوری"))
@router.message(F.text.in_({"نبرد امپراتوری‌ها", "نبرد امپراتوری ها", "نبرد امپراطوری", "empirewar"}))
async def create_empirewar(message: Message):
    await _create(message, "empirewar")


@router.message(Command("auction", "مزایده"))
@router.message(F.text.in_({"مزایده مرگبار", "مزایده", "auction"}))
async def create_auction(message: Message):
    await _create(message, "auction")


@router.message(Command("court", "دادگاه"))
@router.message(F.text.in_({"دادگاه سلطنتی", "دادگاه", "court"}))
async def create_court(message: Message):
    await _create(message, "court")


@router.message(Command("laststand", "بازمانده"))
@router.message(F.text.in_({"آخرین بازمانده", "اخرین بازمانده", "laststand"}))
async def create_laststand(message: Message):
    await _create(message, "laststand")


@router.message(Command("bomb", "بمب_ساعتی"))
@router.message(F.text.in_({"بمب ساعتی", "بمب", "bomb"}))
async def create_bomb(message: Message):
    await _create(message, "bomb")


@router.message(Command("treasure", "شکار_گنج"))
@router.message(F.text.in_({"شکار گنج", "گنج", "treasure"}))
async def create_treasure(message: Message):
    await _create(message, "treasure")


@router.message(Command("wordwar", "نبرد_کلمات"))
@router.message(F.text.in_({"نبرد کلمات", "کلمه بازی", "wordwar"}))
async def create_wordwar(message: Message):
    await _create(message, "wordwar")


@router.message(Command("minigames", "بازیها", "بازی‌ها"))
@router.message(F.text.in_({"بازی‌ها", "بازیها", "بازی های گروهی"}))
async def list_games(message: Message):
    await message.answer(
        "🎮 بازی‌های گروهی (فقط تو گروه):\n\n"
        "🕵️ جاسوس ناشناس\n"
        "🔐 اتاق فرار\n"
        "👑 پادشاه خیانت\n"
        "🏝️ جزیره گمشده\n"
        "🔎 کارآگاه خصوصی\n"
        "⚔️ نبرد امپراتوری‌ها\n"
        "💰 مزایده مرگبار\n"
        "⚖️ دادگاه سلطنتی\n"
        "🏁 آخرین بازمانده\n"
        "💣 بمب ساعتی\n"
        "🗺️ شکار گنج\n"
        "📝 نبرد کلمات\n\n"
        "سریع (خصوصی/گروه):\n"
        "تاس · شیر یا خط · دوئل (ریپلای)\n\n"
        "اسم بازی رو تو گروه بفرست."
    )


# ——— spyfall play commands ———
@router.message(Command("spy_vote", "رای_جاسوس"))
@router.message(F.text.in_({"رأی جاسوس", "رای جاسوس", "شروع رأی جاسوس"}))
async def spy_start_vote(message: Message):
    room = await R.get_open(message.chat.id, "spyfall")
    if not room or room["status"] != "playing":
        await message.answer("بازی جاسوس فعال نیست.")
        return
    await spyfall.start_vote(room["id"])
    pl = await R.players(room["id"])
    rows = [
        [InlineKeyboardButton(
            text=p["display_name"][:40],
            callback_data=f"mg:spyfall:vote:{room['id']}:{p['telegram_id']}",
        )]
        for p in pl
    ]
    rows.append([InlineKeyboardButton(
        text="✅ شمارش آرا",
        callback_data=f"mg:spyfall:tally:{room['id']}",
    )])
    await message.answer(
        "🗳️ به کسی که فکر می‌کنین جاسوسه رأی بدین:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.message(F.text.regexp(r"^(?:جواب فرار|جواب)\s+(.+)$"))
async def escape_answer(message: Message):
    room = await R.get_open(message.chat.id, "escape")
    if not room or room["status"] != "playing":
        return  # silent if not in game
    text = message.text or ""
    for pref in ("جواب فرار", "جواب"):
        if text.startswith(pref):
            text = text[len(pref):].strip()
            break
    try:
        res = await escape.answer(room["id"], message.from_user.id, text)
    except ValueError as e:
        await message.answer(str(e))
        return
    who = message.from_user.full_name or str(message.from_user.id)
    if res.get("reason") == "timeout":
        await message.answer(f"⏰ وقت تموم شد. معماهای حل‌شده: {res.get('solved', 0)}")
        return
    if res.get("ok") and res.get("finished"):
        await message.answer(f"🎉 {who} آخرین رمز رو زد! از اتاق فرار کردین. ({res.get('solved')} معما)")
        return
    if res.get("ok"):
        nxt = res.get("next") or {}
        await message.answer(
            f"✅ {who} درست گفت! ({res.get('solved')} حل‌شده)\n\n"
            f"معمای بعدی:\n{nxt.get('q', '—')}\n"
            f"جواب: جواب فرار …"
        )
        return
    await message.answer(
        f"❌ غلط بود ({res.get('wrong', 0)} غلط)\nراهنما: {res.get('hint') or '—'}"
    )


# ——— callbacks ———


@router.message(Command("dice", "تاس"))
@router.message(F.text.in_({"تاس", "تاس شانس", "dice"}))
async def cmd_dice(message: Message):
    r = await solo_games.dice(message.from_user.id)
    msg = f"🎲 {r['a']} + {r['b']} = {r['total']}"
    if r["reward"]:
        msg += f"\n🎁 +{r['reward']} سکه"
    else:
        msg += "\nاین دفعه چیزی نداد."
    await message.answer(msg)


@router.message(Command("coinflip", "شیرخط"))
@router.message(F.text.in_({"شیر", "خط", "شیر یا خط"}))
async def cmd_coin(message: Message):
    text = (message.text or "").strip()
    if text in {"شیر یا خط", "/coinflip", "/شیرخط"}:
        await message.answer("بگو: شیر   یا   خط")
        return
    pick = "شیر" if text == "شیر" else ("خط" if text == "خط" else "")
    if not pick:
        await message.answer("بگو: شیر یا خط")
        return
    try:
        r = await solo_games.coin_flip(message.from_user.id, pick)
        msg = f"🪙 اومد: {r['result_fa']}"
        if r["win"]:
            msg += f"\n✅ بردی +{r['reward']} سکه"
        else:
            msg += "\n❌ باختی"
        await message.answer(msg)
    except ValueError as e:
        await message.answer(str(e))



@router.message(Command("duel", "دوئل"))
@router.message(F.text.in_({"دوئل", "duel"}))
async def cmd_duel(message: Message):
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.answer("روی پیام حریفت ریپلای کن و بگو دوئل")
        return
    a = message.from_user.id
    b = message.reply_to_message.from_user.id
    if a == b:
        await message.answer("با خودت؟")
        return
    r = await solo_games.duel_power(a, b)
    wa = message.from_user.full_name
    wb = message.reply_to_message.from_user.full_name
    winner = wa if r["winner_id"] == a else wb
    await message.answer(
        f"⚔️ دوئل!\n"
        f"{wa}: قدرت {r['power_a']}\n"
        f"{wb}: قدرت {r['power_b']}\n"
        f"🏆 برنده: {winner}"
    )


@router.message(F.text.regexp(r"^(?:کلمه)\s+(.+)$"))
async def wordwar_word(message: Message):
    room = await R.get_open(message.chat.id, "wordwar")
    if not room or room["status"] != "playing":
        return
    word = (message.text or "").split(maxsplit=1)[-1].strip()
    try:
        res = await wordwar.play_word(room["id"], message.from_user.id, word)
        nxt = res.get("next")
        await message.answer(
            f"✅ «{res['last']}»\nنوبت بعدی: {nxt or '—'}"
        )
        try:
            await message.bot.send_message(
                message.chat.id,
                f"📝 {message.from_user.full_name}: {res['last']}",
            )
        except Exception:
            pass
    except ValueError as e:
        await message.answer(str(e))


@router.message(F.text.regexp(r"^(?:گنج)\s+(.+)$"))
async def treasure_guess_msg(message: Message):
    room = await R.get_open(message.chat.id, "treasure")
    if not room or room["status"] != "playing":
        return
    g = (message.text or "").split(maxsplit=1)[-1].strip()
    try:
        await treasure.guess(room["id"], message.from_user.id, g)
        await message.answer(f"حدس «{g}» ثبت شد.")
    except ValueError as e:
        await message.answer(str(e))

@router.callback_query(F.data.startswith("mg:"))
async def mg_cb(call: CallbackQuery):
    parts = (call.data or "").split(":")
    # mg:game:action:room_id[:extra]
    if len(parts) < 4:
        await call.answer("نامعتبر", show_alert=True)
        return
    game, action, rid_s = parts[1], parts[2], parts[3]
    try:
        room_id = int(rid_s)
    except ValueError:
        await call.answer("نامعتبر", show_alert=True)
        return
    room = await R.room(room_id)
    if not room:
        await call.answer("اتاق نیست", show_alert=True)
        return

    if action == "join":
        try:
            n = await R.join(room_id, call.from_user.id, (call.from_user.full_name or str(call.from_user.id))[:80])
            await call.answer(f"اومدی ({n})")
            await panel_update(call, await lobby_text(game, room_id), reply_markup=lobby_kb(game, room_id))
            try:
                await call.bot.send_message(
                    room["chat_id"],
                    f"✅ {call.from_user.full_name} به {LABELS.get(game, game)} پیوست.",
                )
            except Exception:
                pass
        except ValueError as e:
            await call.answer(str(e)[:180], show_alert=True)
        return

    if action == "status":
        await call.answer()
        if room["status"] == "lobby":
            await panel_update(call, await lobby_text(game, room_id), reply_markup=lobby_kb(game, room_id))
        else:
            st = R.decode(room["state"])
            await panel_update(call, f"وضعیت: {room['status']} · فاز: {st.get('phase', '—')}")
        return

    if action == "cancel":
        try:
            await R.cancel(room_id, call.from_user.id)
            await call.answer("لغو شد")
            await panel_update(call, f"{LABELS.get(game)} لغو شد.")
            try:
                await call.bot.send_message(room["chat_id"], f"❌ {LABELS.get(game)} توسط سازنده لغو شد.")
            except Exception:
                pass
        except ValueError as e:
            await call.answer(str(e)[:180], show_alert=True)
        return

    if action == "start":
        if int(room["creator_id"]) != int(call.from_user.id):
            await call.answer("فقط سازنده شروع کنه.", show_alert=True)
            return
        try:
            if game == "spyfall":
                st = await spyfall.start(room_id)
                await call.answer("شروع شد")
                # DM roles
                for pid, info in (st.get("assignments") or {}).items():
                    try:
                        if info.get("is_spy"):
                            msg = "🕵️ تو جاسوسی. مکان رو نمی‌دونی. خودت رو قاطی بقیه کن."
                        else:
                            msg = (
                                f"📍 مکان: {info.get('location')}\n"
                                f"🎭 نقش تو: {info.get('role')}\n"
                                f"جاسوس رو با سؤال پیدا کنین. لو نده مکان رو مستقیم."
                            )
                        await call.bot.send_message(int(pid), msg)
                    except Exception:
                        pass
                await panel_update(
                    call,
                    f"🕵️ بازی شروع شد!\nحرف بزنین و سؤال بپرسین.\nوقتی آماده‌این بزنین: رأی جاسوس",
                )
                try:
                    await call.bot.send_message(
                        room["chat_id"],
                        f"🕵️ جاسوس ناشناس شروع شد!\nنقش‌ها خصوصی ارسال شد.\n"
                        f"بحث کنین بعد بزنین: رأی جاسوس",
                    )
                except Exception:
                    pass
            elif game == "escape":
                st = await escape.start(room_id)
                await call.answer("شروع")
                pz = escape.current_puzzle(st)
                text = (
                    f"🔐 اتاق فرار شروع شد!\n"
                    f"⏱ حدود {int(st.get('limit_sec', 480)//60)} دقیقه\n\n"
                    f"معما ۱:\n{pz.get('q') if pz else '—'}\n\n"
                    f"جواب رو بنویسین: جواب فرار …"
                )
                await panel_update(call, text)
                try:
                    await call.bot.send_message(room["chat_id"], text)
                except Exception:
                    pass
            elif game == "kingbetray":
                st = await king.start(room_id)
                await call.answer("شروع")
                # DM traitor only
                try:
                    await call.bot.send_message(
                        int(st["traitor_id"]),
                        "🗡️ تو خائن مخفی هستی. سعی کن تاج بگیری یا امتیاز جمع کنی بدون لو رفتن.",
                    )
                except Exception:
                    pass
                text = (
                    f"👑 پادشاه خیانت شروع شد — دور ۱ از ۳\n"
                    f"الان نامزد معرفی کنین: نامزد پادشاه با ریپلای یا از دکمه\n"
                    f"بعد سازنده بزنه: رأی تاج"
                )
                pl = await R.players(room_id)
                rows = [
                    [InlineKeyboardButton(
                        text=f"نامزد: {p['display_name'][:30]}",
                        callback_data=f"mg:kingbetray:nom:{room_id}:{p['telegram_id']}",
                    )]
                    for p in pl
                ]
                rows.append([InlineKeyboardButton(
                    text="🗳️ شروع رأی تاج",
                    callback_data=f"mg:kingbetray:openvote:{room_id}",
                )])
                await panel_update(call, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
                try:
                    await call.bot.send_message(room["chat_id"], text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
                except Exception:
                    pass

            elif game == "island":
                st = await island.start(room_id)
                await call.answer("شروع")
                text = (
                    f"🏝️ جزیره — روز ۱ · غذا: {st['food']}\n"
                    f"هرکس یکی را انتخاب کند: جمع / استراحت / دزدی\n"
                    f"سازنده بعد از عمل‌ها بزند: پایان روز جزیره"
                )
                rows = [
                    [InlineKeyboardButton(text="🌴 جمع‌آوری", callback_data=f"mg:island:act:{room_id}:forage"),
                     InlineKeyboardButton(text="😴 استراحت", callback_data=f"mg:island:act:{room_id}:rest")],
                    [InlineKeyboardButton(text="🗡️ دزدی", callback_data=f"mg:island:act:{room_id}:steal")],
                    [InlineKeyboardButton(text="⏭️ پایان روز", callback_data=f"mg:island:day:{room_id}")],
                ]
                kb = InlineKeyboardMarkup(inline_keyboard=rows)
                await panel_update(call, text, reply_markup=kb)
                try: await call.bot.send_message(room["chat_id"], text, reply_markup=kb)
                except Exception: pass
            elif game == "detective":
                st = await detective.start(room_id)
                await call.answer("شروع")
                case = st["case"]
                text = (
                    f"🔎 پرونده: {case['title']}\n"
                    f"مظنون‌ها: {' · '.join(case['suspects'])}\n"
                    f"سرنخ‌ها را یکی‌یکی باز کنید."
                )
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📜 سرنخ بعدی", callback_data=f"mg:detective:clue:{room_id}")],
                    [InlineKeyboardButton(text="✅ اعلام قاتل", callback_data=f"mg:detective:reveal:{room_id}")],
                ])
                await panel_update(call, text, reply_markup=kb)
                try: await call.bot.send_message(room["chat_id"], text, reply_markup=kb)
                except Exception: pass
            elif game == "empirewar":
                st = await empirewar.start(room_id)
                await call.answer("شروع")
                pl = await R.players(room_id)
                names = {int(p["telegram_id"]): p["display_name"] for p in pl}
                red = "، ".join(names.get(i, str(i)) for i in st["red"])
                blue = "، ".join(names.get(i, str(i)) for i in st["blue"])
                text = (
                    f"⚔️ نبرد امپراتوری‌ها\n"
                    f"🔴 قرمز ({st['hp_red']} HP): {red}\n"
                    f"🔵 آبی ({st['hp_blue']} HP): {blue}\n"
                    f"هرکس: حمله یا دفاع"
                )
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="⚔️ حمله", callback_data=f"mg:empirewar:act:{room_id}:attack"),
                     InlineKeyboardButton(text="🛡️ دفاع", callback_data=f"mg:empirewar:act:{room_id}:defend")],
                    [InlineKeyboardButton(text="⏭️ پایان راند", callback_data=f"mg:empirewar:round:{room_id}")],
                ])
                await panel_update(call, text, reply_markup=kb)
                try: await call.bot.send_message(room["chat_id"], text, reply_markup=kb)
                except Exception: pass
            elif game == "auction":
                st = await auction.start(room_id)
                await call.answer("شروع")
                item = auction.current_item(st)
                text = (
                    f"💰 مزایده مرگبار\n"
                    f"آیتم: {item['name'] if item else '—'} (حداقل {item['min'] if item else '?'} )\n"
                    f"بودجه اولیه ۱۰۰\n"
                    f"پیشنهاد: پیشنهاد مزایده [مبلغ]"
                )
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="⏭️ بستن این آیتم", callback_data=f"mg:auction:close:{room_id}")],
                ])
                await panel_update(call, text, reply_markup=kb)
                try: await call.bot.send_message(room["chat_id"], text, reply_markup=kb)
                except Exception: pass
            elif game == "court":
                st = await court.start(room_id)
                await call.answer("شروع")
                pl = await R.players(room_id)
                names = {int(p["telegram_id"]): p["display_name"] for p in pl}
                acc = names.get(int(st["accused_id"]), st["accused_id"])
                text = (
                    f"⚖️ دادگاه سلطنتی\n"
                    f"متهم: {acc}\n"
                    f"اتهام: {st['charge']}\n"
                    f"بحث کنید بعد رأی: گناهکار / بیگناه"
                )
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="☠️ گناهکار", callback_data=f"mg:court:vote:{room_id}:guilty"),
                     InlineKeyboardButton(text="🕊️ بیگناه", callback_data=f"mg:court:vote:{room_id}:innocent")],
                    [InlineKeyboardButton(text="📜 حکم", callback_data=f"mg:court:verdict:{room_id}")],
                ])
                await panel_update(call, text, reply_markup=kb)
                try: await call.bot.send_message(room["chat_id"], text, reply_markup=kb)
                except Exception: pass
            elif game == "laststand":
                st = await laststand.start(room_id)
                await call.answer("شروع")
                pl = await R.players(room_id)
                rows = [[InlineKeyboardButton(
                    text=f"حذف {p['display_name'][:28]}",
                    callback_data=f"mg:laststand:vote:{room_id}:{p['telegram_id']}",
                )] for p in pl]
                rows.append([InlineKeyboardButton(text="⏭️ شمارش", callback_data=f"mg:laststand:resolve:{room_id}")])
                text = "🏁 آخرین بازمانده — به یکی برای حذف رأی دهید"
                kb = InlineKeyboardMarkup(inline_keyboard=rows)
                await panel_update(call, text, reply_markup=kb)
                try: await call.bot.send_message(room["chat_id"], text, reply_markup=kb)
                except Exception: pass


            elif game == "bomb":
                st = await bomb.start(room_id)
                await call.answer("شروع")
                pl = await R.players(room_id)
                names = {int(p["telegram_id"]): p["display_name"] for p in pl}
                holder = names.get(int(st["holder"]), st["holder"])
                rows = [[InlineKeyboardButton(
                    text=f"پاس به {p['display_name'][:24]}",
                    callback_data=f"mg:bomb:pass:{room_id}:{p['telegram_id']}",
                )] for p in pl if int(p["telegram_id"]) != int(st["holder"])]
                text = f"💣 بمب دست {holder} است! سریع پاس بده."
                kb = InlineKeyboardMarkup(inline_keyboard=rows)
                await panel_update(call, text, reply_markup=kb)
                try: await call.bot.send_message(room["chat_id"], text, reply_markup=kb)
                except Exception: pass
            elif game == "treasure":
                st = await treasure.start(room_id)
                await call.answer("شروع")
                text = "🗺️ شکار گنج شروع شد. سرنخ بگیر و حدس بزن: گنج [مکان]"
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📜 سرنخ", callback_data=f"mg:treasure:clue:{room_id}")],
                    [InlineKeyboardButton(text="🏁 اعلام نتیجه", callback_data=f"mg:treasure:reveal:{room_id}")],
                ])
                await panel_update(call, text, reply_markup=kb)
                try: await call.bot.send_message(room["chat_id"], text, reply_markup=kb)
                except Exception: pass
            elif game == "wordwar":
                st = await wordwar.start(room_id)
                await call.answer("شروع")
                cur = wordwar.current_player(st)
                text = (
                    f"📝 نبرد کلمات\n"
                    f"شروع با: {st['last_word']}\n"
                    f"نوبت: {cur}\n"
                    f"بگو: کلمه [واژه]"
                )
                await panel_update(call, text)
                try: await call.bot.send_message(room["chat_id"], text)
                except Exception: pass

            else:
                await call.answer("بازی؟", show_alert=True)
        except ValueError as e:
            await call.answer(str(e)[:180], show_alert=True)
        return

    # spyfall vote / tally
    if game == "spyfall" and action == "vote" and len(parts) >= 5:
        try:
            target = int(parts[4])
            await spyfall.cast_vote(room_id, call.from_user.id, target)
            await call.answer("رأی ثبت شد")
            try:
                await call.bot.send_message(
                    room["chat_id"],
                    f"🗳️ {call.from_user.full_name} رأی داد.",
                )
            except Exception:
                pass
        except ValueError as e:
            await call.answer(str(e)[:180], show_alert=True)
        return

    if game == "spyfall" and action == "tally":
        try:
            res = await spyfall.resolve_vote(room_id)
            spy_name = str(res["spy_id"])
            acc_name = str(res["accused"])
            pl = await R.players(room_id)
            names = {int(p["telegram_id"]): p["display_name"] for p in pl}
            spy_name = names.get(int(res["spy_id"]), spy_name)
            acc_name = names.get(int(res["accused"]), acc_name)
            if res["spy_caught"]:
                msg = f"🏁 جاسوس گیر افتاد: {spy_name}\nمکان واقعی: {res['location']}\nشهروندها بردن."
                for p in pl:
                    if int(p["telegram_id"]) != int(res["spy_id"]):
                        await _reward(int(p["telegram_id"]), 25)
            else:
                msg = (
                    f"🏁 اشتباه گرفتن ({acc_name}).\n"
                    f"جاسوس {spy_name} بود · مکان: {res['location']}\nجاسوس برد."
                )
                await _reward(int(res["spy_id"]), 40)
            await call.answer("تمام")
            await panel_update(call, msg)
            try:
                await call.bot.send_message(room["chat_id"], msg)
            except Exception:
                pass
        except ValueError as e:
            await call.answer(str(e)[:180], show_alert=True)
        return

    # kingbetray
    if game == "kingbetray" and action == "nom" and len(parts) >= 5:
        try:
            cand = int(parts[4])
            await king.nominate(room_id, call.from_user.id, cand)
            await call.answer("نامزد ثبت شد")
            try:
                await call.bot.send_message(
                    room["chat_id"],
                    f"👑 {call.from_user.full_name} یک نفر را نامزد کرد.",
                )
            except Exception:
                pass
        except ValueError as e:
            await call.answer(str(e)[:180], show_alert=True)
        return

    if game == "kingbetray" and action == "openvote":
        try:
            st = await king.open_vote(room_id)
            cands = st.get("candidates") or []
            pl = await R.players(room_id)
            names = {int(p["telegram_id"]): p["display_name"] for p in pl}
            rows = [
                [InlineKeyboardButton(
                    text=f"🗳️ {names.get(c, c)}",
                    callback_data=f"mg:kingbetray:votek:{room_id}:{c}",
                )]
                for c in cands
            ]
            rows.append([InlineKeyboardButton(
                text="✅ اعلام پادشاه",
                callback_data=f"mg:kingbetray:resolve:{room_id}",
            )])
            await call.answer("رأی‌گیری")
            text = "🗳️ به نامزد پادشاهی رأی بدین:"
            await panel_update(call, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
            try:
                await call.bot.send_message(
                    room["chat_id"], text,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
                )
            except Exception:
                pass
        except ValueError as e:
            await call.answer(str(e)[:180], show_alert=True)
        return

    if game == "kingbetray" and action == "votek" and len(parts) >= 5:
        try:
            await king.vote_king(room_id, call.from_user.id, int(parts[4]))
            await call.answer("رأی ثبت")
            try:
                await call.bot.send_message(room["chat_id"], f"🗳️ {call.from_user.full_name} رأی تاج داد.")
            except Exception:
                pass
        except ValueError as e:
            await call.answer(str(e)[:180], show_alert=True)
        return

    if game == "kingbetray" and action == "resolve":
        try:
            st = await king.resolve_round(room_id)
            pl = await R.players(room_id)
            names = {int(p["telegram_id"]): p["display_name"] for p in pl}
            king_id = st.get("king_id")
            msg = f"👑 پادشاه این دور: {names.get(int(king_id), king_id)}"
            if st.get("phase") == "ended":
                w = st.get("winner_id")
                traitor = st.get("traitor_id")
                msg += (
                    f"\n🏁 پایان بازی!\n"
                    f"برنده امتیاز: {names.get(int(w), w)}\n"
                    f"خائن مخفی: {names.get(int(traitor), traitor)}"
                )
            else:
                msg += f"\nدور بعد: {st.get('round')} — دوباره نامزد کنین."
                rows = [
                    [InlineKeyboardButton(
                        text=f"نامزد: {p['display_name'][:30]}",
                        callback_data=f"mg:kingbetray:nom:{room_id}:{p['telegram_id']}",
                    )]
                    for p in pl
                ]
                rows.append([InlineKeyboardButton(
                    text="🗳️ شروع رأی تاج",
                    callback_data=f"mg:kingbetray:openvote:{room_id}",
                )])
                await panel_update(call, msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
                try:
                    await call.bot.send_message(room["chat_id"], msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
                except Exception:
                    pass
                await call.answer("دور بعد")
                return
            await call.answer("پایان")
            await panel_update(call, msg)
            try:
                await call.bot.send_message(room["chat_id"], msg)
            except Exception:
                pass
        except ValueError as e:
            await call.answer(str(e)[:180], show_alert=True)
        return


    # —— island ——
    if game == "island" and action == "act" and len(parts) >= 5:
        try:
            await island.act(room_id, call.from_user.id, parts[4])
            await call.answer("ثبت شد")
            try:
                await call.bot.send_message(room["chat_id"], f"🏝️ {call.from_user.full_name} عملش را انتخاب کرد.")
            except Exception:
                pass
        except ValueError as e:
            await call.answer(str(e)[:180], show_alert=True)
        return
    if game == "island" and action == "day":
        try:
            st = await island.resolve_day(room_id)
            log = " | ".join((st.get("log") or [])[-3:])
            alive_n = sum(1 for a in (st.get("alive") or {}).values() if a)
            msg = f"🏝️ روز {st.get('day')} · غذا {st.get('food')} · زنده {alive_n}\n{log}"
            if st.get("phase") == "ended":
                msg += f"\n🏁 برنده: {st.get('winner_id')}"
            else:
                msg += "\nعمل بعدی را انتخاب کنید."
            await call.answer("روز تموم")
            rows = [
                [InlineKeyboardButton(text="🌴 جمع", callback_data=f"mg:island:act:{room_id}:forage"),
                 InlineKeyboardButton(text="😴 استراحت", callback_data=f"mg:island:act:{room_id}:rest"),
                 InlineKeyboardButton(text="🗡️ دزدی", callback_data=f"mg:island:act:{room_id}:steal")],
                [InlineKeyboardButton(text="⏭️ پایان روز", callback_data=f"mg:island:day:{room_id}")],
            ] if st.get("phase") != "ended" else []
            kb = InlineKeyboardMarkup(inline_keyboard=rows) if rows else None
            await panel_update(call, msg, reply_markup=kb)
            try: await call.bot.send_message(room["chat_id"], msg, reply_markup=kb)
            except Exception: pass
        except ValueError as e:
            await call.answer(str(e)[:180], show_alert=True)
        return

    # —— detective ——
    if game == "detective" and action == "clue":
        try:
            res = await detective.next_clue(room_id)
            if res.get("done"):
                await call.answer("سرنخ‌ها تمام")
                msg = "همه سرنخ‌ها اومد. حدس: متهم [اسم]\nبعد سازنده: اعلام قاتل"
            else:
                await call.answer(f"سرنخ {res['n']}")
                msg = f"📜 سرنخ {res['n']}/{res['total']}:\n{res['clue']}"
            try: await call.bot.send_message(room["chat_id"], msg)
            except Exception: pass
            await panel_update(call, msg)
        except ValueError as e:
            await call.answer(str(e)[:180], show_alert=True)
        return
    if game == "detective" and action == "reveal":
        try:
            st = await detective.reveal(room_id)
            msg = f"🏁 قاتل واقعی: {st.get('killer')}\nدرست‌حدس‌زن‌ها: {st.get('winners') or '—'}"
            await call.answer("پایان")
            await panel_update(call, msg)
            try: await call.bot.send_message(room["chat_id"], msg)
            except Exception: pass
        except ValueError as e:
            await call.answer(str(e)[:180], show_alert=True)
        return

    # —— empirewar ——
    if game == "empirewar" and action == "act" and len(parts) >= 5:
        try:
            await empirewar.act(room_id, call.from_user.id, parts[4])
            await call.answer("ثبت")
            try: await call.bot.send_message(room["chat_id"], f"⚔️ {call.from_user.full_name} آماده نبرد شد.")
            except Exception: pass
        except ValueError as e:
            await call.answer(str(e)[:180], show_alert=True)
        return
    if game == "empirewar" and action == "round":
        try:
            st = await empirewar.resolve_round(room_id)
            d = st.get("last_dmg") or {}
            msg = (
                f"راند {st.get('round')}\n"
                f"🔴 {st.get('hp_red')} (−{d.get('to_red',0)}) · 🔵 {st.get('hp_blue')} (−{d.get('to_blue',0)})"
            )
            if st.get("phase") == "ended":
                msg += f"\n🏁 برنده: {st.get('winner')}"
            await call.answer("راند")
            rows = [
                [InlineKeyboardButton(text="⚔️ حمله", callback_data=f"mg:empirewar:act:{room_id}:attack"),
                 InlineKeyboardButton(text="🛡️ دفاع", callback_data=f"mg:empirewar:act:{room_id}:defend")],
                [InlineKeyboardButton(text="⏭️ پایان راند", callback_data=f"mg:empirewar:round:{room_id}")],
            ] if st.get("phase") != "ended" else []
            kb = InlineKeyboardMarkup(inline_keyboard=rows) if rows else None
            await panel_update(call, msg, reply_markup=kb)
            try: await call.bot.send_message(room["chat_id"], msg, reply_markup=kb)
            except Exception: pass
        except ValueError as e:
            await call.answer(str(e)[:180], show_alert=True)
        return

    # —— auction ——
    if game == "auction" and action == "close":
        try:
            res = await auction.close_item(room_id)
            st = res["state"]
            if res.get("passed"):
                msg = "کسی پیشنهاد نداد؛ رفت آیتم بعدی."
            else:
                last = st.get("last") or {}
                msg = f"🔨 {last.get('item')} به {last.get('winner')} با {last.get('price')}"
            if st.get("phase") == "ended":
                msg += f"\n🏁 برنده مزایده: {st.get('winner_id')}"
            else:
                item = auction.current_item(st)
                if item:
                    msg += f"\nبعدی: {item['name']} (حداقل {item['min']})"
            await call.answer("بسته شد")
            kb = None
            if st.get("phase") != "ended":
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="⏭️ بستن این آیتم", callback_data=f"mg:auction:close:{room_id}")],
                ])
            await panel_update(call, msg, reply_markup=kb)
            try: await call.bot.send_message(room["chat_id"], msg, reply_markup=kb)
            except Exception: pass
        except ValueError as e:
            await call.answer(str(e)[:180], show_alert=True)
        return

    # —— court ——
    if game == "court" and action == "vote" and len(parts) >= 5:
        try:
            await court.vote(room_id, call.from_user.id, parts[4])
            await call.answer("رأی ثبت")
            try: await call.bot.send_message(room["chat_id"], f"⚖️ {call.from_user.full_name} رأی داد.")
            except Exception: pass
        except ValueError as e:
            await call.answer(str(e)[:180], show_alert=True)
        return
    if game == "court" and action == "verdict":
        try:
            st = await court.verdict(room_id)
            msg = (
                f"📜 حکم دادگاه: {'گناهکار' if st.get('decision')=='guilty' else 'بیگناه'}\n"
                f"واقعیت: {'واقعاً گناهکار بود' if st.get('guilty') else 'بیگناه بود'}\n"
                f"{'✅ دادگاه درست فهمید' if st.get('correct') else '❌ اشتباه شد'}"
            )
            await call.answer("حکم")
            await panel_update(call, msg)
            try: await call.bot.send_message(room["chat_id"], msg)
            except Exception: pass
        except ValueError as e:
            await call.answer(str(e)[:180], show_alert=True)
        return

    # —— laststand ——
    if game == "laststand" and action == "vote" and len(parts) >= 5:
        try:
            await laststand.vote(room_id, call.from_user.id, int(parts[4]))
            await call.answer("رأی")
            try: await call.bot.send_message(room["chat_id"], f"🏁 {call.from_user.full_name} رأی حذف داد.")
            except Exception: pass
        except ValueError as e:
            await call.answer(str(e)[:180], show_alert=True)
        return
    if game == "laststand" and action == "resolve":
        try:
            st = await laststand.resolve(room_id)
            msg = f"حذف شد: {st.get('last_out')}"
            if st.get("phase") == "ended":
                msg += f"\n🏆 بازمانده: {st.get('winner_id')}"
                if st.get("winner_id"):
                    await _reward(int(st["winner_id"]), 35)
            else:
                pl = await R.players(room_id)
                alive = st.get("alive") or {}
                rows = [[InlineKeyboardButton(
                    text=f"حذف {p['display_name'][:28]}",
                    callback_data=f"mg:laststand:vote:{room_id}:{p['telegram_id']}",
                )] for p in pl if alive.get(str(p['telegram_id']))]
                rows.append([InlineKeyboardButton(text="⏭️ شمارش", callback_data=f"mg:laststand:resolve:{room_id}")])
                kb = InlineKeyboardMarkup(inline_keyboard=rows)
                await panel_update(call, msg + f"\nدور {st.get('round')}", reply_markup=kb)
                try: await call.bot.send_message(room["chat_id"], msg, reply_markup=kb)
                except Exception: pass
                await call.answer("حذف")
                return
            await call.answer("پایان")
            await panel_update(call, msg)
            try: await call.bot.send_message(room["chat_id"], msg)
            except Exception: pass
        except ValueError as e:
            await call.answer(str(e)[:180], show_alert=True)
        return


    if game == "bomb" and action == "pass" and len(parts) >= 5:
        try:
            st = await bomb.pass_bomb(room_id, call.from_user.id, int(parts[4]))
            pl = await R.players(room_id)
            names = {int(p["telegram_id"]): p["display_name"] for p in pl}
            if st.get("exploded"):
                msg = f"💥 بمب ترکید روی {names.get(int(st.get('last_boom') or 0), st.get('last_boom'))}!"
                if st.get("phase") == "ended":
                    msg += f"\n🏆 بازمانده: {names.get(int(st.get('winner_id') or 0), st.get('winner_id'))}"
                    if st.get("winner_id"):
                        await _reward(int(st["winner_id"]), 35)
                else:
                    msg += f"\nبمب جدید دست {names.get(int(st['holder']), st['holder'])}"
            else:
                msg = f"💣 پاس داده شد → {names.get(int(st['holder']), st['holder'])}"
            await call.answer("پاس")
            alive = st.get("alive") or {}
            holder = int(st.get("holder") or 0)
            rows = [[InlineKeyboardButton(
                text=f"پاس به {p['display_name'][:24]}",
                callback_data=f"mg:bomb:pass:{room_id}:{p['telegram_id']}",
            )] for p in pl if alive.get(str(p["telegram_id"])) and int(p["telegram_id"]) != holder] if st.get("phase") != "ended" else []
            kb = InlineKeyboardMarkup(inline_keyboard=rows) if rows else None
            await panel_update(call, msg, reply_markup=kb)
            try: await call.bot.send_message(room["chat_id"], msg, reply_markup=kb)
            except Exception: pass
        except ValueError as e:
            await call.answer(str(e)[:180], show_alert=True)
        return

    if game == "treasure" and action == "clue":
        try:
            res = await treasure.show_clue(room_id)
            if res.get("done"):
                msg = "سرنخ دیگری نیست. حدس: گنج [مکان]"
            else:
                msg = f"📜 سرنخ {res['n']}/{res['total']}: {res['clue']}"
            await call.answer("سرنخ")
            await panel_update(call, msg)
            try: await call.bot.send_message(room["chat_id"], msg)
            except Exception: pass
        except ValueError as e:
            await call.answer(str(e)[:180], show_alert=True)
        return
    if game == "treasure" and action == "reveal":
        try:
            st = await treasure.reveal(room_id)
            msg = f"🗺️ گنج تو «{st.get('spot')}» بود.\nبرنده‌ها: {st.get('winners') or '—'}"
            await call.answer("پایان")
            await panel_update(call, msg)
            try: await call.bot.send_message(room["chat_id"], msg)
            except Exception: pass
        except ValueError as e:
            await call.answer(str(e)[:180], show_alert=True)
        return

    await call.answer("اقدام ناشناخته", show_alert=True)
