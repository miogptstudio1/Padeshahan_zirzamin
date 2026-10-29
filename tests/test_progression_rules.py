import unittest
from games.empire.progression_rules import MISSIONS, ACHIEVEMENTS, mission_progress, level_for_xp, period_key

class ProgressionRulesTests(unittest.TestCase):
    def test_level_progression(self):
        self.assertEqual(level_for_xp(0), 1)
        self.assertEqual(level_for_xp(99), 1)
        self.assertEqual(level_for_xp(100), 2)
        self.assertEqual(level_for_xp(999), 10)

    def test_mission_progress_is_capped(self):
        mission = MISSIONS['daily'][0]
        result = mission_progress(mission, {'soldiers': 900})
        self.assertTrue(result['complete'])
        self.assertEqual(result['progress'], mission['target'])

    def test_incomplete_mission(self):
        mission = MISSIONS['weekly'][0]
        result = mission_progress(mission, {'games_played': 2})
        self.assertFalse(result['complete'])
        self.assertEqual(result['progress'], 2)

    def test_mission_and_achievement_keys_unique(self):
        for kind in MISSIONS:
            keys = [x['key'] for x in MISSIONS[kind]]
            self.assertEqual(len(keys), len(set(keys)))
        keys = [x['key'] for x in ACHIEVEMENTS]
        self.assertEqual(len(keys), len(set(keys)))

    def test_period_key_rejects_invalid_kind(self):
        with self.assertRaises(ValueError):
            period_key('monthly', '2026-10-29')

if __name__ == '__main__': unittest.main()
