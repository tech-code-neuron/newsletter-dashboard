"""
Title Formatter - Smart title case conversion for press releases

Handles:
- ALL CAPS to title case conversion
- Preserving acronyms (REIT, CEO, NYSE, etc.)
- Preserving company name capitalization (DiamondRock, AvalonBay)
- Standard title case rules (lowercase articles/prepositions)
"""
import re
from typing import List, Tuple


# Words to keep in ALL CAPS (acronyms, common terms)
PRESERVE_UPPER = {
    'REIT', 'CEO', 'CFO', 'COO', 'CIO', 'NYSE', 'NASDAQ', 'SEC', 'IPO', 'FFO',
    'Q1', 'Q2', 'Q3', 'Q4', 'FY', 'YTD', 'US', 'USA', 'UK', 'EU', 'AI', 'IT',
    'LLC', 'LP', 'INC', 'CORP', 'LTD', 'PLC', 'ETF', 'S&P', 'ESG', 'JV',
    'CBD', 'NOI', 'NAV', 'EBITDA', 'M&A', 'PR', 'IR', 'NYC', 'LA', 'DC', 'SF',
    'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X',
}

# Words to keep lowercase (articles, conjunctions, prepositions)
KEEP_LOWER = {'a', 'an', 'the', 'and', 'but', 'or', 'nor', 'for', 'so', 'yet',
              'at', 'by', 'in', 'of', 'on', 'to', 'up', 'as', 'is', 'if'}

# Company name patterns to preserve (CamelCase, special caps)
COMPANY_PATTERNS: List[Tuple[str, str]] = [
    # CamelCase company names
    (r'\bDiamondRock\b', 'DiamondRock'),
    (r'\bAvalonBay\b', 'AvalonBay'),
    (r'\bHealthpeak\b', 'Healthpeak'),
    (r'\bPrologis\b', 'Prologis'),
    (r'\bVentas\b', 'Ventas'),
    (r'\bWelltower\b', 'Welltower'),
    (r'\bRealty\s*Income\b', 'Realty Income'),
    (r'\bSimon\s*Property\b', 'Simon Property'),
    (r'\bPublic\s*Storage\b', 'Public Storage'),
    (r'\bEquinix\b', 'Equinix'),
    (r'\bDigital\s*Realty\b', 'Digital Realty'),
    (r'\bCrown\s*Castle\b', 'Crown Castle'),
    (r'\bAmerican\s*Tower\b', 'American Tower'),
    (r'\bSBA\s*Communications\b', 'SBA Communications'),
    (r'\bKimco\b', 'Kimco'),
    (r'\bRegency\s*Centers\b', 'Regency Centers'),
    (r'\bFederal\s*Realty\b', 'Federal Realty'),
    (r'\bEssex\b', 'Essex'),
    (r'\bUDR\b', 'UDR'),
    (r'\bMid-America\b', 'Mid-America'),
    (r'\bEquityLifeStyle\b', 'EquityLifestyle'),
    (r'\bSun\s*Communities\b', 'Sun Communities'),
    (r'\bInvitation\s*Homes\b', 'Invitation Homes'),
    (r'\bAMH\b', 'AMH'),
    (r'\bBXP\b', 'BXP'),
    (r'\bSL\s*Green\b', 'SL Green'),
    (r'\bVornado\b', 'Vornado'),
    (r'\bAlexandria\b', 'Alexandria'),
    (r'\bBioMed\b', 'BioMed'),
    (r'\bHealthcare\s*Trust\b', 'Healthcare Trust'),
    (r'\bOmega\s*Healthcare\b', 'Omega Healthcare'),
    (r'\bSabra\b', 'Sabra'),
    (r'\bCareTrust\b', 'CareTrust'),
    (r'\bLTC\s*Properties\b', 'LTC Properties'),
    (r'\bNational\s*Health\b', 'National Health'),
    (r'\bMedical\s*Properties\b', 'Medical Properties'),
    (r'\bCushman\s*&\s*Wakefield\b', 'Cushman & Wakefield'),
    (r'\bJones\s*Lang\s*LaSalle\b', 'Jones Lang LaSalle'),
    (r'\bCBRE\b', 'CBRE'),
    (r'\bJLL\b', 'JLL'),
    (r'\bNetSTREIT\b', 'NetSTREIT'),
    (r'\bSTAG\b', 'STAG'),
    (r'\bTerreno\b', 'Terreno'),
    (r'\bRexford\b', 'Rexford'),
    (r'\bFirst\s*Industrial\b', 'First Industrial'),
    (r'\bDuke\s*Realty\b', 'Duke Realty'),
    (r'\bEastGroup\b', 'EastGroup'),
    (r'\bMonmouth\b', 'Monmouth'),
    (r'\bPlymouth\b', 'Plymouth'),
    (r'\bGladstone\b', 'Gladstone'),
    (r'\bNexPoint\b', 'NexPoint'),
    (r'\bBlackstone\b', 'Blackstone'),
    (r'\bStarwood\b', 'Starwood'),
    (r'\bBrookfield\b', 'Brookfield'),
    (r'\bTPG\b', 'TPG'),
    (r'\bKKR\b', 'KKR'),
    (r'\bApollo\b', 'Apollo'),
    (r'\bAres\b', 'Ares'),
    (r'\bOaktree\b', 'Oaktree'),
]


def is_all_caps(text: str) -> bool:
    """Check if text is entirely uppercase (ignoring punctuation/numbers)."""
    letters = re.sub(r'[^a-zA-Z]', '', text)
    return letters.isupper() if letters else False


def smart_title_case(text: str) -> str:
    """
    Convert text to title case ONLY if it's all caps.
    Otherwise, preserve the exact original capitalization.

    When converting, preserves:
    - Company name capitalization (DiamondRock, AvalonBay)
    - Acronyms (REIT, CEO, Q1, NYSE)
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

    return title


class TitleFormatter:
    """
    Formats press release titles with smart case handling.

    Can be subclassed to add custom acronyms or company patterns.
    """

    def __init__(
        self,
        preserve_upper: set = None,
        keep_lower: set = None,
        company_patterns: list = None
    ):
        """
        Initialize with optional custom patterns.

        Args:
            preserve_upper: Additional acronyms to preserve (merged with defaults)
            keep_lower: Additional words to keep lowercase (merged with defaults)
            company_patterns: Additional company patterns (merged with defaults)
        """
        self.preserve_upper = PRESERVE_UPPER.copy()
        self.keep_lower = KEEP_LOWER.copy()
        self.company_patterns = list(COMPANY_PATTERNS)

        if preserve_upper:
            self.preserve_upper.update(preserve_upper)
        if keep_lower:
            self.keep_lower.update(keep_lower)
        if company_patterns:
            self.company_patterns.extend(company_patterns)

    def format(self, text: str) -> str:
        """
        Format a title using smart title case rules.

        Args:
            text: Raw title text

        Returns:
            Formatted title
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
            clean_word = re.sub(r'[^\w]', '', word.upper())

            if clean_word in self.preserve_upper:
                result.append(re.sub(r'[a-zA-Z]+', clean_word, word, count=1))
            elif i > 0 and word.lower() in self.keep_lower:
                result.append(word.lower())
            else:
                result.append(word.capitalize())

        title = ' '.join(result)

        # Apply company name pattern corrections
        for pattern, replacement in self.company_patterns:
            title = re.sub(pattern, replacement, title, flags=re.IGNORECASE)

        return title
