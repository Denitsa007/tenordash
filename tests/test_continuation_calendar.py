import unittest
from datetime import date
from unittest.mock import patch

from app import build_continuation_calendar


class ContinuationCalendarTests(unittest.TestCase):
    """Tests for build_continuation_calendar() date logic."""

    @patch("app.date")
    def test_normal_month_structure(self, mock_date):
        """March 2026 starts on Sunday (weekday=6), 31 days."""
        mock_date.today.return_value = date(2026, 3, 15)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        result = build_continuation_calendar([])

        self.assertEqual(result["month_label"], "March 2026")
        # 6 leading blanks (Sun start) + 31 days = 37, padded to 42 (6 rows)
        self.assertEqual(len(result["cells"]) % 7, 0)
        # First real day should be day 1
        day_cells = [c for c in result["cells"] if c["day"] != ""]
        self.assertEqual(day_cells[0]["day"], 1)
        self.assertEqual(day_cells[-1]["day"], 31)

    @patch("app.date")
    def test_month_starting_monday(self, mock_date):
        """June 2026 starts on Monday (weekday=0), no leading blanks."""
        mock_date.today.return_value = date(2026, 6, 10)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        result = build_continuation_calendar([])

        # No leading blanks — first cell should be day 1
        self.assertEqual(result["cells"][0]["day"], 1)
        self.assertEqual(result["month_label"], "June 2026")

    @patch("app.date")
    def test_december_year_rollover(self, mock_date):
        """December correctly calculates 31 days (next_month = Jan of next year)."""
        mock_date.today.return_value = date(2026, 12, 5)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        result = build_continuation_calendar([])

        self.assertEqual(result["month_label"], "December 2026")
        day_cells = [c for c in result["cells"] if c["day"] != ""]
        self.assertEqual(len(day_cells), 31)

    @patch("app.date")
    def test_february_non_leap(self, mock_date):
        """February 2026 (non-leap) has 28 days."""
        mock_date.today.return_value = date(2026, 2, 14)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        result = build_continuation_calendar([])

        day_cells = [c for c in result["cells"] if c["day"] != ""]
        self.assertEqual(len(day_cells), 28)

    @patch("app.date")
    def test_february_leap_year(self, mock_date):
        """February 2028 (leap) has 29 days."""
        mock_date.today.return_value = date(2028, 2, 10)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        result = build_continuation_calendar([])

        day_cells = [c for c in result["cells"] if c["day"] != ""]
        self.assertEqual(len(day_cells), 29)

    @patch("app.date")
    def test_marked_dates_flagged(self, mock_date):
        """Continuation dates are marked in cells."""
        mock_date.today.return_value = date(2026, 3, 15)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        alerts = [
            {"continuation_date": "2026-03-10"},
            {"continuation_date": "2026-03-20"},
        ]
        result = build_continuation_calendar(alerts)

        marked = [c for c in result["cells"] if c["marked"]]
        self.assertEqual(len(marked), 2)
        self.assertEqual({c["day"] for c in marked}, {10, 20})

    @patch("app.date")
    def test_today_flagged(self, mock_date):
        """Today's date is flagged in cells."""
        mock_date.today.return_value = date(2026, 3, 15)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        result = build_continuation_calendar([])

        today_cells = [c for c in result["cells"] if c["today"]]
        self.assertEqual(len(today_cells), 1)
        self.assertEqual(today_cells[0]["day"], 15)

    @patch("app.date")
    def test_grid_always_complete_weeks(self, mock_date):
        """Cell count is always a multiple of 7."""
        for month in range(1, 13):
            mock_date.today.return_value = date(2026, month, 1)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            result = build_continuation_calendar([])
            self.assertEqual(
                len(result["cells"]) % 7, 0,
                f"Month {month} cells not a multiple of 7"
            )


if __name__ == "__main__":
    unittest.main()
