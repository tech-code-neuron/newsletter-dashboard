"""
Title Cleanup Module - Remove Company Name Duplication + Smart Title Case

Problem:
  Current: "Xenia Hotels & Resorts, Inc. - Xenia Hotels & Resorts Announces Q1 Earnings"
  Desired: "Xenia Hotels & Resorts Announces Q1 Earnings"

Algorithm:
  1. Split on first " - " separator
  2. Normalize both parts (strip legal suffixes, "The" prefix, punctuation)
  3. Check if normalized "before" is found in normalized "after" (duplication)
  4. If YES: Return original "after" part
  5. If NO: Concatenate "before + after" (remove " - ")
  6. Apply smart title case (if ALL CAPS, convert to title case)

Key Principles:
  - Normalization is for COMPARISON only (detect duplication)
  - Title case conversion only if ALL CAPS
  - Preserve company names, acronyms (REIT, CEO, Q1, etc.)
"""

import re
import logging

logger = logging.getLogger()

# Legal entity suffixes to strip during normalization (for comparison only)
LEGAL_SUFFIXES = [
    r',?\s*Incorporated\s*$',
    r',?\s*Inc\.?\s*$',
    r',?\s*Corporation\s*$',
    r',?\s*Corp\.?\s*$',
    r',?\s*Limited Liability Company\s*$',
    r',?\s*L\.L\.C\.?\s*$',
    r',?\s*LLC\.?\s*$',
    r',?\s*Limited Partnership\s*$',
    r',?\s*L\.P\.?\s*$',
    r',?\s*LP\.?\s*$',
    r',?\s*Limited Liability Partnership\s*$',
    r',?\s*L\.L\.P\.?\s*$',
    r',?\s*LLP\.?\s*$',
    r',?\s*Limited\s*$',
    r',?\s*Ltd\.?\s*$',
    r',?\s*Company\s*$',
    r',?\s*Co\.?\s*$',
    r',?\s*REIT\s*$',
    r',?\s*Trust\s*$',
    r',?\s*Public Limited Company\s*$',
    r',?\s*P\.L\.C\.?\s*$',
    r',?\s*PLC\.?\s*$',
]

# Words to preserve as ALL CAPS (acronyms, common terms)
PRESERVE_UPPER = {
    'REIT', 'CEO', 'CFO', 'COO', 'CIO', 'NYSE', 'NASDAQ', 'SEC', 'IPO', 'FFO',
    'Q1', 'Q2', 'Q3', 'Q4', 'FY', 'YTD', 'US', 'USA', 'UK', 'EU', 'AI', 'IT',
    'LLC', 'LP', 'LTD', 'PLC', 'ETF', 'S&P', 'ESG', 'JV',
    'CBD', 'NOI', 'NAV', 'EBITDA', 'M&A', 'PR', 'IR', 'NYC', 'LA', 'DC', 'SF',
    'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X',
    'UMH', 'UDR', 'AMH', 'BXP', 'JLL', 'KKR', 'TPG', 'BGO',  # Ticker-style company names
}

# Special title case patterns (applied after general title casing)
SPECIAL_CASE_PATTERNS = [
    (r'\bINC\b\.?', 'Inc.'),      # Incorporated - always "Inc."
    (r'\bCORP\b\.?', 'Corp.'),    # Corporation - always "Corp."
]

# Words to keep lowercase (articles, conjunctions, prepositions)
KEEP_LOWER = {'a', 'an', 'the', 'and', 'but', 'or', 'nor', 'for', 'so', 'yet',
              'at', 'by', 'in', 'of', 'on', 'to', 'up', 'as', 'is', 'if'}

