"""
Sponsor Configuration - Single source of truth for PE sponsors.

This module defines the canonical list of private equity sponsors used
for private REIT companies. All sponsor names in the database should
match one of these canonical forms.

Usage:
    from config.sponsors import SPONSORS, get_canonical_sponsor, get_sponsor_choices

    # Check if a name is canonical
    canonical = get_canonical_sponsor('GIP')  # Returns 'Global Infrastructure Partners'

    # Get choices for form dropdowns
    choices = get_sponsor_choices()  # Returns [(value, label), ...]
"""
from typing import List, Tuple, Optional


# =============================================================================
# Canonical Sponsor List (alphabetically sorted)
# =============================================================================
# These are the "correct" forms that should be stored in the database.
# Add new sponsors here when onboarding new private companies.

SPONSORS: List[str] = [
    'Affinius',
    'AJ Capital Partners',
    'Almanac Realty',
    'Apollo Global Management',
    'Ares Management',
    'Argo Infrastructure Partners',
    'Bain Capital',
    'Barings',
    'Bellco Capital',
    'Berkshire Partners',
    'Blackstone',
    'Blue Owl Capital',
    'Bridge Industrial',
    'Brookfield Asset Management',
    'CalPERS',
    'CalSTRS',
    'Capital Research',
    'Carlyle Group',
    'CDPQ',
    'Centerbridge Partners',
    'Cerberus Capital Management',
    'Clarion Partners',
    'Cloud Capital',
    'Coastwood Capital',
    'Conversant Capital',
    'Crow Holdings Capital',
    'Daiwa House',
    'Declaration Partners',
    'DigitalBridge',
    'EQT',
    'Extra Space Storage',
    'Federal Capital Partners',
    'GI Partners',
    'GIC',
    'Global Infrastructure Partners',
    'Greystar',
    'Guardian Life',
    'Hackman Capital Partners',
    'Host Hotels & Resorts',
    'Hudson Pacific Properties',
    'IFM Investors',
    'Innovative Industrial Properties',
    'Institutional',
    'Ivanhoe Cambridge',
    'J.P. Morgan Asset Management',
    'John Swire & Sons',
    'Kayne Anderson',
    'KKR',
    'Koch Industries',
    'KSL Capital Partners',
    'Lee Equity Partners',
    'Lowe Enterprises',
    'Macquarie Asset Management',
    'Madison International Realty',
    'MGX',
    'Monarch Alternative Capital',
    'Morgan Stanley Investment Management',
    'Nautic Partners',
    'Ontario Teachers\' Pension Plan',
    'Oxford Properties',
    'PGIM Real Estate',
    'PIMCO',
    'Platform Ventures',
    'Pretium Partners',
    'QuadReal Property Group',
    'Saxum Real Estate',
    'Silver Lake',
    'Silverstein Properties',
    'SoftBank',
    'Square Mile Capital',
    'Starwood Capital Group',
    'StepStone Group',
    'Stockbridge Capital',
    'Stonepeak',
    'Temerity Strategic Partners',
    'Thayer Street Partners',
    'Tishman Speyer',
    'TJC',
    'Toll Brothers',
    'TPG',
    'UBS Asset Management',
    'Venture/Growth-backed',
    'Westport Capital Partners',
]

# Special values for non-institutional sponsors
SPECIAL_SPONSORS: List[str] = [
    'Family-owned',
    'Institutional',
    'Management/PE-backed',
    'Venture/Growth-backed',
]


# =============================================================================
# Sponsor Aliases (for deduplication)
# =============================================================================
# Maps variations/abbreviations to canonical names.
# Key: lowercase variation, Value: canonical name
# Used by get_canonical_sponsor() to normalize input.

