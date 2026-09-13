"""Tests for the intraday lookback clamp, which mirrors Yahoo Finance's real limits."""

from datetime import date, timedelta

from datasources.base import clamp_start_for_interval

TODAY = date.today()


def test_daily_is_never_clamped():
    """Daily data has no lookback limit, however old the start date is."""
    start = date(2000, 1, 1)
    end = TODAY
    clamped_start, was_clamped = clamp_start_for_interval("daily", start, end)
    assert clamped_start == start
    assert was_clamped is False


def test_5min_within_limit_is_not_clamped():
    """A start date within the last 60 days is left alone."""
    start = TODAY - timedelta(days=30)
    end = TODAY
    clamped_start, was_clamped = clamp_start_for_interval("5min", start, end)
    assert clamped_start == start
    assert was_clamped is False


def test_5min_beyond_limit_is_clamped_to_today_minus_60():
    """A start date older than 60 days is clamped to exactly 60 days before today."""
    start = TODAY - timedelta(days=200)
    end = TODAY - timedelta(days=100)
    clamped_start, was_clamped = clamp_start_for_interval("5min", start, end)
    assert clamped_start == TODAY - timedelta(days=60)
    assert was_clamped is True


def test_clamp_is_anchored_to_today_not_to_end():
    """A range that's entirely far in the past still gets clamped relative to *today*.

    This is the actual bug: Yahoo's limit is "the last 60 days from now", not
    "60 days before whatever end date the user picked" -- a request whose
    start/end are both 6+ months ago must still be clamped forward to
    today-60, not left untouched just because the *width* of the range is
    under 60 days.
    """
    start = TODAY - timedelta(days=200)
    end = TODAY - timedelta(days=170)  # only a 30-day-wide range, but old
    clamped_start, was_clamped = clamp_start_for_interval("5min", start, end)
    assert clamped_start == TODAY - timedelta(days=60)
    assert was_clamped is True


def test_1hour_uses_730_day_limit():
    """1-hour data follows Yahoo's longer (730-day) lookback window, not the 60-day one."""
    start = TODAY - timedelta(days=100)
    end = TODAY
    clamped_start, was_clamped = clamp_start_for_interval("1hour", start, end)
    assert clamped_start == start
    assert was_clamped is False

    old_start = TODAY - timedelta(days=800)
    clamped_start, was_clamped = clamp_start_for_interval("1hour", old_start, end)
    assert clamped_start == TODAY - timedelta(days=730)
    assert was_clamped is True