# Company name patterns to preserve (CamelCase, special caps)
COMPANY_PATTERNS = [
    (r'\bDiamondRock\b', 'DiamondRock'),
    (r'\bAvalonBay\b', 'AvalonBay'),
    (r'\bHealthpeak\b', 'Healthpeak'),
    (r'\bRealty\s*Income\b', 'Realty Income'),
    (r'\bSimon\s*Property\b', 'Simon Property'),
    (r'\bPublic\s*Storage\b', 'Public Storage'),
    (r'\bDigital\s*Realty\b', 'Digital Realty'),
    (r'\bCrown\s*Castle\b', 'Crown Castle'),
    (r'\bAmerican\s*Tower\b', 'American Tower'),
    (r'\bSBA\s*Communications\b', 'SBA Communications'),
    (r'\bRegency\s*Centers\b', 'Regency Centers'),
    (r'\bFederal\s*Realty\b', 'Federal Realty'),
    (r'\bMid-America\b', 'Mid-America'),
    (r'\bEquityLifestyle\b', 'EquityLifestyle'),
    (r'\bSun\s*Communities\b', 'Sun Communities'),
    (r'\bInvitation\s*Homes\b', 'Invitation Homes'),
    (r'\bSL\s*Green\b', 'SL Green'),
    (r'\bOmega\s*Healthcare\b', 'Omega Healthcare'),
    (r'\bCareTrust\b', 'CareTrust'),
    (r'\bLTC\s*Properties\b', 'LTC Properties'),
    (r'\bMedical\s*Properties\b', 'Medical Properties'),
    (r'\bNetSTREIT\b', 'NetSTREIT'),
    (r'\bFirst\s*Industrial\b', 'First Industrial'),
    (r'\bDuke\s*Realty\b', 'Duke Realty'),
    (r'\bEastGroup\b', 'EastGroup'),
    (r'\bNexPoint\b', 'NexPoint'),
]


def normalize_for_comparison(text: str) -> str:
    """
    Normalize text for comparison only (not for output).
    Strips legal suffixes, "The" prefix, punctuation, and lowercases.

    Args:
        text: Text to normalize

    Returns:
        Normalized text (lowercase, no punctuation/suffixes)
    """
    normalized = text.strip()

    # Strip "The" prefix (case-insensitive)
    normalized = re.sub(r'^The\s+', '', normalized, flags=re.IGNORECASE)

    # Strip legal suffixes
    for suffix_pattern in LEGAL_SUFFIXES:
        normalized = re.sub(suffix_pattern, '', normalized, flags=re.IGNORECASE)

    # Remove punctuation (keep spaces)
    normalized = re.sub(r'[^\w\s]', '', normalized)

    # Normalize whitespace
    normalized = re.sub(r'\s+', ' ', normalized)

    # Lowercase
    normalized = normalized.lower().strip()

    return normalized


def is_all_caps(text: str) -> bool:
    """
    Check if text is entirely uppercase (ignoring punctuation/numbers).

    Args:
        text: Text to check

    Returns:
        True if all letters are uppercase
    """
    letters = re.sub(r'[^a-zA-Z]', '', text)
    return letters.isupper() if letters else False


def smart_title_case(text: str) -> str:
    """
    Convert text to title case ONLY if it's all caps.
    Otherwise, preserve the exact original capitalization.

    When converting, preserves:
    - Company name capitalization (DiamondRock, AvalonBay)
    - Acronyms (REIT, CEO, Q1, NYSE, UMH)
    - Standard title case rules (lowercase articles/prepositions except at start)

    Args:
        text: Raw title text

    Returns:
        Properly formatted string (title case if was ALL CAPS, otherwise unchanged)
    """
    if not text:
        return text

    # Only convert if the title is ALL CAPS
    if not is_all_caps(text):
        return text

    # Convert to title case
    words = text.split()
    result = []

    for i, word in enumerate(words):
        # Check if word (stripped of punctuation) should be preserved as uppercase
        clean_word = re.sub(r'[^\w]', '', word.upper())

        if clean_word in PRESERVE_UPPER:
            # Keep acronym uppercase, preserve original punctuation
            result.append(re.sub(r'[a-zA-Z]+', clean_word, word, count=1))
        elif i > 0 and word.lower() in KEEP_LOWER:
            # Lowercase articles/prepositions (except at start)
            result.append(word.lower())
        else:
            # Title case the word
            result.append(word.capitalize())

    title = ' '.join(result)

    # Apply company name pattern corrections
    for pattern, replacement in COMPANY_PATTERNS:
        title = re.sub(pattern, replacement, title, flags=re.IGNORECASE)

    # Apply special case patterns (Inc., Corp., etc.)
    for pattern, replacement in SPECIAL_CASE_PATTERNS:
        title = re.sub(pattern, replacement, title, flags=re.IGNORECASE)

    return title


