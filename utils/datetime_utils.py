"""
Date and time utility functions.
Centralizes timezone handling and datetime parsing (Single Responsibility).
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from config.newsletter_config import (
    TIME_BEFORE_MARKET_OPEN_HOUR,
    TIME_BEFORE_MARKET_OPEN_MINUTE,
    TIME_AFTER_MARKET_CLOSE_HOUR,
    TIME_AFTER_MARKET_CLOSE_MINUTE,
    MORNING_NEWSLETTER_START_HOUR,
    MORNING_NEWSLETTER_START_MINUTE,
    MORNING_NEWSLETTER_LOOKBACK_DAYS,
    BREAKING_NEWSLETTER_START_HOUR,
    BREAKING_NEWSLETTER_START_MINUTE,
    BREAKING_NEWSLETTER_END_HOUR,
    BREAKING_NEWSLETTER_END_MINUTE,
    NEWSLETTER_TYPE_MORNING
)


# ------------------------------------------------------------------
# TIMEZONE CONSTANTS
# ------------------------------------------------------------------

TIMEZONE_UTC = ZoneInfo('UTC')
TIMEZONE_EASTERN = ZoneInfo('America/New_York')


# ------------------------------------------------------------------
# DATETIME PARSING - Single Responsibility
# ------------------------------------------------------------------

def parse_press_release_datetime(date_str, time_option):
    """
    Parse date and time option into UTC datetime for database storage.

    Args:
        date_str: Date string in format YYYY-MM-DD
        time_option: 'before' (pre-market) or 'after' (after-market)

    Returns:
        datetime: Naive UTC datetime for database storage

    Raises:
        ValueError: If date_str format is invalid
    """
    # Parse the date
    date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()

    # Set time based on option (in Eastern Time)
    if time_option == 'before':
        hour = TIME_BEFORE_MARKET_OPEN_HOUR
        minute = TIME_BEFORE_MARKET_OPEN_MINUTE
    else:
        hour = TIME_AFTER_MARKET_CLOSE_HOUR
        minute = TIME_AFTER_MARKET_CLOSE_MINUTE

    # Create datetime in Eastern Time
    published_date_et = datetime(
        date_obj.year, date_obj.month, date_obj.day,
        hour, minute, 0,
        tzinfo=TIMEZONE_EASTERN
    )

    # Convert to UTC for database storage (naive)
    return published_date_et.astimezone(TIMEZONE_UTC).replace(tzinfo=None)


def parse_edit_form_datetime(date_str, time_str):
    """
    Parse date and time strings from edit form into UTC datetime.

    Args:
        date_str: Date string in format YYYY-MM-DD
        time_str: Time string in format HH:MM (24-hour)

    Returns:
        datetime: Naive UTC datetime for database storage

    Raises:
        ValueError: If date_str or time_str format is invalid
    """
    date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
    time_obj = datetime.strptime(time_str, '%H:%M').time()

    # Combine and set as Eastern Time
    published_date_et = datetime.combine(date_obj, time_obj, tzinfo=TIMEZONE_EASTERN)

    # Convert to UTC for database storage (naive)
    return published_date_et.astimezone(TIMEZONE_UTC).replace(tzinfo=None)


# ------------------------------------------------------------------
# TIMEZONE CONVERSION - Single Responsibility
# ------------------------------------------------------------------

def convert_utc_to_eastern(utc_datetime):
    """
    Convert naive UTC datetime to Eastern timezone-aware datetime.

    Args:
        utc_datetime: Naive UTC datetime from database

    Returns:
        datetime: Eastern timezone-aware datetime for display
    """
    if utc_datetime is None:
        return None

    # Add UTC timezone, then convert to Eastern
    utc_aware = utc_datetime.replace(tzinfo=TIMEZONE_UTC)
    return utc_aware.astimezone(TIMEZONE_EASTERN)


def convert_eastern_to_utc(eastern_datetime):
    """
    Convert Eastern timezone-aware datetime to naive UTC datetime.

    Args:
        eastern_datetime: Eastern timezone-aware datetime

    Returns:
        datetime: Naive UTC datetime for database storage
    """
    if eastern_datetime is None:
        return None

    return eastern_datetime.astimezone(TIMEZONE_UTC).replace(tzinfo=None)


# ------------------------------------------------------------------
# NEWSLETTER DATE RANGE CALCULATION
# ------------------------------------------------------------------

def calculate_newsletter_date_range(newsletter_type, date):
    """
    Calculate start and end dates for newsletter based on type.

    Args:
        newsletter_type: 'morning' or 'breaking'
        date: Eastern timezone-aware datetime (base date)

    Returns:
        tuple: (start_date_utc, end_date_utc) as naive UTC datetimes

    Raises:
        ValueError: If newsletter_type is invalid
    """
    if newsletter_type == NEWSLETTER_TYPE_MORNING:
        # Morning: yesterday 12:01 AM - today 11:59:59 PM (ET)
        end_date = date.replace(
            hour=MORNING_NEWSLETTER_START_HOUR,
            minute=MORNING_NEWSLETTER_START_MINUTE,
            second=0,
            microsecond=0
        )
        start_date = (end_date - timedelta(days=MORNING_NEWSLETTER_LOOKBACK_DAYS)).replace(
            hour=MORNING_NEWSLETTER_START_HOUR,
            minute=MORNING_NEWSLETTER_START_MINUTE
        )
        end_date = end_date - timedelta(microseconds=1)  # Just before midnight

    else:  # breaking
        # Breaking: today 12:01 AM - today 8:00 AM (ET)
        start_date = date.replace(
            hour=BREAKING_NEWSLETTER_START_HOUR,
            minute=BREAKING_NEWSLETTER_START_MINUTE,
            second=0,
            microsecond=0
        )
        end_date = date.replace(
            hour=BREAKING_NEWSLETTER_END_HOUR,
            minute=BREAKING_NEWSLETTER_END_MINUTE,
            second=0,
            microsecond=0
        )

    # Convert to UTC (naive)
    start_date_utc = start_date.astimezone(TIMEZONE_UTC).replace(tzinfo=None)
    end_date_utc = end_date.astimezone(TIMEZONE_UTC).replace(tzinfo=None)

    return start_date_utc, end_date_utc
