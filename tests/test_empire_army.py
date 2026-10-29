import unittest
from games.empire.engine import (
    SOLDIER_RECRUIT_COST, MAX_SOLDIERS, recruit_cost, army_power_bonus,
)


class EmpireArmyTests(unittest.TestCase):
    def test_recruit_cost(self):
        self.assertEqual(recruit_cost(1), SOLDIER_RECRUIT_COST)
        self.assertEqual(recruit_cost(10), 200)
        self.assertEqual(recruit_cost(100), 2000)

    def test_recruit_count_bounds(self):
        for count in (0, -1, 101):
            with self.subTest(count=count), self.assertRaises(ValueError):
                recruit_cost(count)

    def test_army_power_bonus(self):
        self.assertEqual(army_power_bonus(0), 0)
        self.assertEqual(army_power_bonus(10), 30)
        self.assertEqual(army_power_bonus(MAX_SOLDIERS), MAX_SOLDIERS * 3)

    def test_army_power_rejects_invalid_counts(self):
        for count in (-1, MAX_SOLDIERS + 1):
            with self.subTest(count=count), self.assertRaises(ValueError):
                army_power_bonus(count)


if __name__ == '__main__':
    unittest.main()
