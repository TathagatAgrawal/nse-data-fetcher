"""Tests for the upfront date-range validation shown before a download starts."""

from datetime import date, timedelta

from downloader import validate_date_range

TODAY = date.today()


def test_valid_daily_range_passes():
    """A sensible daily range with no interval-window concerns passes with no error."""
    assert validate_date_range("daily", TODAY - timedelta(days=365), TODAY) is None


def test_reversed_range_is_rejected():
    """A 'From' date after the 'To' date is rejected regardless of interval."""
    error = validate_date_range("daily", TODAY, TODAY - timedelta(days=1))
    assert error is not None
    assert "before" in error


def test_future_end_date_is_rejected():
    """A 'To' date in the future is rejected regardless of interval."""
    error = validate_date_range("daily", TODAY - timedelta(days=10), TODAY + timedelta(days=1))
    assert error is not None
    assert "future" in error


def test_old_daily_range_is_never_rejected_for_being_old():
    """Daily has no lookback limit, so an old range is fine even for a very old start."""
    assert validate_date_range("daily", date(2000, 1, 1), date(2010, 1, 1)) is None


def test_5min_range_entirely_outside_lookback_window_is_rejected():
    """A 5-minute range that's entirely more than 60 days old is rejected with a clear reason."""
    start = TODAY - timedelta(days=200)
    end = TODAY - timedelta(days=170)
    error = validate_date_range("5min", start, end)
    assert error is not None
    assert "60 days" in error


def test_5min_range_within_lookback_window_passes():
    """A recent 5-minute range within the last 60 days passes."""
    start = TODAY - timedelta(days=30)
    end = TODAY - timedelta(days=1)
    assert validate_date_range("5min", start, end) is None


def test_5min_range_partially_overlapping_lookback_window_passes():
    """A range that starts before the window but still overlaps it is fine -- it'll just be narrowed."""
    start = TODAY - timedelta(days=100)
    end = TODAY - timedelta(days=1)
    assert validate_date_range("5min", start, end) is None


def test_1hour_uses_the_wider_730_day_window():
    """1-hour data's longer lookback window means a range 5min would reject can still pass."""
    start = TODAY - timedelta(days=200)
    end = TODAY - timedelta(days=170)
    assert validate_date_range("1hour", start, end) is None
