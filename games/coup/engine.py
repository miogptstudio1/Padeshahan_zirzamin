"""Pure rules helpers for the Persian Coup game."""
from __future__ import annotations
import random
import time

ROLES = ("duke", "assassin", "captain", "ambassador", "contessa")
ROLE_FA = {
    "duke": "دوک", "assassin": "آدم‌کش", "captain": "کاپیتان",
    "ambassador": "سفیر", "contessa": "کنتسا",
}
ROLE_ACTION = {"tax": "duke", "assassinate": "assassin", "steal": "captain", "exchange": "ambassador"}
ROLE_BLOCKS = {"duke": "foreign_aid", "captain": "steal", "ambassador": "steal", "contessa": "assassinate"}
ACTION_FA = {"income": "درآمد", "foreign_aid": "کمک خارجی", "tax": "مالیات", "steal": "سرقت", "exchange": "تبادل", "assassinate": "ترور", "coup": "کودتا"}


def new_game(player_ids: list[int], rng=None) -> dict:
    if len(player_ids) < 2 or len(player_ids) > 6 or len(set(player_ids)) != len(player_ids):
        raise ValueError("برای کودتا حداقل دو بازیکن متفاوت لازم است.")
    rng = rng or random
    deck = [role for role in ROLES for _ in range(3)]
    rng.shuffle(deck)
    players = {}
    for pid in player_ids:
        players[str(pid)] = {"cards": [deck.pop(), deck.pop()], "coins": 2, "alive": True}
    return {"players": players, "deck": deck, "turn_order": [str(x) for x in player_ids], "turn_index": 0,
            "status": "playing", "last_action": None, "pending_loss": None, "winner": None}


def living_ids(state: dict) -> list[str]:
    return [pid for pid in state["turn_order"] if state["players"][pid]["alive"]]


def current_player(state: dict) -> str | None:
    alive = living_ids(state)
    if len(alive) <= 1:
        return alive[0] if alive else None
    for offset in range(len(state["turn_order"])):
        idx = (state["turn_index"] + offset) % len(state["turn_order"])
        pid = state["turn_order"][idx]
        if state["players"][pid]["alive"]:
            return pid
    return None


def _finish_if_needed(state: dict):
    alive = living_ids(state)
    if len(alive) <= 1:
        state["status"] = "finished"
        state["winner"] = alive[0] if alive else None


def lose_influence(state: dict, pid: int | str, card_index: int) -> str:
    key = str(pid)
    player = state["players"].get(key)
    if not player or not player["alive"]:
        raise ValueError("بازیکن زنده نیست.")
    if card_index not in (0, 1) or card_index >= len(player["cards"]):
        raise ValueError("شمارهٔ کارت نامعتبر است.")
    lost = player["cards"].pop(card_index)
    if not player["cards"]:
        player["alive"] = False
    pending = state.get("pending_loss")
    if pending and str(pending.get("target")) == key:
        state["pending_loss"] = None
        continuation = pending.get('continuation')
        claim = state.get('pending_claim')
        if continuation == 'proceed' and claim:
            _apply_claim_effect(state, claim['actor'], claim['action'], claim.get('target'))
        elif continuation in {'cancel_action', 'cancel_block'}:
            if continuation == 'cancel_block' and claim and claim.get('action') == 'assassinate':
                state['players'][claim['actor']]['coins'] -= 3
            state['pending_claim'] = None
            if state.get('status') == 'playing': _next_turn(state)
        elif state.get("status") == "playing":
            _next_turn(state)
    _finish_if_needed(state)
    return lost


def _next_turn(state: dict):
    """Advance to the next living player so eliminated seats are skipped cleanly."""
    order = state.get("turn_order") or []
    n = len(order)
    if n == 0:
        _finish_if_needed(state)
        return
    start = int(state.get("turn_index") or 0) % n
    for offset in range(1, n + 1):
        idx = (start + offset) % n
        pid = order[idx]
        pl = state["players"].get(pid) or {}
        if pl.get("alive"):
            state["turn_index"] = idx
            break
    else:
        state["turn_index"] = start
    _finish_if_needed(state)


