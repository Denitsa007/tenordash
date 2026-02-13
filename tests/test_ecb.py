from datetime import date
import json
import unittest
from unittest import mock

import ecb
from config import BASE_CURRENCY


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class EcbResilienceTests(unittest.TestCase):
    def setUp(self):
        ecb.clear_cache()

    def tearDown(self):
        ecb.clear_cache()

    def test_cache_hit_skips_network(self):
        today = date.today().isoformat()
        ecb._cache["date"] = today
        ecb._cache["rates"] = {BASE_CURRENCY: 1.0, "EUR": 1.05}

        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("should not call network")):
            rates, rate_date = ecb.get_fx_rates([{"code": "CHF", "ecb_available": 1}])

        self.assertEqual(rates["EUR"], 1.05)
        self.assertEqual(rate_date, today)

    def test_timeout_falls_back_to_base_rate_when_no_cache(self):
        with mock.patch("urllib.request.urlopen", side_effect=TimeoutError("timeout")):
            rates, rate_date = ecb.get_fx_rates(
                [{"code": "CHF", "ecb_available": 1}, {"code": "USD", "ecb_available": 1}]
            )

        self.assertEqual(rates, {BASE_CURRENCY: 1.0})
        self.assertIsNone(rate_date)

    def test_malformed_payload_falls_back_to_cached_rates(self):
        ecb._cache["date"] = "2026-01-01"
        ecb._cache["rates"] = {BASE_CURRENCY: 1.0, "EUR": 1.02}
        bad_payload = json.dumps({"unexpected": "shape"}).encode("utf-8")

        with mock.patch("urllib.request.urlopen", return_value=_FakeResponse(bad_payload)):
            rates, rate_date = ecb.get_fx_rates(
                [{"code": "CHF", "ecb_available": 1}, {"code": "USD", "ecb_available": 1}]
            )

        self.assertEqual(rates["EUR"], 1.02)
        self.assertEqual(rate_date, "2026-01-01")

    def test_validate_currency_network_error(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("network down")):
            ok, msg = ecb.validate_currency_ecb("ABC")

        self.assertFalse(ok)
        self.assertIn("Could not verify ABC", msg)


if __name__ == "__main__":
    unittest.main()
