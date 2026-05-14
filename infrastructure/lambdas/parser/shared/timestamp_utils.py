"""
Timestamp Utilities - Single Source of Truth
=============================================
Purpose: Canonical functions for extracting and formatting timestamps

CRITICAL: ALL Lambdas MUST use these functions for timestamp handling
- Prevents date-only strings on *_at fields (loses timezone)
- Ensures consistent ISO 8601 format across entire system
- Single module to update if format requirements change

Field Naming Convention:
- *_date fields → DATE ONLY (YYYY-MM-DD) - business date, no timezone
- *_at fields → ISO 8601 WITH TIMEZONE - precise moment, includes timezone

Usage:
    from shared.timestamp_utils import get_current_timestamp_utc, extract_date_only_from_email

    item = {
        'first_seen_at': get_current_timestamp_utc(),  # ISO 8601 with timezone
        'press_release_date': extract_date_only_from_email(email_date),  # DATE ONLY
    }

Last Updated: 2026-03-15
"""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def get_current_timestamp_utc() -> str:
    """
    Get current UTC timestamp in ISO 8601 format with timezone.

    Use for: *_at fields (first_seen_at, created_at, updated_at, etc.)
    Format: YYYY-MM-DDTHH:MM:SS+00:00

    Returns:
        str: ISO 8601 timestamp with timezone

    Example:
        >>> get_current_timestamp_utc()
        '2026-03-15T10:30:00+00:00'
    """
    return datetime.now(timezone.utc).isoformat()


def extract_timestamp_from_email_date(email_date_str: str) -> Optional[str]:
    """
    Extract ISO 8601 timestamp from email Date header (RFC 2822 format).

    Use for: *_at fields (email_received_at, etc.)
    Format: YYYY-MM-DDTHH:MM:SS+00:00

    Email dates are in RFC 2822 format:
        "Tue, 11 Mar 2026 20:00:00 +0000"

    Converts to ISO 8601 with timezone:
        "2026-03-11T20:00:00+00:00"

    Args:
        email_date_str: Email Date header string (RFC 2822 format)

    Returns:
        str: ISO 8601 timestamp with timezone, or None if parsing fails

    Example:
        >>> extract_timestamp_from_email_date("Tue, 11 Mar 2026 20:00:00 +0000")
        '2026-03-11T20:00:00+00:00'
    """
    if not email_date_str:
        return None

    try:
        dt = parsedate_to_datetime(email_date_str)
        return dt.isoformat()  # CORRECT - includes timezone
    except Exception as e:
        logger.warning(f"Could not parse email date '{email_date_str}': {e}")
        return None


def extract_date_only_from_email(email_date_str: str) -> Optional[str]:
    """
    Extract DATE ONLY (YYYY-MM-DD) from email Date header.

    Use for: *_date fields (press_release_date only)
    Format: YYYY-MM-DD (no time, no timezone)

    This is for business dates where timezone doesn't matter
    (e.g., "press release was issued on March 15, 2026").

    Args:
        email_date_str: Email Date header string (RFC 2822 format)

    Returns:
        str: Date in YYYY-MM-DD format, or None if parsing fails

    Example:
        >>> extract_date_only_from_email("Tue, 11 Mar 2026 20:00:00 +0000")
        '2026-03-11'
    """
    if not email_date_str:
        return None

    try:
        dt = parsedate_to_datetime(email_date_str)
        return dt.strftime('%Y-%m-%d')  # CORRECT - date only for *_date fields
    except Exception as e:
        logger.warning(f"Could not parse email date '{email_date_str}': {e}")
        return None


def get_current_date_only_utc() -> str:
    """
    Get current UTC date in YYYY-MM-DD format (no time, no timezone).

    Use for: *_date fields (press_release_date) as last resort fallback
    Format: YYYY-MM-DD

    WARNING: Only use as fallback when no better date source exists.
    Prefer extracting date from email body or email Date header.

    Returns:
        str: Date in YYYY-MM-DD format

    Example:
        >>> get_current_date_only_utc()
        '2026-03-15'
    """
    return datetime.now(timezone.utc).strftime('%Y-%m-%d')


def format_datetime_as_iso(dt: datetime) -> str:
    """
    Format datetime object as ISO 8601 with timezone.

    Use for: Converting datetime objects to string for DynamoDB *_at fields
    Format: YYYY-MM-DDTHH:MM:SS+00:00

    IMPORTANT: Only use for *_at fields, not *_date fields.

    Args:
        dt: datetime object (must have timezone)

    Returns:
        str: ISO 8601 timestamp with timezone

    Raises:
        ValueError: If datetime is naive (no timezone)

    Example:
        >>> from datetime import datetime, timezone
        >>> dt = datetime(2026, 3, 15, 10, 30, 0, tzinfo=timezone.utc)
        >>> format_datetime_as_iso(dt)
        '2026-03-15T10:30:00+00:00'
    """
    if dt.tzinfo is None:
        raise ValueError(
            "datetime object must have timezone. "
            "Use datetime.now(timezone.utc) instead of datetime.now()"
        )

    return dt.isoformat()


def validate_iso_timestamp(timestamp_str: str) -> bool:
    """
    Validate that a string is ISO 8601 format with timezone.

    Use for: Runtime validation of *_at field values

    Args:
        timestamp_str: Timestamp string to validate

    Returns:
        bool: True if valid ISO 8601 with timezone

    Example:
        >>> validate_iso_timestamp('2026-03-15T10:30:00+00:00')
        True
        >>> validate_iso_timestamp('2026-03-15')
        False  # Missing time and timezone
    """
    import re

    # ISO 8601 pattern: YYYY-MM-DDTHH:MM:SS+00:00
    pattern = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$')
    return pattern.match(timestamp_str) is not None


def validate_date_only(date_str: str) -> bool:
    """
    Validate that a string is DATE ONLY format (YYYY-MM-DD).

    Use for: Runtime validation of *_date field values

    Args:
        date_str: Date string to validate

    Returns:
        bool: True if valid YYYY-MM-DD format

    Example:
        >>> validate_date_only('2026-03-15')
        True
        >>> validate_date_only('2026-03-15T10:30:00+00:00')
        False  # Has time component
    """
    import re

    # DATE ONLY pattern: YYYY-MM-DD
    pattern = re.compile(r'^\d{4}-\d{2}-\d{2}$')
    return pattern.match(date_str) is not None
