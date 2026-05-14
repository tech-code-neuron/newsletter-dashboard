"""
Timezone Utilities - Standardize timezone handling across all Lambdas
======================================================================
Purpose: Convert UTC to Eastern Time (ET) for circuit breaker and business logic
Pattern: Single Source of Truth for timezone conversions

Why ET instead of UTC:
- Business day aligns with company operations (9 AM - 5 PM ET)
- Circuit breaker "new day" should match business calendar
- Press releases typically sent during ET business hours

Usage:
    from shared.timezone_utils import get_today_et

    today_iso = get_today_et()  # Returns '2026-03-15' in ET

SOLID Principles:
- Single Responsibility: Only handles timezone conversions
- No external dependencies: Uses stdlib zoneinfo (Python 3.9+)

Last Updated: 2026-03-15
"""

from datetime import datetime
from zoneinfo import ZoneInfo


def get_today_et() -> str:
    """
    Get current date in Eastern Time (ET) as ISO string.

    Handles daylight saving time automatically:
    - EST (UTC-5): November - March
    - EDT (UTC-4): March - November

    Returns:
        str: Today's date in YYYY-MM-DD format (ET timezone)

    Examples:
        >>> # If current time is 2026-03-15 01:00 UTC
        >>> get_today_et()
        '2026-03-14'  # 8:00 PM ET on March 14 (still previous day)

        >>> # If current time is 2026-03-15 05:00 UTC
        >>> get_today_et()
        '2026-03-15'  # 12:00 AM ET on March 15 (new day)
    """
    eastern = ZoneInfo('America/New_York')
    now_et = datetime.now(eastern)
    return now_et.strftime('%Y-%m-%d')


def get_current_time_et() -> datetime:
    """
    Get current datetime in Eastern Time (ET).

    Returns:
        datetime: Current datetime with ET timezone

    Examples:
        >>> now = get_current_time_et()
        >>> now.strftime('%Y-%m-%d %H:%M:%S %Z')
        '2026-03-15 14:30:00 EDT'
    """
    eastern = ZoneInfo('America/New_York')
    return datetime.now(eastern)


def utc_to_et(utc_datetime: datetime) -> datetime:
    """
    Convert UTC datetime to Eastern Time.

    Args:
        utc_datetime: Datetime in UTC timezone

    Returns:
        datetime: Converted to ET timezone

    Examples:
        >>> from datetime import timezone
        >>> utc_time = datetime(2026, 3, 15, 5, 0, 0, tzinfo=timezone.utc)
        >>> et_time = utc_to_et(utc_time)
        >>> et_time.strftime('%Y-%m-%d %H:%M:%S %Z')
        '2026-03-15 00:00:00 EST'  # Midnight ET
    """
    eastern = ZoneInfo('America/New_York')
    return utc_datetime.astimezone(eastern)