def clean_title(title: str, ticker: str = None) -> dict:
    """
    Clean title by detecting and removing company name duplication.

    Normalization is for comparison only - output is always original text.

    Args:
        title: Raw title from email subject
        ticker: Optional company ticker for enhanced detection

    Returns:
        dict: {
            'cleaned_title': str,  # Cleaned version (original text, not normalized)
            'original_title': str,  # Original for reference
            'was_cleaned': bool    # Whether cleaning was applied
        }
    """
    if not title:
        return {
            'cleaned_title': title,
            'original_title': title,
            'was_cleaned': False
        }

    original_title = title

    # Strip email forward/reply prefixes FIRST (Fw:, Fwd:, Re:, etc.)
    email_header_pattern = r'^(Fw:|Fwd:|Re:|RE:|FW:|FWD:)\s*'
    title = re.sub(email_header_pattern, '', title, flags=re.IGNORECASE).strip()

    # Strip leading dashes/hyphens (common after removing headers)
    title = re.sub(r'^[-\u2013\u2014]+\s*', '', title).strip()

    # If no " - " separator, still apply title case if needed
    if ' - ' not in title:
        cleaned = smart_title_case(title)
        return {
            'cleaned_title': cleaned,
            'original_title': original_title,
            'was_cleaned': cleaned != title
        }

    # Split on first " - " separator only
    parts = title.split(' - ', 1)
    before = parts[0].strip()
    after = parts[1].strip()

    # Check for "Company Name - TICKER Title" pattern
    # If "after" starts with the ticker, treat entire "before" as company identifier
    if ticker and after.upper().startswith(ticker.upper() + ' '):
        # Pattern: "Four Corners Property Trust - FCPT Announces..."
        # Return: "FCPT Announces..."
        cleaned = smart_title_case(after)
        logger.info(f"✂️  Ticker prefix detected: '{before}' → '{after[:50]}...'")
        return {
            'cleaned_title': cleaned,
            'original_title': original_title,
            'was_cleaned': True
        }

    # Normalize for comparison only
    normalized_before = normalize_for_comparison(before)
    normalized_after = normalize_for_comparison(after)

    # Check if normalized "before" appears in normalized "after" (duplication)
    if normalized_before and normalized_before in normalized_after:
        # Duplication detected - keep original "after" part
        cleaned = after
        logger.info(f"✂️  Duplication detected: '{before}' found in '{after[:50]}...'")
    else:
        # No duplication - concatenate both parts (remove " - ")
        cleaned = f"{before} {after}"
        logger.info(f"✂️  No duplication: concatenating '{before}' + '{after[:30]}...'")

    # Safety check: Don't create titles that are too short
    if len(cleaned) < 10:
        logger.warning(f"Cleaned title too short ({len(cleaned)} chars), keeping original")
        return {
            'cleaned_title': title,
            'original_title': original_title,
            'was_cleaned': False
        }

    # Apply smart title case (convert to title case if ALL CAPS)
    cleaned = smart_title_case(cleaned)

    return {
        'cleaned_title': cleaned,
        'original_title': original_title,
        'was_cleaned': True
    }


def add_display_title_to_metadata(metadata: dict, ticker: str = None) -> None:
    """
    Add cleaned display_title to metadata before DynamoDB save.

    Feature-flagged with ENABLE_TITLE_CLEANUP env var (default: 'true')

    Args:
        metadata: Metadata dict to update (modified in-place)
        ticker: Optional company ticker for enhanced title cleaning
    """
    import os

    # Feature flag check
    if os.environ.get('ENABLE_TITLE_CLEANUP', 'true').lower() != 'true':
        metadata['display_title'] = metadata.get('subject', '')
        return

    email_subject = metadata.get('subject', '')

    if not email_subject:
        return

    try:
        cleanup_result = clean_title(email_subject, ticker)

        if cleanup_result['was_cleaned']:
            metadata['display_title'] = cleanup_result['cleaned_title']
            logger.info(f"Title cleaned: '{email_subject[:50]}...' → '{cleanup_result['cleaned_title'][:50]}...'")
        else:
            metadata['display_title'] = email_subject

    except Exception as e:
        logger.error(f"Title cleanup failed: {e}", exc_info=True)
        # Fallback: Use original title
        metadata['display_title'] = email_subject