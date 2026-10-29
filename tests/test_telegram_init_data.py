import hashlib
import hmac
import json
import unittest
from urllib.parse import urlencode, parse_qsl
from api.auth import validate_init_data, TelegramAuthError

TOKEN = "123456:TEST_TOKEN"


def signed_data(user, auth_date=1_800_000_000, token=TOKEN):
    fields = {"auth_date": str(auth_date), "query_id": "AAE-test", "user": json.dumps(user, separators=(",", ":"))}
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


class TelegramInitDataTests(unittest.TestCase):
    def test_valid_signature(self):
        data = signed_data({"id": 42, "first_name": "Test"})
        self.assertEqual(validate_init_data(data, TOKEN, now=1_800_000_010)["user"]["id"], 42)

    def test_tampered_user_rejected(self):
        fields = dict(parse_qsl(signed_data({"id": 42})))
        fields["user"] = json.dumps({"id": 43}, separators=(",", ":"))
        data = urlencode(fields)
        with self.assertRaises(TelegramAuthError):
            validate_init_data(data, TOKEN, now=1_800_000_010)

    def test_expired_data_rejected(self):
        data = signed_data({"id": 42}, auth_date=1_700_000_000)
        with self.assertRaises(TelegramAuthError):
            validate_init_data(data, TOKEN, now=1_800_000_000, max_age_seconds=60)

    def test_wrong_token_rejected(self):
        data = signed_data({"id": 42})
        with self.assertRaises(TelegramAuthError):
            validate_init_data(data, "wrong", now=1_800_000_010)

    def test_missing_data_rejected(self):
        with self.assertRaises(TelegramAuthError):
            validate_init_data("", TOKEN, now=1_800_000_010)

    def test_missing_user_rejected(self):
        data = signed_data({"id": 42})
        fields = dict(parse_qsl(data))
        fields.pop("user")
        data = urlencode(fields)
        with self.assertRaises(TelegramAuthError):
            validate_init_data(data, TOKEN, now=1_800_000_010)


if __name__ == "__main__":
    unittest.main()
