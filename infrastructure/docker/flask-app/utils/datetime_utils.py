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


def parse_newsletter_date(date_str: str, default_tz=None) -> datetime.date:
    """
    Parse YYYY-MM-DD string to date, defaulting to today if invalid or None.

    This is a simple utility to replace repeated date parsing patterns
    throughout the publisher routes.

    Args:
        date_str: Date string in format YYYY-MM-DD (or None)
        default_tz: Timezone for "today" default (defaults to TIMEZONE_EASTERN)

    Returns:
        date: Parsed date or today's date in the specified timezone
    """
    if default_tz is None:
        default_tz = TIMEZONE_EASTERN

    if date_str:
        try:
            return datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            pass
    return datetime.now(default_tz).date()


# ------------------------------------------------------------------
# TIMEZONE CONVERSION - Single Responsibility
# ------------------------------------------------------------------

def convert_utc_to_eastern(utc_datetime):
    """
    Convert UTC datetime to Eastern timezone-aware datetime.

    Handles multiple input types:
    - datetime objects (naive or aware)
    - ISO 8601 strings from DynamoDB
    - date objects (converted to midnight)
    - date-only strings ('YYYY-MM-DD')

    Args:
        utc_datetime: UTC datetime, ISO 8601 string, date object, or date string

    Returns:
        datetime: Eastern timezone-aware datetime for display, or None if parsing fails
    """
    from datetime import date

    if utc_datetime is None:
        return None

    # Handle ISO 8601 string inputs (from DynamoDB)
    if isinstance(utc_datetime, str):
        try:
            # Parse ISO 8601 format (with timezone)
            utc_datetime = datetime.fromisoformat(utc_datetime.replace('Z', '+00:00'))
        except ValueError:
            # Try date-only format
            try:
                utc_datetime = datetime.strptime(utc_datetime, '%Y-%m-%d')
            except ValueError:
                return None

    # Handle date objects (convert to midnight datetime)
    if isinstance(utc_datetime, date) and not isinstance(utc_datetime, datetime):
        utc_datetime = datetime.combine(utc_datetime, datetime.min.time())

    # Ensure timezone-aware
    if utc_datetime.tzinfo is None:
        utc_aware = utc_datetime.replace(tzinfo=TIMEZONE_UTC)
    else:
        utc_aware = utc_datetime

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
