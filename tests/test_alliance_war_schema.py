import unittest
from pydantic import ValidationError
from api.schemas import DeclareAllianceWarRequest

class AllianceWarSchemaTests(unittest.TestCase):
    def test_valid_target(self):
        body = DeclareAllianceWarRequest(target_city_key='capital')
        self.assertEqual(body.target_city_key, 'capital')

    def test_rejects_invalid_target(self):
        for value in ('', 'Capital City', 'capital;DROP', 'x' * 41):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    DeclareAllianceWarRequest(target_city_key=value)

if __name__ == '__main__':
    unittest.main()
