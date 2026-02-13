from datetime import date, timedelta
import unittest

import helpers


class HelpersBusinessRuleTests(unittest.TestCase):
    def test_calc_days(self):
        self.assertEqual(helpers.calc_days("2026-01-01", "2026-01-31"), 30)

    def test_interest_rate_calc_and_guards(self):
        self.assertAlmostEqual(
            helpers.calc_interest_rate_pa(1000, 100_000, 30),
            12.0,
            places=6,
        )
        self.assertEqual(helpers.calc_interest_rate_pa(1000, 100_000, 0), 0.0)
        self.assertEqual(helpers.calc_interest_rate_pa(1000, 0, 30), 0.0)
        self.assertEqual(helpers.calc_interest_rate_pa(1000, -1, 30), 0.0)

    def test_continuation_date_skips_weekends(self):
        # Monday end date -> should move back to the prior Wednesday.
        self.assertEqual(
            helpers.suggest_continuation_date("2026-01-12"),
            "2026-01-07",
        )

    def test_is_currently_active_boundaries(self):
        today = date.today()
        self.assertTrue(
            helpers.is_currently_active(
                today.isoformat(),
                (today + timedelta(days=1)).isoformat(),
            )
        )
        self.assertFalse(
            helpers.is_currently_active(
                (today - timedelta(days=1)).isoformat(),
                today.isoformat(),
            )
        )
        self.assertFalse(
            helpers.is_currently_active(
                (today + timedelta(days=1)).isoformat(),
                (today + timedelta(days=2)).isoformat(),
            )
        )


if __name__ == "__main__":
    unittest.main()
