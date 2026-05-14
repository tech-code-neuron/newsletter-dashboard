"""
Title Case Module - Smart Title Case Conversion + Duplication Detection
=========================================================================
Shared module for title cleanup across all Lambdas.

Used by:
- Parser (RSS fast path)
- Enricher (via title_cleanup)
- Playwright Scraper

Key Features:
- Detects and removes company name duplication ("Company - Company Announces...")
- Only converts to title case if text is ALL CAPS (preserves mixed case)
- Preserves acronyms (REIT, CEO, Q1, NYSE, etc.)
- Preserves company names (DiamondRock, AvalonBay, etc.)
- Standard title case rules (lowercase articles/prepositions)
"""

import re

# Words to preserve as ALL CAPS (acronyms, common terms)
PRESERVE_UPPER = {
    'REIT', 'CEO', 'CFO', 'COO', 'CIO', 'NYSE', 'NASDAQ', 'SEC', 'IPO', 'FFO',
    'Q1', 'Q2', 'Q3', 'Q4', 'FY', 'YTD', 'US', 'USA', 'UK', 'EU', 'AI', 'IT',
    'LLC', 'LP', 'LTD', 'PLC', 'ETF', 'S&P', 'ESG', 'JV',
    'CBD', 'NOI', 'NAV', 'EBITDA', 'M&A', 'PR', 'IR', 'NYC', 'LA', 'DC', 'SF',
    'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X',
    'UMH', 'UDR', 'AMH', 'BXP', 'JLL', 'KKR', 'TPG', 'BGO',
}

# Words to keep lowercase (articles, conjunctions, prepositions)
KEEP_LOWER = {'a', 'an', 'the', 'and', 'but', 'or', 'nor', 'for', 'so', 'yet',
              'at', 'by', 'in', 'of', 'on', 'to', 'up', 'as', 'is', 'if'}

# Special title case patterns (applied after general title casing)
SPECIAL_CASE_PATTERNS = [
    (r'\bINC\b\.?', 'Inc.'),
    (r'\bCORP\b\.?', 'Corp.'),
]

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


# ============================================================================
# Title Duplication Detection
# ============================================================================

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
    r',?\s*Limited\s*$',
    r',?\s*Ltd\.?\s*$',
    r',?\s*Company\s*$',
    r',?\s*Co\.?\s*$',
    r',?\s*REIT\s*$',
    r',?\s*Trust\s*$',
]


def normalize_for_comparison(text: str) -> str:
    """
    Normalize text for comparison only (not for output).
    Strips legal suffixes, "The" prefix, punctuation, and lowercases.
    """
    normalized = text.strip()
    normalized = re.sub(r'^The\s+', '', normalized, flags=re.IGNORECASE)
    for suffix_pattern in LEGAL_SUFFIXES:
        normalized = re.sub(suffix_pattern, '', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'[^\w\s]', '', normalized)
    normalized = re.sub(r'\s+', ' ', normalized)
    return normalized.lower().strip()


def clean_title(title: str, ticker: str = None) -> dict:
    """
    Clean title by detecting and removing company name duplication.

    Examples:
        "Company Inc. - Company Announces Q1" → "Company Announces Q1"
        "COMPANY REPORTS EARNINGS" → "Company Reports Earnings" (title case)

    Args:
        title: Raw title from email subject
        ticker: Optional company ticker for enhanced detection

    Returns:
        dict: {
            'cleaned_title': str,
            'original_title': str,
            'was_cleaned': bool
        }
    """
    if not title:
        return {'cleaned_title': title, 'original_title': title, 'was_cleaned': False}

    original_title = title

    # Strip email forward/reply prefixes
    title = re.sub(r'^(Fw:|Fwd:|Re:|RE:|FW:|FWD:)\s*', '', title, flags=re.IGNORECASE).strip()
    title = re.sub(r'^[-–—]+\s*', '', title).strip()

    # If no " - " separator, check for back-to-back company name duplication
    if ' - ' not in title:
        # Strategy: Check if title starts with pattern that repeats later
        # Example: "TPG Real Estate Trust TPG RE Finance Trust, Inc. Reports..."
        words = title.split()
        if len(words) >= 4:
            for prefix_len in [1, 2, 3]:
                prefix = ' '.join(words[:prefix_len]).upper()
                remainder = ' '.join(words[prefix_len:])
                match = re.search(rf'\b{re.escape(prefix)}\b', remainder.upper())
                if match:
                    split_pos = len(' '.join(words[:prefix_len])) + 1 + match.start()
                    cleaned = title[split_pos:]
                    cleaned = smart_title_case(cleaned)
                    return {
                        'cleaned_title': cleaned,
                        'original_title': original_title,
                        'was_cleaned': True
                    }

        # No duplication found, just apply title case
        cleaned = smart_title_case(title)
        return {
            'cleaned_title': cleaned,
            'original_title': original_title,
            'was_cleaned': cleaned != title
        }

    # Split on first " - " separator
    parts = title.split(' - ', 1)
    before = parts[0].strip()
    after = parts[1].strip()

    # Check for "Company Name - TICKER Title" pattern
    if ticker and after.upper().startswith(ticker.upper() + ' '):
        cleaned = smart_title_case(after)
        return {'cleaned_title': cleaned, 'original_title': original_title, 'was_cleaned': True}

    # Normalize for comparison
    normalized_before = normalize_for_comparison(before)
    normalized_after = normalize_for_comparison(after)

    # Check if normalized "before" appears in normalized "after" (duplication)
    if normalized_before and normalized_before in normalized_after:
        cleaned = after
    else:
        cleaned = f"{before} {after}"

    # Safety check
    if len(cleaned) < 10:
        return {'cleaned_title': title, 'original_title': original_title, 'was_cleaned': False}

    cleaned = smart_title_case(cleaned)
    return {'cleaned_title': cleaned, 'original_title': original_title, 'was_cleaned': True}