def apply_action(state: dict, actor_id: int | str, action: str, target_id: int | str | None = None, *, exchange_cards: list[str] | None = None) -> dict:
    """Apply a direct action. Challenge/block resolution is intentionally separate/future work."""
    actor = str(actor_id)
    if state.get("status") != "playing": raise ValueError("بازی تمام شده است.")
    if state.get("pending_loss") is not None: raise ValueError("ابتدا بازیکن هدف باید کارت نفوذ خود را انتخاب کند.")
    if (state.get("last_action") or {}).get("needs_exchange_choice"): raise ValueError("ابتدا باید کارت‌های تبادل را انتخاب کنی.")
    if current_player(state) != actor: raise ValueError("الان نوبت تو نیست.")
    player = state["players"][actor]
    if not player["alive"]: raise ValueError("بازیکن حذف‌شده نمی‌تواند بازی کند.")
    if player["coins"] >= 10 and action != "coup": raise ValueError("با ۱۰ سکه یا بیشتر، باید کودتا کنی.")
    target = str(target_id) if target_id is not None else None
    if action in {"steal", "assassinate", "coup"}:
        if not target or target not in state["players"] or not state["players"][target]["alive"] or target == actor:
            raise ValueError("هدف باید یک حریف زنده باشد.")
    if action == "income":
        player["coins"] += 1
    elif action == "foreign_aid":
        player["coins"] += 2
    elif action == "tax":
        player["coins"] += 3
    elif action == "steal":
        victim = state["players"][target]
        amount = min(2, victim["coins"])
        victim["coins"] -= amount; player["coins"] += amount
    elif action == "exchange":
        pool = list(state.get("deck", []))
        random.shuffle(pool)
        offered = list(player["cards"]) + pool[:2]
        state["deck"] = pool[2:]
        state["last_action"] = {"actor": actor, "action": action, "offered": offered, "needs_exchange_choice": True}
        return state["last_action"]
    elif action == "assassinate":
        if player["coins"] < 3: raise ValueError("ترور ۳ سکه هزینه دارد.")
        player["coins"] -= 3
        state["pending_loss"] = {"actor": actor, "target": target, "action": action}
    elif action == "coup":
        if player["coins"] < 7: raise ValueError("کودتا حداقل ۷ سکه هزینه دارد.")
        player["coins"] -= 7
        state["pending_loss"] = {"actor": actor, "target": target, "action": action}
    else:
        raise ValueError("اقدام نامعتبر است.")
    state["last_action"] = {"actor": actor, "action": action, "target": target}
    if not state.get("pending_loss"):
        _next_turn(state)
    return state["last_action"]


def _apply_claim_effect(state: dict, actor: str, action: str, target: str | None):
    """Apply an action after its claim/block window has been resolved."""
    player = state['players'][actor]
    if action == 'foreign_aid':
        player['coins'] += 2
    elif action == 'tax':
        player['coins'] += 3
    elif action == 'steal':
        victim = state['players'][target]
        amount = min(2, victim['coins'])
        victim['coins'] -= amount
        player['coins'] += amount
    elif action == 'exchange':
        pool = list(state.get('deck', [])); random.shuffle(pool)
        offered = list(player['cards']) + pool[:2]
        state['deck'] = pool[2:]
        state['last_action'] = {'actor': actor, 'action': action, 'offered': offered, 'needs_exchange_choice': True}
        state['pending_claim'] = None
        return state['last_action']
    elif action == 'assassinate':
        player['coins'] -= 3
        state['pending_loss'] = {'actor': actor, 'target': target, 'action': action}
        state['pending_claim'] = None
        state['last_action'] = {'actor': actor, 'action': action, 'target': target}
        return state['last_action']
    state['last_action'] = {'actor': actor, 'action': action, 'target': target}
    state['pending_claim'] = None
    _next_turn(state)
    return state['last_action']


def declare_action(state: dict, actor_id: int | str, action: str, target_id: int | str | None = None) -> dict:
    """Declare actions that can be challenged or blocked; other actions use the base engine."""
    actor = str(actor_id)
    if state.get('pending_claim') or state.get('pending_loss') is not None:
        raise ValueError('ابتدا اقدام یا کارت ازدست‌رفتهٔ فعلی را تمام کن.')
    if action not in {'foreign_aid', 'tax', 'steal', 'exchange', 'assassinate'}:
        return apply_action(state, actor_id, action, target_id)
    if state.get('status') != 'playing' or current_player(state) != actor:
        raise ValueError('الان نوبت تو نیست یا بازی تمام شده است.')
    player = state['players'][actor]
    if player['coins'] >= 10:
        raise ValueError('با ۱۰ سکه یا بیشتر، باید کودتا کنی.')
    target = str(target_id) if target_id is not None else None
    if action in {'steal', 'assassinate'} and (not target or target not in state['players'] or not state['players'][target]['alive'] or target == actor):
        raise ValueError('هدف باید یک حریف زنده باشد.')
    if action == 'assassinate' and player['coins'] < 3:
        raise ValueError('ترور ۳ سکه هزینه دارد.')
    claim = ROLE_ACTION.get(action)
    state['pending_claim'] = {'actor': actor, 'action': action, 'target': target, 'phase': 'challenge' if claim else 'block', 'claim_role': claim, 'blocker': None, 'block_role': None, 'deadline': time.time() + 20}
    state['last_action'] = {'actor': actor, 'action': action, 'target': target, 'claim_role': claim, 'pending': True}
    return state['last_action']


