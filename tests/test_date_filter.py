"""Tests for the natural-language date filter parser."""

from datetime import date

from src.date_filter import parse_date_expression

# Fixed reference date so assertions are deterministic. Mid-August 2026,
# i.e. still inside meteorological summer.
TODAY = date(2026, 8, 18)


class TestParseDateExpression:
    def test_empty_and_unparseable(self):
        assert parse_date_expression("", TODAY) == (None, None)
        assert parse_date_expression("   ", TODAY) == (None, None)
        assert parse_date_expression("banana", TODAY) == (None, None)

    def test_bare_year(self):
        assert parse_date_expression("2023", TODAY) == ("2023-01-01", "2023-12-31")

    def test_iso_date(self):
        assert parse_date_expression("2024-01-15", TODAY) == ("2024-01-15", "2024-01-15")

    def test_year_month(self):
        assert parse_date_expression("2024-02", TODAY) == ("2024-02-01", "2024-02-29")

    def test_month_year(self):
        assert parse_date_expression("January 2024", TODAY) == ("2024-01-01", "2024-01-31")
        assert parse_date_expression("feb 2023", TODAY) == ("2023-02-01", "2023-02-28")
        assert parse_date_expression("sept 2024", TODAY) == ("2024-09-01", "2024-09-30")

    def test_bare_month_most_recent(self):
        # August -> current year (we're in it)
        assert parse_date_expression("august", TODAY) == ("2026-08-01", "2026-08-31")
        # January already passed this year
        assert parse_date_expression("january", TODAY) == ("2026-01-01", "2026-01-31")
        # December hasn't happened yet -> previous year
        assert parse_date_expression("december", TODAY) == ("2025-12-01", "2025-12-31")

    def test_last_month(self):
        assert parse_date_expression("last month", TODAY) == ("2026-07-01", "2026-07-31")

    def test_last_month_january_rollover(self):
        assert parse_date_expression("last month", date(2026, 1, 10)) == ("2025-12-01", "2025-12-31")

    def test_this_month(self):
        assert parse_date_expression("this month", TODAY) == ("2026-08-01", "2026-08-31")

    def test_this_year_and_last_year(self):
        assert parse_date_expression("this year", TODAY) == ("2026-01-01", "2026-12-31")
        assert parse_date_expression("last year", TODAY) == ("2025-01-01", "2025-12-31")

    def test_today_and_yesterday(self):
        assert parse_date_expression("today", TODAY) == ("2026-08-18", "2026-08-18")
        assert parse_date_expression("yesterday", TODAY) == ("2026-08-17", "2026-08-17")

    def test_last_week(self):
        # 2026-08-18 is a Tuesday (weekday=1). Last week Monday -> Sunday.
        assert parse_date_expression("last week", TODAY) == ("2026-08-10", "2026-08-16")

    def test_this_summer(self):
        assert parse_date_expression("this summer", TODAY) == ("2026-06-01", "2026-08-31")

    def test_last_summer(self):
        # Currently inside summer 2026 -> last summer is 2025.
        assert parse_date_expression("last summer", TODAY) == ("2025-06-01", "2025-08-31")

    def test_last_summer_in_winter(self):
        # In February, last summer already completed -> same-year summer is past,
        # so "last summer" is the previous year's summer? No: completed => current
        # year's summer (2026) if it ended. Feb 2026: summer 2025 ended -> last = 2025.
        assert parse_date_expression("last summer", date(2026, 2, 10)) == ("2025-06-01", "2025-08-31")
        # In October, summer 2026 completed -> last summer is 2026.
        assert parse_date_expression("last summer", date(2026, 10, 5)) == ("2026-06-01", "2026-08-31")

    def test_season_year(self):
        assert parse_date_expression("summer 2024", TODAY) == ("2024-06-01", "2024-08-31")
        assert parse_date_expression("winter 2024", TODAY) == ("2024-12-01", "2025-02-28")
        assert parse_date_expression("spring 2024", TODAY) == ("2024-03-01", "2024-05-31")
        assert parse_date_expression("autumn 2024", TODAY) == ("2024-09-01", "2024-11-30")
        assert parse_date_expression("fall 2024", TODAY) == ("2024-09-01", "2024-11-30")

    def test_last_winter_in_summer(self):
        # August 2026 -> most recent ended winter is Dec 2025 - Feb 2026.
        assert parse_date_expression("last winter", TODAY) == ("2025-12-01", "2026-02-28")

    def test_last_winter_in_january(self):
        # January 2026: ongoing winter is 2025-2026, so "last winter" is the
        # previous one (2024-2025).
        assert parse_date_expression("last winter", date(2026, 1, 10)) == ("2024-12-01", "2025-02-28")

    def test_last_winter_in_march(self):
        # March 2026: winter 2025-2026 just ended.
        assert parse_date_expression("last winter", date(2026, 3, 5)) == ("2025-12-01", "2026-02-28")

    def test_this_winter_in_january_is_ongoing(self):
        # January 2026: "this winter" = the ongoing Dec 2025 - Feb 2026.
        assert parse_date_expression("this winter", date(2026, 1, 10)) == ("2025-12-01", "2026-02-28")

    def test_this_winter_in_summer_is_upcoming(self):
        assert parse_date_expression("this winter", TODAY) == ("2026-12-01", "2027-02-28")

    def test_last_month_name(self):
        assert parse_date_expression("last january", TODAY) == ("2026-01-01", "2026-01-31")
        assert parse_date_expression("last december", TODAY) == ("2025-12-01", "2025-12-31")

    def test_case_and_whitespace_insensitive(self):
        assert parse_date_expression("  Last   Summer  ", TODAY) == ("2025-06-01", "2025-08-31")
        assert parse_date_expression("SUMMER 2024", TODAY) == ("2024-06-01", "2024-08-31")

    def test_defaults_to_today(self):
        # No today supplied; must still produce a valid 4-digit-year range.
        start, end = parse_date_expression("2023")
        assert start == "2023-01-01" and end == "2023-12-31"