SPONSOR_ALIASES = {
    # Abbreviations
    'gip': 'Global Infrastructure Partners',
    'kkr': 'KKR',
    'tpg': 'TPG',
    'gic': 'GIC',
    'eqt': 'EQT',
    'cdpq': 'CDPQ',
    'tjc': 'TJC',
    'mgx': 'MGX',
    'ifm': 'IFM Investors',
    'ubs': 'UBS Asset Management',

    # Incomplete names
    'ksl capital': 'KSL Capital Partners',
    'ksl': 'KSL Capital Partners',
    'almanac': 'Almanac Realty',
    'almanac realty': 'Almanac Realty',
    'ares': 'Ares Management',
    'apollo': 'Apollo Global Management',
    'brookfield': 'Brookfield Asset Management',
    'centerbridge': 'Centerbridge Partners',
    'cerberus': 'Cerberus Capital Management',
    'macquarie': 'Macquarie Asset Management',
    'starwood': 'Starwood Capital Group',
    'pretium': 'Pretium Partners',
    'stonepeak': 'Stonepeak',
    'blue owl': 'Blue Owl Capital',
    'greystar': 'Greystar',
    'blackstone': 'Blackstone',
    'carlyle': 'Carlyle Group',
    'carlyle group': 'Carlyle Group',

    # Strategy-specific variants (merged to parent)
    'bain capital re': 'Bain Capital',
    'bain capital real estate': 'Bain Capital',
    'eqt infrastructure': 'EQT',
    'morgan stanley re': 'Morgan Stanley Investment Management',
    'morgan stanley infrastructure': 'Morgan Stanley Investment Management',
    'morgan stanley real estate': 'Morgan Stanley Investment Management',
    'pgim re': 'PGIM Real Estate',
    'pgim real estate': 'PGIM Real Estate',

    # Punctuation/formatting variations
    'j.p. morgan': 'J.P. Morgan Asset Management',
    'jp morgan': 'J.P. Morgan Asset Management',
    'jpmorgan': 'J.P. Morgan Asset Management',
    'j.p. morgan asset management': 'J.P. Morgan Asset Management',
    'jpmorgan asset management': 'J.P. Morgan Asset Management',

    # Name variations
    'global infrastructure partners': 'Global Infrastructure Partners',
    'ivanhoé cambridge': 'Ivanhoe Cambridge',
    'ivanhoe cambridge': 'Ivanhoe Cambridge',
    "ontario teachers'": "Ontario Teachers' Pension Plan",
    'ontario teachers': "Ontario Teachers' Pension Plan",
    'otpp': "Ontario Teachers' Pension Plan",
    'hackman': 'Hackman Capital Partners',
    'hackman capital': 'Hackman Capital Partners',
    'host hotels': 'Host Hotels & Resorts',
    'extra space': 'Extra Space Storage',
    'madison international': 'Madison International Realty',
    'coastwood': 'Coastwood Capital',
    'saxum': 'Saxum Real Estate',
    'stockbridge': 'Stockbridge Capital',
    'quadreal': 'QuadReal Property Group',
    'monarch': 'Monarch Alternative Capital',
    'silverstein family': 'Silverstein Properties',
    'silverstein': 'Silverstein Properties',
    'koch': 'Koch Industries',
    'softbank': 'SoftBank',
    'silver lake': 'Silver Lake',
    'calpers': 'CalPERS',
    'calstrs': 'CalSTRS',
    'argo': 'Argo Infrastructure Partners',
    'westport capital': 'Westport Capital Partners',

    # Special categories
    'institutional': 'Institutional',
    'family-owned': 'Family-owned',
    'management/pe-backed': 'Management/PE-backed',
    'venture/growth-backed': 'Venture/Growth-backed',
}


# =============================================================================
# Helper Functions
# =============================================================================

def get_canonical_sponsor(name: str) -> str:
    """
    Map a sponsor name to its canonical form.

    Args:
        name: Sponsor name (any casing/variation)

    Returns:
        Canonical sponsor name if found in aliases,
        otherwise returns the input stripped of whitespace.

    Examples:
        >>> get_canonical_sponsor('GIP')
        'Global Infrastructure Partners'
        >>> get_canonical_sponsor('Bain Capital RE')
        'Bain Capital'
        >>> get_canonical_sponsor('  Blackstone  ')
        'Blackstone'
    """
    if not name:
        return ''

    cleaned = name.strip()
    normalized = cleaned.lower()

    # Check aliases first
    if normalized in SPONSOR_ALIASES:
        return SPONSOR_ALIASES[normalized]

    # If exact match in canonical list, return it
    for sponsor in SPONSORS:
        if sponsor.lower() == normalized:
            return sponsor

    # No match found - return cleaned input (new sponsor)
    return cleaned


def get_sponsor_choices(include_empty: bool = True) -> List[Tuple[str, str]]:
    """
    Get sponsor choices for form dropdowns.

    Args:
        include_empty: Whether to include empty "Select..." option

    Returns:
        List of (value, label) tuples for use in SelectField choices.
    """
    choices = []

    if include_empty:
        choices.append(('', 'Select Sponsor (optional)'))

    # Add canonical sponsors (excluding special values)
    regular_sponsors = [s for s in SPONSORS if s not in SPECIAL_SPONSORS]
    for sponsor in sorted(regular_sponsors):
        choices.append((sponsor, sponsor))

    # Add separator and special values
    choices.append(('', '──────────────'))
    for special in SPECIAL_SPONSORS:
        choices.append((special, special))

    return choices


def is_canonical_sponsor(name: str) -> bool:
    """
    Check if a sponsor name is in canonical form.

    Args:
        name: Sponsor name to check

    Returns:
        True if the name matches a canonical sponsor exactly.
    """
    if not name:
        return False
    return name.strip() in SPONSORS or name.strip() in SPECIAL_SPONSORS


def get_all_sponsors() -> List[str]:
    """
    Get all canonical sponsors (including special values).

    Returns:
        Sorted list of all canonical sponsor names.
    """
    return sorted(SPONSORS)
