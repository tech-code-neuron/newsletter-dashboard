"""
Parser - Company Name Normalization
====================================
Normalize company names for fuzzy matching

SOLID Principles:
- Single Responsibility: Only normalizes names
- No Hardcoded Values: All suffixes from constants.py

Last Created: 2026-03-11
"""

import re
import logging
from constants import COMPANY_NAME_SUFFIXES

logger = logging.getLogger()


def normalize_company_name(name: str) -> str:
    """
    Normalize company name for fuzzy matching

    Single Responsibility: Only normalizes names

    Examples:
        "Alexander's, Inc." → "alexanders"
        "Terreno Realty Corporation" → "terreno"
        "S.L. Green Realty Corp." → "sl green"
        "W. P. Carey Inc." → "wp carey"

    Args:
        name: Company name string

    Returns:
        str: Normalized lowercase string
    """
    if not name:
        return ""

    # Convert to lowercase
    normalized = name.lower()

    # Remove common suffixes
    for suffix in COMPANY_NAME_SUFFIXES:
        normalized = re.sub(suffix, '', normalized)

    # Remove all punctuation except spaces
    normalized = re.sub(r'[^\w\s]', '', normalized)

    # Collapse adjacent single letters (W. P. → wp)
    # Handles initials that become separated when dots are removed
    while True:
        collapsed = re.sub(r'\b([a-z]) ([a-z])\b', r'\1\2', normalized)
        if collapsed == normalized:
            break
        normalized = collapsed

    # Normalize whitespace
    normalized = ' '.join(normalized.split())

    return normalized.strip()


def extract_sender_name(from_field: str) -> str:
    """
    Extract sender name from From field

    Single Responsibility: Only extracts sender name

    Example:
        "Chatham Lodging Trust <alerts@em.equisolve.com>" → "Chatham Lodging Trust"

    Args:
        from_field: Email From header

    Returns:
        str: Sender name or None
    """
    if not from_field:
        return None

    # Try to extract name from "Name <email>" format
    match = re.match(r'^(.+?)\s*<.+>$', from_field)
    if match:
        return match.group(1).strip().strip('"').strip("'")

    # If no angle brackets, return as-is (might be just email)
    return from_field.strip()
