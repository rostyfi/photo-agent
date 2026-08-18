"""Natural-language date expression parsing for photo search filters.

Converts human-readable date expressions such as "last summer", "summer 2024",
"January 2024", "last week", or "2023" into an inclusive ``(start, end)``
ISO date range (``YYYY-MM-DD`` strings).

The parser is dependency-free and intentionally narrow: it covers the
common phrasings a user is likely to type in the chat. Anything it cannot
recognise returns ``(None, None)``, signalling the caller to skip the
date filter.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

# Meteorological season definitions: (start_month, end_month) inclusive.
_SEASONS: dict[str, tuple[int, int]] = {
    "winter": (12, 2),
    "spring": (3, 5),
    "summer": (6, 8),
    "fall": (9, 11),
    "autumn": (9, 11),
}

_MONTHS: dict[str, int] = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}


def _month_end(year: int, month: int) -> int:
    """Last calendar day of ``month`` in ``year``."""
    nxt = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return (nxt - timedelta(days=1)).day


def _season_range(year: int, season: str) -> tuple[date, date]:
    """Inclusive date range for ``season`` anchored in ``year``.

    Winter spans two calendar years: Dec of ``year`` through Feb of
    ``year+1``.
    """
    start_month, end_month = _SEASONS[season]
    if season == "winter":
        start = date(year, 12, 1)
        end = date(year + 1, 2, _month_end(year + 1, 2))
    else:
        start = date(year, start_month, 1)
        end = date(year, end_month, _month_end(year, end_month))
    return start, end


def _last_ended_season_year(today: date, season: str) -> int:
    """Anchor year of the most recent *fully ended* occurrence of ``season``.

    For non-winter seasons an occurrence lives entirely within calendar year
    ``Y`` and ends at the close of its end month. For winter, occurrence ``Y``
    spans Dec ``Y`` through Feb ``Y+1`` and only ends once March of ``Y+1``
    arrives.
    """
    _, end_month = _SEASONS[season]
    if season == "winter":
        # Winter Y ends in Feb Y+1; it has ended once March of Y+1 arrives.
        # In Jan/Feb we are still inside winter (Y-1 -> Y), so the most recent
        # ended winter started two years before today.
        return today.year - 1 if today.month >= 3 else today.year - 2
    # Non-winter: this year's occurrence has ended once we are past its end month.
    return today.year if today.month > end_month else today.year - 1


def _this_season_year(today: date, season: str) -> int:
    """Anchor year for ``this <season>`` (the current/upcoming occurrence)."""
    if season == "winter":
        # In Jan/Feb the ongoing winter started in Dec of the previous year.
        return today.year - 1 if today.month in (1, 2) else today.year
    return today.year


def _last_occurrence_month(today: date, month: int) -> tuple[int, int]:
    """Year/month of the most recent *completed* occurrence of ``month``."""
    if today.month > month or (today.month == month and today.day >= _month_end(today.year, month)):
        return today.year, month
    # Most recent occurrence was in the previous year if the month hasn't
    # been reached yet, OR if we're inside the month right now treat the
    # current month as the most recent started occurrence.
    if today.month == month:
        return today.year, month
    return today.year - 1, month


def _iso(d: date) -> str:
    return d.isoformat()


def parse_date_expression(
    text: str, today: date | None = None
) -> tuple[str | None, str | None]:
    """Parse a natural-language date expression into an inclusive ISO date range.

    Args:
        text: The date expression (e.g. "last summer", "January 2024", "2023").
        today: Reference date for relative expressions. Defaults to ``date.today()``.

    Returns:
        ``(start_iso, end_iso)`` as ``YYYY-MM-DD`` strings (inclusive), or
        ``(None, None)`` if the expression could not be parsed.
    """
    if not text:
        return None, None
    today = today or date.today()
    raw = text.strip().lower()
    # Collapse internal whitespace.
    expr = re.sub(r"\s+", " ", raw)
    if not expr:
        return None, None

    # --- Absolute ISO dates -------------------------------------------------
    # Full date: 2024-01-15
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", expr)
    if m:
        d = date(int(m[1]), int(m[2]), int(m[3]))
        return _iso(d), _iso(d)

    # Year-month: 2024-01
    m = re.fullmatch(r"(\d{4})-(\d{1,2})", expr)
    if m:
        year, month = int(m[1]), int(m[2])
        if 1 <= month <= 12:
            start = date(year, month, 1)
            end = date(year, month, _month_end(year, month))
            return _iso(start), _iso(end)

    # Bare year: 2023
    m = re.fullmatch(r"(\d{4})", expr)
    if m:
        year = int(m[1])
        return _iso(date(year, 1, 1)), _iso(date(year, 12, 31))

    # --- Relative keywords -------------------------------------------------
    if expr in ("today",):
        return _iso(today), _iso(today)
    if expr in ("yesterday",):
        return _iso(today - timedelta(days=1)), _iso(today - timedelta(days=1))

    if expr in ("this week",):
        monday = today - timedelta(days=today.weekday())
        sunday = monday + timedelta(days=6)
        return _iso(monday), _iso(sunday)
    if expr in ("last week",):
        monday = today - timedelta(days=today.weekday()) - timedelta(weeks=1)
        sunday = monday + timedelta(days=6)
        return _iso(monday), _iso(sunday)

    if expr in ("this month",):
        start = date(today.year, today.month, 1)
        end = date(today.year, today.month, _month_end(today.year, today.month))
        return _iso(start), _iso(end)
    if expr in ("last month",):
        if today.month == 1:
            y, mo = today.year - 1, 12
        else:
            y, mo = today.year, today.month - 1
        start = date(y, mo, 1)
        end = date(y, mo, _month_end(y, mo))
        return _iso(start), _iso(end)

    if expr in ("this year",):
        return _iso(date(today.year, 1, 1)), _iso(date(today.year, 12, 31))
    if expr in ("last year",):
        return _iso(date(today.year - 1, 1, 1)), _iso(date(today.year - 1, 12, 31))

    # --- Seasons -----------------------------------------------------------
    # "last summer" / "this summer" / "last winter" ...
    m = re.fullmatch(r"(last|this)\s+(winter|spring|summer|fall|autumn)", expr)
    if m:
        season = m.group(2)
        if m.group(1) == "this":
            start, end = _season_range(_this_season_year(today, season), season)
        else:  # last -> most recent fully ended occurrence
            start, end = _season_range(_last_ended_season_year(today, season), season)
        return _iso(start), _iso(end)

    # "<season> <year>" e.g. "summer 2024"
    m = re.fullmatch(r"(winter|spring|summer|fall|autumn)\s+(\d{4})", expr)
    if m:
        start, end = _season_range(int(m.group(2)), m.group(1))
        return _iso(start), _iso(end)

    # "last <season>" already handled above; "last <month>" below.

    # --- Months ------------------------------------------------------------
    # "<month> <year>" e.g. "January 2024", "jan 2024"
    m = re.fullmatch(r"([a-z]+)\s+(\d{4})", expr)
    if m and m.group(1) in _MONTHS:
        month = _MONTHS[m.group(1)]
        year = int(m.group(2))
        start = date(year, month, 1)
        end = date(year, month, _month_end(year, month))
        return _iso(start), _iso(end)

    # "last <month>" e.g. "last january"
    m = re.fullmatch(r"last\s+([a-z]+)", expr)
    if m and m.group(1) in _MONTHS:
        month = _MONTHS[m.group(1)]
        y, mo = _last_occurrence_month(today, month)
        start = date(y, mo, 1)
        end = date(y, mo, _month_end(y, mo))
        return _iso(start), _iso(end)

    # "this <month>" e.g. "this january" -> that month in the current year
    m = re.fullmatch(r"this\s+([a-z]+)", expr)
    if m and m.group(1) in _MONTHS:
        month = _MONTHS[m.group(1)]
        year = today.year
        start = date(year, month, 1)
        end = date(year, month, _month_end(year, month))
        return _iso(start), _iso(end)

    # Bare month name e.g. "january" -> most recent started occurrence
    if expr in _MONTHS:
        month = _MONTHS[expr]
        y, mo = _last_occurrence_month(today, month)
        start = date(y, mo, 1)
        end = date(y, mo, _month_end(y, mo))
        return _iso(start), _iso(end)

    return None, None
