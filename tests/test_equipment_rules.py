import unittest
from games.empire.equipment_rules import ITEMS, BOX_PRICE, item_stats, roll_box_reward

class FixedRng:
    def __init__(self, roll, choice=None): self.roll=roll; self._choice=choice
    def randint(self, _a, _b): return self.roll
    def choice(self, values): return self._choice if self._choice in values else values[0]

class EquipmentRulesTests(unittest.TestCase):
    def test_catalog_has_valid_prices_and_types(self):
        self.assertGreaterEqual(len(ITEMS), 20)
        firearms = [item for item in ITEMS.values() if item.get('category') == 'firearm']
        self.assertGreaterEqual(len(firearms), 10)
        for item in ITEMS.values():
            self.assertGreater(item['price'], 0)
            self.assertIn(item['kind'], {'weapon', 'armor'})

    def test_equipment_stats_combine_weapon_and_armor(self):
        stats = item_stats('iron_sword', 'chainmail')
        self.assertEqual(stats, {'attack': 12, 'defense': 12})

    def test_empty_loadout_has_no_bonus(self):
        self.assertEqual(item_stats(None, None), {'attack': 0, 'defense': 0})

    def test_box_coin_probabilities_boundaries(self):
        self.assertEqual(roll_box_reward(FixedRng(1))['amount'], 80)
        self.assertEqual(roll_box_reward(FixedRng(26))['amount'], 150)
        self.assertEqual(roll_box_reward(FixedRng(51))['amount'], 300)

    def test_box_can_reward_equipment(self):
        result = roll_box_reward(FixedRng(75, 'wood_sword'))
        self.assertEqual(result['type'], 'item')
        self.assertIn(result['item_key'], ITEMS)

    def test_box_price_is_in_game_currency(self):
        self.assertEqual(BOX_PRICE, 250)

if __name__ == '__main__': unittest.main()
