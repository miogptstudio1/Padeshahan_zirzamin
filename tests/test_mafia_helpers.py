import unittest
import sys
import types

# These helper tests do not need a live PostgreSQL driver or database.
if 'asyncpg' not in sys.modules:
    fake_asyncpg = types.ModuleType('asyncpg')
    fake_asyncpg.Pool = type('Pool', (), {})
    sys.modules['asyncpg'] = fake_asyncpg

from games.mafia.service import decode_state, winner, choose_mafia_target, eligible_vote_target_ids

class MafiaHelperTests(unittest.TestCase):
    def test_decode_json_string(self):
        self.assertEqual(decode_state('{"round": 2}'), {"round": 2})

    def test_decode_none(self):
        self.assertEqual(decode_state(None), {})

    def test_town_wins_when_no_mafia(self):
        players = [{'role': 'citizen', 'alive': True}, {'role': 'doctor', 'alive': True}]
        self.assertEqual(winner(players), 'town')

    def test_mafia_wins_at_parity(self):
        players = [{'role': 'mafia', 'alive': True}, {'role': 'citizen', 'alive': True}]
        self.assertEqual(winner(players), 'mafia')

    def test_game_continues_when_town_has_majority(self):
        players = [{'role': 'mafia', 'alive': True}, {'role': 'citizen', 'alive': True}, {'role': 'doctor', 'alive': True}]
        self.assertIsNone(winner(players))

    def test_dead_mafia_does_not_count_for_parity(self):
        players = [{'role': 'mafia', 'alive': False}, {'role': 'citizen', 'alive': True}, {'role': 'doctor', 'alive': True}]
        self.assertEqual(winner(players), 'town')

    def test_mafia_target_uses_unique_plurality(self):
        actions = {'1': {'role': 'mafia', 'target': 10}, '2': {'role': 'mafia', 'target': 10}, '3': {'role': 'mafia', 'target': 11}}
        self.assertEqual(choose_mafia_target(actions), 10)

    def test_mafia_target_tie_means_no_kill(self):
        actions = {'1': {'role': 'mafia', 'target': 10}, '2': {'role': 'mafia', 'target': 11}}
        self.assertIsNone(choose_mafia_target(actions))

    def test_challenge_requires_cover_for_vote_eligibility(self):
        state = {'challenges': [{'target_id': 10}, {'target_id': 11}], 'covers': {'11': 7}}
        self.assertEqual(eligible_vote_target_ids(state, [10, 11, 12]), {11})

    def test_no_challenges_all_living_players_are_eligible(self):
        self.assertEqual(eligible_vote_target_ids({}, [10, 11]), {10, 11})

if __name__ == '__main__':
    unittest.main()