def accept_action(state: dict, actor_id: int | str) -> dict:
    claim = state.get('pending_claim')
    if not claim:
        raise ValueError('اقدامی برای تأیید وجود ندارد.')
    if claim.get('phase') == 'block_challenge':
        if str(actor_id) != claim.get('blocker'):
            raise ValueError('فقط مسدودکننده می‌تواند مسدودسازی را نهایی کند.')
        return resolve_block(state)
    if claim.get('phase') not in {'challenge', 'block'}:
        raise ValueError('اقدامی برای تأیید وجود ندارد.')
    if str(actor_id) != claim['actor']:
        raise ValueError('فقط بازیکنی که اقدام را اعلام کرده می‌تواند آن را تأیید کند.')
    return _apply_claim_effect(state, claim['actor'], claim['action'], claim.get('target'))


def block_action(state: dict, blocker_id: int | str, role: str) -> dict:
    claim = state.get('pending_claim')
    blocker = str(blocker_id)
    if not claim or claim.get('phase') not in {'challenge', 'block'}:
        raise ValueError('اکنون اقدامی برای مسدودسازی وجود ندارد.')
    if blocker == claim['actor'] or blocker not in living_ids(state):
        raise ValueError('این بازیکن نمی‌تواند اقدام خودش را مسدود کند.')
    allowed = {'foreign_aid': {'duke'}, 'steal': {'captain', 'ambassador'}, 'assassinate': {'contessa'}}
    if role not in allowed.get(claim['action'], set()):
        raise ValueError('این نقش نمی‌تواند این اقدام را مسدود کند.')
    claim.update({'phase': 'block_challenge', 'blocker': blocker, 'block_role': role, 'deadline': time.time() + 20})
    state['pending_claim'] = claim
    state['last_action'] = {'actor': claim['actor'], 'action': claim['action'], 'target': claim.get('target'), 'blocked_by': blocker, 'block_role': role, 'pending': True}
    return state['last_action']


def challenge_action(state: dict, challenger_id: int | str) -> dict:
    claim = state.get('pending_claim')
    challenger = str(challenger_id)
    if not claim or claim.get('phase') not in {'challenge', 'block_challenge'}:
        raise ValueError('اکنون ادعایی برای چالش وجود ندارد.')
    claimant = claim['blocker'] if claim['phase'] == 'block_challenge' else claim['actor']
    role = claim['block_role'] if claim['phase'] == 'block_challenge' else claim['claim_role']
    if challenger == claimant or challenger not in living_ids(state):
        raise ValueError('نمی‌توانی ادعای خودت را چالش کنی.')
    has_role = role in state['players'][claimant]['cards']
    if has_role:
        # The claimed card is revealed, returned to the deck, and replaced.
        state['players'][claimant]['cards'].remove(role)
        state['deck'].append(role)
        if state['deck']:
            replacement = state['deck'].pop(random.randrange(len(state['deck'])))
            state['players'][claimant]['cards'].append(replacement)
        else:
            state['players'][claimant]['cards'].append(role)
        loser = challenger
        continuation = 'cancel_block' if claim['phase'] == 'block_challenge' else 'proceed'
    else:
        loser = claimant
        continuation = 'proceed' if claim['phase'] == 'block_challenge' else 'cancel_action'
    state['pending_loss'] = {'actor': claimant, 'target': loser, 'action': 'challenge', 'continuation': continuation}
    claim['phase'] = 'waiting_loss'
    claim['continuation'] = continuation
    claim['claimant'] = claimant
    claim['challenger'] = challenger
    state['pending_claim'] = claim
    state['last_action'] = {'actor': claimant, 'action': 'challenge', 'target': loser, 'continuation': continuation}
    return state['last_action']


def resolve_block(state: dict) -> dict:
    claim = state.get('pending_claim')
    if not claim or claim.get('phase') != 'block_challenge':
        raise ValueError('مسدودسازی فعالی وجود ندارد.')
    if claim['action'] == 'assassinate':
        # The assassination fee is paid even when Contessa blocks it.
        state['players'][claim['actor']]['coins'] -= 3
    state['last_action'] = {'actor': claim['actor'], 'action': claim['action'], 'blocked': True, 'blocker': claim['blocker']}
    state['pending_claim'] = None
    _next_turn(state)
    return state['last_action']
