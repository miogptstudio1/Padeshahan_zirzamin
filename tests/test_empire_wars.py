import unittest
from games.empire.engine import (war_fee, attack_power, defense_power, war_attacker_wins, WAR_RANDOM_MAX, war_result_message)

class EmpireWarTests(unittest.TestCase):
    def test_war_fee_is_ten_percent(self):
        self.assertEqual(war_fee(500), 50)
        self.assertEqual(war_fee(1), 1)
        with self.assertRaises(ValueError): war_fee(0)
    def test_attack_power_components(self):
        self.assertEqual(attack_power(1, 0, 0), 65)
        self.assertEqual(attack_power(2, 1, WAR_RANDOM_MAX), 130)
        with self.assertRaises(ValueError): attack_power(0, 0, 0)
    def test_defense_power_components(self):
        self.assertEqual(defense_power(1, 0), 65)
        self.assertEqual(defense_power(2, 2), 130)
        with self.assertRaises(ValueError): defense_power(1, 6)

    def test_auto_result_message_for_attacker_win(self):
        message = war_result_message({"id": 7, "won": True, "target_name": "بندر قدیمی", "attack_power": 120, "defense_power": 95})
        self.assertIn("پیروزی مهاجم", message)
        self.assertIn("بندر قدیمی", message)
        self.assertIn("120", message)

    def test_auto_result_message_for_defender_win(self):
        message = war_result_message({"id": 8, "won": False, "target_name": "ارگ سلطنتی", "attack_power": 80, "defense_power": 90})
        self.assertIn("مدافع پیروز", message)
        self.assertIn("ارگ سلطنتی", message)

    def test_auto_result_message_for_cancelled_war(self):
        message = war_result_message({"id": 9, "cancelled": True})
        self.assertIn("لغو شد", message)
        self.assertIn("9", message)

    def test_ties_favor_defender(self):
        self.assertFalse(war_attacker_wins(100, 100))
        self.assertTrue(war_attacker_wins(101, 100))
        with self.assertRaises(ValueError): war_attacker_wins(-1, 0)

if __name__ == '__main__': unittest.main()
