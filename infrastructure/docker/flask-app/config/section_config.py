"""
Newsletter Section Configuration - Single Source of Truth

Defines all section metadata: keys, display names, and ordering.
Import from here to avoid duplication across modules.
"""
from typing import List, Dict, Tuple


# Section definitions in display order
# Format: (internal_key, display_name, dynamo_key)
SECTIONS: List[Tuple[str, str, str]] = [
    ('headline', 'Headlines', 'headlines'),
    ('financing', 'Financings and Offerings', 'financing_releases'),
    ('management', 'Management and Board Changes', 'management_changes'),
    ('property', 'Property Transactions and Leases', 'property_transactions'),
    ('earnings', 'Earnings Releases and Quarterly Updates', 'earnings_releases'),
    ('conference_call', 'Conference Call Scheduling', 'conference_calls'),
    ('dividend', 'Dividends', 'dividends'),
    ('other', 'Other Announcements', 'other_announcements'),
]

# Derived constants for convenience
SECTION_KEYS: List[str] = [s[0] for s in SECTIONS]
SECTION_DISPLAY_NAMES: Dict[str, str] = {s[0]: s[1] for s in SECTIONS}
SECTION_DYNAMO_KEYS: Dict[str, str] = {s[0]: s[2] for s in SECTIONS}
DYNAMO_TO_INTERNAL: Dict[str, str] = {s[2]: s[0] for s in SECTIONS}

# Valid sections for manual override (includes 'auto' for resetting)
VALID_MANUAL_SECTIONS = set(SECTION_KEYS) | {'auto'}


def get_display_name(section_key: str) -> str:
    """Get display name for a section key."""
    return SECTION_DISPLAY_NAMES.get(section_key, 'Other Announcements')


def get_empty_sections() -> Dict[str, list]:
    """Get empty sections dict with all DynamoDB keys."""
    return {s[2]: [] for s in SECTIONS}


def get_sections_from_data(sections_data: dict) -> Dict[str, list]:
    """
    Map internal section keys to DynamoDB keys.

    Args:
        sections_data: Dict with internal keys (headline, financing, etc.)

    Returns:
        Dict with DynamoDB keys (headlines, financing_releases, etc.)
    """
    return {
        dynamo_key: sections_data.get(internal_key, [])
        for internal_key, _, dynamo_key in SECTIONS
    }
