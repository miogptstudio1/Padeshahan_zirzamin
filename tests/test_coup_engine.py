import unittest
from games.coup.engine import new_game, current_player, apply_action, declare_action, challenge_action, block_action, accept_action, lose_influence, living_ids

class CoupEngineTests(unittest.TestCase):
    def game(self):
        return new_game([11, 22, 33])

    def test_game_starts_with_two_cards_and_two_coins(self):
        state = self.game()
        for player in state['players'].values():
            self.assertEqual(len(player['cards']), 2)
            self.assertEqual(player['coins'], 2)

    def test_income_adds_one_coin_and_advances_turn(self):
        state = self.game(); actor = current_player(state)
        before = state['players'][actor]['coins']
        apply_action(state, actor, 'income')
        self.assertEqual(state['players'][actor]['coins'], before + 1)
        self.assertNotEqual(current_player(state), actor)

    def test_coup_requires_seven_coins(self):
        state = self.game(); actor = current_player(state)
        with self.assertRaises(ValueError): apply_action(state, actor, 'coup', 22)

    def test_assassination_requires_three_coins_and_target_loses_by_choice(self):
        state = self.game(); actor = current_player(state)
        state['players'][actor]['coins'] = 3
        action = apply_action(state, actor, 'assassinate', 22)
        self.assertEqual(state['players'][actor]['coins'], 0)
        self.assertEqual(state['pending_loss']['target'], '22')
        self.assertEqual(len(state['players']['22']['cards']), 2)
        lose_influence(state, 22, 0)
        self.assertEqual(len(state['players']['22']['cards']), 1)
        self.assertIsNone(state['pending_loss'])

    def test_ten_coins_force_coup(self):
        state = self.game(); actor = current_player(state)
        target = next(pid for pid in state['players'] if pid != actor)
        state['players'][actor]['coins'] = 10
        with self.assertRaises(ValueError): apply_action(state, actor, 'income')
        apply_action(state, actor, 'coup', target)
        self.assertEqual(state['players'][actor]['coins'], 3)
        self.assertIsNotNone(state['pending_loss'])

    def test_exchange_requires_choice_before_next_action(self):
        state = self.game(); actor = current_player(state)
        result = apply_action(state, actor, 'exchange')
        self.assertTrue(result['needs_exchange_choice'])
        with self.assertRaises(ValueError): apply_action(state, actor, 'income')


    def test_tax_claim_waits_for_acceptance(self):
        state = self.game(); actor = current_player(state)
        before = state['players'][actor]['coins']
        declare_action(state, actor, 'tax')
        self.assertEqual(state['players'][actor]['coins'], before)
        self.assertEqual(state['pending_claim']['phase'], 'challenge')
        accept_action(state, actor)
        self.assertEqual(state['players'][actor]['coins'], before + 3)

    def test_challenge_false_claim_cancels_action_after_card_loss(self):
        state = self.game(); actor = current_player(state)
        state['players'][actor]['cards'] = ['captain', 'ambassador']
        declare_action(state, actor, 'tax')
        challenger = next(pid for pid in living_ids(state) if pid != actor)
        challenge_action(state, challenger)
        self.assertEqual(state['pending_loss']['target'], actor)
        lose_influence(state, actor, 0)
        self.assertIsNone(state['pending_claim'])
        self.assertEqual(state['players'][actor]['coins'], 2)

    def test_foreign_aid_can_be_blocked_by_duke_claim(self):
        state = self.game(); actor = current_player(state)
        declare_action(state, actor, 'foreign_aid')
        blocker = next(pid for pid in living_ids(state) if pid != actor)
        block_action(state, blocker, 'duke')
        accept_action(state, blocker)
        self.assertEqual(state['players'][actor]['coins'], 2)
        self.assertIsNone(state['pending_claim'])

    def test_challenged_valid_role_makes_challenger_lose_influence(self):
        state = self.game(); actor = current_player(state)
        state['players'][actor]['cards'] = ['duke', state['players'][actor]['cards'][1]]
        declare_action(state, actor, 'tax')
        challenger = next(pid for pid in living_ids(state) if pid != actor)
        challenge_action(state, challenger)
        self.assertEqual(state['pending_loss']['target'], challenger)
        lose_influence(state, challenger, 0)
        self.assertEqual(state['players'][actor]['coins'], 5)
        self.assertIsNone(state['pending_claim'])


    def test_false_block_claim_is_challenged_and_steal_proceeds(self):
        state = self.game(); actor = current_player(state)
        victim = next(pid for pid in living_ids(state) if pid != actor)
        state['players'][actor]['cards'] = ['duke', 'contessa']
        state['players'][actor]['coins'] = 0
        state['players'][victim]['coins'] = 2
        declare_action(state, actor, 'steal', victim)
        blocker = next(pid for pid in living_ids(state) if pid not in {actor, victim})
        state['players'][blocker]['cards'] = ['duke', 'contessa']
        block_action(state, blocker, 'ambassador')
        challenge_action(state, actor)
        self.assertEqual(state['pending_loss']['target'], blocker)
        lose_influence(state, blocker, 0)
        self.assertEqual(state['players'][actor]['coins'], 2)
        self.assertEqual(state['players'][victim]['coins'], 0)

    def test_valid_block_stops_foreign_aid_after_challenge(self):
        state = self.game(); actor = current_player(state)
        blocker = next(pid for pid in living_ids(state) if pid != actor)
        state['players'][blocker]['cards'][0] = 'duke'
        declare_action(state, actor, 'foreign_aid')
        block_action(state, blocker, 'duke')
        challenger = next(pid for pid in living_ids(state) if pid not in {actor, blocker})
        challenge_action(state, challenger)
        self.assertEqual(state['pending_loss']['target'], challenger)
        lose_influence(state, challenger, 0)
        self.assertEqual(state['players'][actor]['coins'], 2)
        self.assertIsNone(state['pending_claim'])


    def test_claim_has_challenge_deadline(self):
        state = self.game(); actor = current_player(state)
        declare_action(state, actor, 'tax')
        self.assertGreater(state['pending_claim']['deadline'], 0)

    def test_blocking_resets_deadline_and_enters_block_challenge(self):
        state = self.game(); actor = current_player(state)
        declare_action(state, actor, 'foreign_aid')
        blocker = next(pid for pid in living_ids(state) if pid != actor)
        before = state['pending_claim']['deadline']
        block_action(state, blocker, 'duke')
        self.assertEqual(state['pending_claim']['phase'], 'block_challenge')
        self.assertGreaterEqual(state['pending_claim']['deadline'], before)

    def test_foreign_aid_cannot_be_challenged_as_role_claim(self):
        state = self.game(); actor = current_player(state)
        declare_action(state, actor, 'foreign_aid')
        challenger = next(pid for pid in living_ids(state) if pid != actor)
        with self.assertRaises(ValueError):
            challenge_action(state, challenger)


    def test_blocked_assassination_still_costs_three_coins(self):
        state = self.game(); actor = current_player(state)
        target = next(pid for pid in living_ids(state) if pid != actor)
        state['players'][actor]['coins'] = 4
        declare_action(state, actor, 'assassinate', target)
        blocker = next(pid for pid in living_ids(state) if pid not in {actor, target})
        state['players'][blocker]['cards'] = ['contessa', state['players'][blocker]['cards'][1]]
        block_action(state, blocker, 'contessa')
        accept_action(state, blocker)
        self.assertEqual(state['players'][actor]['coins'], 1)
        self.assertIsNone(state['pending_loss'])

    def test_challenged_valid_contessa_block_still_charges_assassination_fee(self):
        state = self.game(); actor = current_player(state)
        target = next(pid for pid in living_ids(state) if pid != actor)
        state['players'][actor]['coins'] = 4
        declare_action(state, actor, 'assassinate', target)
        blocker = next(pid for pid in living_ids(state) if pid not in {actor, target})
        state['players'][blocker]['cards'] = ['contessa', state['players'][blocker]['cards'][1]]
        block_action(state, blocker, 'contessa')
        challenge_action(state, actor)
        self.assertEqual(state['pending_loss']['target'], actor)
        lose_influence(state, actor, 0)
        self.assertEqual(state['players'][actor]['coins'], 1)
        self.assertIsNone(state['pending_claim'])

    def test_elimination_when_last_influence_is_lost(self):
        state = self.game()
        state['players']['22']['cards'] = ['duke']
        state['pending_loss'] = {'actor': '11', 'target': '22', 'action': 'coup'}
        lose_influence(state, 22, 0)
        self.assertFalse(state['players']['22']['alive'])
        self.assertNotIn('22', living_ids(state))

if __name__ == '__main__': unittest.main()
