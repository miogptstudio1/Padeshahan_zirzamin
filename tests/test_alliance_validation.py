import unittest
from games.empire.alliance_rules import clean_name, clean_tag

class AllianceValidationTests(unittest.TestCase):
    def test_name_is_trimmed_and_whitespace_normalized(self):
        self.assertEqual(clean_name('  نگهبانان   شب  '), 'نگهبانان شب')

    def test_name_bounds(self):
        for name in ('ab', 'x' * 33):
            with self.assertRaises(ValueError):
                clean_name(name)

    def test_tag_is_normalized(self):
        self.assertEqual(clean_tag('n1ght'), 'N1GHT')

    def test_tag_rejects_non_ascii_or_wrong_length(self):
        for tag in ('A', 'TOOLONG', 'تاج', 'A-1'):
            with self.assertRaises(ValueError):
                clean_tag(tag)

if __name__ == '__main__':
    unittest.main()
