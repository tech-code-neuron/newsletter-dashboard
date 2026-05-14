"""
Section Classifier - Categorize press releases into newsletter sections

Classifies press releases based on title keywords into:
- Headlines (default, newsworthy items)
- Earnings (quarterly results, FFO/AFFO)
- Financing (offerings, notes, credit facilities)
- Property (acquisitions, dispositions, development)
- Other (dividends, webcasts, routine announcements)
"""
import re
from typing import Any, Dict, List
from config.design_tokens import get_color


# Category detection patterns (for badge display)
CATEGORY_PATTERNS: Dict[str, List[str]] = {
    'EARNINGS': [
        r'\bearnings?\b', r'\bquarterly\b', r'\bQ[1-4]\b', r'\bresults?\b',
        r'\bfinancial results?\b', r'\breports? results?\b', r'\bfiscal\b'
    ],
    'ACQUISITION': [
        r'\bacquir(e|es|ed|ing|ition)\b', r'\bpurchas(e|es|ed|ing)\b',
        r'\bbuy(s|ing)?\b', r'\bmerger?\b', r'\btransaction\b', r'\bacquisition\b'
    ],
    'DIVIDEND': [
        r'\bdividends?\b', r'\bdistribution\b', r'\bdeclare(s|d)?\b',
        r'\bpayable\b', r'\bquarterly (cash )?distribution\b'
    ],
    'FINANCING': [
        r'\boffering\b', r'\bnotes?\b', r'\bcredit facility\b',
        r'\bdebt\b', r'\bfinancing\b', r'\bunderwritten\b', r'\bsecondary offering\b'
    ],
}

# Category badge colors (SOLID compliant: uses design tokens)
CATEGORY_COLORS: Dict[str, str] = {
    'EARNINGS': get_color('primary'),      # Blue
    'ACQUISITION': get_color('success'),   # Green
    'DIVIDEND': get_color('warning'),      # Yellow/Gold
    'FINANCING': get_color('info'),        # Purple
    'OTHER': get_color('text_muted'),      # Gray
}

# Earnings keywords (earnings releases, results announcements, conference calls)
# Be careful: "quarter" alone could be dividend
# Only use definitive earnings terms
EARNINGS_KEYWORDS: List[str] = [
    r'\bearnings\b',           # "earnings" (most specific)
    r'\bresults\b',            # "results" (Q1 results, financial results)
    r'\bFFO\b',                # Funds From Operations (REIT-specific earnings)
    r'\bAFFO\b',               # Adjusted FFO
    r'\bconference call\b',    # Earnings conference calls
    r'\bearnings call\b',      # Variation
]

# Other Announcements keywords (mundane/routine announcements)
# NOTE: Dividend and conference call keywords moved to dedicated sections
OTHER_ANNOUNCEMENTS_KEYWORDS: List[str] = [
    # Transcripts and investor materials
    r'\btranscript\b',
    r'\bsupplemental\b',
    r'\binvestor presentation\b',

    # Reports and awards (routine, not headline-worthy)
    r'\bannual report\b',
    r'\bsustainability report\b',
    r'\btop workplace\b',
]

# Financings and Offerings keywords (capital markets activity)
FINANCING_KEYWORDS: List[str] = [
    # Debt offerings
    r'\bdebt offering\b',
    r'\bsenior notes?\b',
    r'\bconvertible notes?\b',
    r'\bsubordinated notes?\b',
    r'\bsecured notes?\b',
    r'\bunsecured notes?\b',
    r'\bfloating rate notes?\b',
    r'\bfixed rate notes?\b',
    r'\bnotes offering\b',
    r'\bbond offering\b',
    r'\bbonds?\b',
    r'\bdebentures?\b',
    r'\bgreen bond\b',
    r'\bsustainability bond\b',
    r'\b144A\b',

    # Equity offerings
    r'\bequity offering\b',
    r'\bpublic offering\b',
    r'\bsecondary offering\b',
    r'\bfollow-on offering\b',
    r'\bstock offering\b',
    r'\bpreferred stock\b',
    r'\bprivate placement\b',
    r'\bATM\b',
    r'\bat-the-market\b',
    r'\bshelf registration\b',

    # Credit facilities
    r'\bCMBS\b',
    r'\bterm loan\b',
    r'\brevolver\b',
    r'\bcredit agreement\b',
    r'\bcredit facility\b',
    r'\bcredit line\b',
    r'\bmortgage\b',
    r'\brefinanc(e|es|ed|ing)\b',

    # Pricing and redemption
    r'\bbond pricing\b',
    r'\bnote pricing\b',
    r'\boffering prices?\b',
    r'\btender offer\b',
    r'\bredemption\b',
    r'\bcallable notes?\b',

    # Collateralized/Securitization instruments
    r'\bcollateraliz(e|ed|es|ing|ation)\b',
    r'\bsecuritiz(e|ed|es|ing|ation)\b',
    r'\bCLO\b',  # Collateralized Loan Obligation
    r'\bCDO\b',  # Collateralized Debt Obligation

    # Standalone offering (singular and plural)
    r'\bofferings?\b',
]

# Property Transactions keywords (acquisitions, dispositions)
PROPERTY_TRANSACTION_KEYWORDS: List[str] = [
    # Core transaction terms
    r'\bacquisition\b',
    r'\bdisposition\b',
    r'\bpurchase[sd]?\b',
    r'\bsale[s]?\b',
    r'\bdivestiture\b',

    # Action verbs
    r'\bacquire[sd]?\b',
    r'\bsell[s]?\b',
    r'\bsold\b',
    r'\bbuy[s]?\b',
    r'\bbought\b',
    r'\bdivest(ed|s)?\b',
    r'\bdispose[sd]?\b',

    # Compound terms
    r'\bproperty sale\b',
    r'\basset sale\b',
    r'\bportfolio sale\b',
    r'\bproperty acquisition\b',
    r'\breal estate transaction\b',
    r'\bstrategic acquisition\b',

    # Development and ground lease
    r'\bdevelopment\b',
    r'\bground lease\b',

    # Lease announcements
    r'\bannounces? lease\b',
    r'\bleases?\b',  # Standalone "Lease" or "Leases"
]

# Management and Board Changes keywords
MANAGEMENT_KEYWORDS: List[str] = [
    # C-Suite titles
    r'\bCEO\b',
    r'\bCFO\b',
    r'\bCOO\b',
    r'\bCIO\b',
    r'\bCTO\b',
    r'\bCMO\b',
    r'\bCHRO\b',
    r'\bchief executive\b',
    r'\bchief financial\b',
    r'\bchief operating\b',
    r'\bchief investment\b',
    r'\bpresident\b',
    r'\bvice president\b',
    r'\bEVP\b',
    r'\bSVP\b',
    r'\bmanaging director\b',
    r'\bgeneral counsel\b',

    # Board terms
    r'\bboard of directors\b',
    r'\bboard of trustees\b',
    r'\bdirector\b',
    r'\bindependent director\b',
    r'\bchairman\b',
    r'\bchairwoman\b',
    r'\bchair\b',
    r'\bvice chair\b',
    r'\btrustee\b',

    # Actions
    r'\bappoint(s|ed|ment)?\b',
    r'\belect(s|ed|ion)?\b',
    r'\bhire[sd]?\b',
    r'\bresign(s|ed|ation)?\b',
    r'\bretire[sd]?\b',
    r'\bretirement\b',
    r'\bdepart(s|ed|ure|ing)?\b',
    r'\bpromot(e|es|ed|ion)\b',
    r'\bsucceed(s|ed)?\b',
    r'\bsuccession\b',
    r'\bsuccessor\b',
    r'\btransition(s|ed|ing)?\b',
    r'\binterim\b',
    r'\bnominat(e|es|ed|ion)\b',
    r'\bstep(s|ping)? down\b',
]

# Conference Call keywords
CONFERENCE_CALL_KEYWORDS: List[str] = [
    r'\bconference call\b',
    r'\bearnings call\b',
    r'\binvestor call\b',
    r'\bwebcast\b',
    r'\bschedul(e|es|ed|ing)\b.*\bcall\b',
    r'\brelease date\b',
    r'\bto release\b',
    r'\bto report\b',           # "Company to Report Q1 Results" = scheduling, not actual results
    r'\bannounces? date\b',
]

# Dividend keywords
DIVIDEND_KEYWORDS: List[str] = [
    r'\bdividends?\b',
    r'\bdistributions?\b',
    r'\bdeclare[sd]?\b',
    r'\brecord date\b',
    r'\bpayment date\b',
    r'\bex-dividend\b',
    r'\bpayable\b',
    r'\bquarterly (cash )?distribution\b',
]


def detect_category(title: str) -> str:
    """
    Detect press release category from title.

    Args:
        title: Press release title

    Returns:
        Category string: 'EARNINGS', 'ACQUISITION', 'DIVIDEND', 'FINANCING', or 'OTHER'
    """
    if not title:
        return 'OTHER'

    title_lower = title.lower()

    # Check each category pattern
    for category, patterns in CATEGORY_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, title_lower, re.IGNORECASE):
                return category

    return 'OTHER'


def is_other_announcement(title: str) -> bool:
    """
    Check if a press release is a routine/mundane announcement.

    These are announcements like earnings, dividends, conference calls, etc.
    that should go in the "Other Announcements" section with condensed formatting.

    Args:
        title: Press release title

    Returns:
        True if this is a routine announcement, False if it's a headline
    """
    if not title:
        return False

    title_lower = title.lower()

    # Check against all "Other Announcements" keywords
    for pattern in OTHER_ANNOUNCEMENTS_KEYWORDS:
        if re.search(pattern, title_lower, re.IGNORECASE):
            return True

    return False


def get_section_classification(title: str, item: Any = None) -> str:
    """
    Classify a press release or SEC filing into a newsletter section.

    Order of precedence (most specific first):
    0. SEC filings -> 'financing' (always - they are prospectuses/offerings)
    1. Conference Call keywords -> 'conference_call' (catches all calls including earnings)
    2. Dividend keywords -> 'dividend' (before financing to catch "dividends on preferred stock")
    3. Financing keywords -> 'financing'
    4. Management keywords -> 'management'
    5. Property Transaction keywords -> 'property'
    6. Earnings keywords -> 'earnings'
    7. Other Announcements keywords -> 'other'
    8. Default -> 'headline'

    Args:
        title: Press release title
        item: Optional item (PressReleaseDTO or DisclosureDTO)

    Returns:
        Section string: 'headline', 'financing', 'management', 'property',
                       'earnings', 'conference_call', 'dividend', or 'other'
    """
    # SEC filings are always financings (424B prospectuses, FWP, etc.)
    if item and getattr(item, 'is_sec_filing', False):
        return 'financing'

    if not title:
        return 'headline'

    title_lower = title.lower()

    # Check conference call keywords first (catches all calls including earnings)
    for pattern in CONFERENCE_CALL_KEYWORDS:
        if re.search(pattern, title_lower, re.IGNORECASE):
            return 'conference_call'

    # Check dividend keywords before financing (to catch "dividends on preferred stock")
    for pattern in DIVIDEND_KEYWORDS:
        if re.search(pattern, title_lower, re.IGNORECASE):
            return 'dividend'

    # Check financing keywords (capital markets)
    for pattern in FINANCING_KEYWORDS:
        if re.search(pattern, title_lower, re.IGNORECASE):
            return 'financing'

    # Check management and board changes keywords
    # Exclude company ticker from matching (e.g., "CTO Realty Growth" - CTO is ticker, not Chief Technology Officer)
    title_for_management = title_lower
    if item and hasattr(item, 'ticker') and item.ticker:
        ticker_lower = item.ticker.lower()
        if title_lower.startswith(ticker_lower + ' ') or title_lower.startswith(ticker_lower + ':'):
            title_for_management = title_lower[len(ticker_lower):].lstrip(': ')
    for pattern in MANAGEMENT_KEYWORDS:
        if re.search(pattern, title_for_management, re.IGNORECASE):
            return 'management'

    # Check property transaction keywords
    for pattern in PROPERTY_TRANSACTION_KEYWORDS:
        if re.search(pattern, title_lower, re.IGNORECASE):
            return 'property'

    # Check earnings keywords (earnings releases, results)
    for pattern in EARNINGS_KEYWORDS:
        if re.search(pattern, title_lower, re.IGNORECASE):
            return 'earnings'

    # Check other announcements (routine items)
    for pattern in OTHER_ANNOUNCEMENTS_KEYWORDS:
        if re.search(pattern, title_lower, re.IGNORECASE):
            return 'other'

    # Default to headline
    return 'headline'


class SectionClassifier:
    """
    Classifies press releases into newsletter sections.

    Can be subclassed to customize keyword patterns.
    """

    def __init__(
        self,
        earnings_keywords: List[str] = None,
        financing_keywords: List[str] = None,
        property_keywords: List[str] = None,
        management_keywords: List[str] = None,
        conference_call_keywords: List[str] = None,
        dividend_keywords: List[str] = None,
        other_keywords: List[str] = None
    ):
        """
        Initialize with optional custom keywords.

        Args:
            earnings_keywords: Override earnings keywords
            financing_keywords: Override financing keywords
            property_keywords: Override property transaction keywords
            management_keywords: Override management/board keywords
            conference_call_keywords: Override conference call keywords
            dividend_keywords: Override dividend keywords
            other_keywords: Override other announcement keywords
        """
        self.earnings_keywords = earnings_keywords or EARNINGS_KEYWORDS
        self.financing_keywords = financing_keywords or FINANCING_KEYWORDS
        self.property_keywords = property_keywords or PROPERTY_TRANSACTION_KEYWORDS
        self.management_keywords = management_keywords or MANAGEMENT_KEYWORDS
        self.conference_call_keywords = conference_call_keywords or CONFERENCE_CALL_KEYWORDS
        self.dividend_keywords = dividend_keywords or DIVIDEND_KEYWORDS
        self.other_keywords = other_keywords or OTHER_ANNOUNCEMENTS_KEYWORDS

    def classify(self, title: str, item: Any = None) -> str:
        """
        Classify a press release into a newsletter section.

        Args:
            title: Press release title
            item: Optional item with is_sec_filing attribute

        Returns:
            Section string: 'headline', 'financing', 'management', 'property',
                           'earnings', 'conference_call', 'dividend', or 'other'
        """
        # SEC filings are always financings
        if item and getattr(item, 'is_sec_filing', False):
            return 'financing'

        if not title:
            return 'headline'

        title_lower = title.lower()

        # Check in order of precedence
        for pattern in self.conference_call_keywords:
            if re.search(pattern, title_lower, re.IGNORECASE):
                return 'conference_call'

        # Dividend before financing (to catch "dividends on preferred stock")
        for pattern in self.dividend_keywords:
            if re.search(pattern, title_lower, re.IGNORECASE):
                return 'dividend'

        for pattern in self.financing_keywords:
            if re.search(pattern, title_lower, re.IGNORECASE):
                return 'financing'

        for pattern in self.management_keywords:
            if re.search(pattern, title_lower, re.IGNORECASE):
                return 'management'

        for pattern in self.property_keywords:
            if re.search(pattern, title_lower, re.IGNORECASE):
                return 'property'

        for pattern in self.earnings_keywords:
            if re.search(pattern, title_lower, re.IGNORECASE):
                return 'earnings'

        for pattern in self.other_keywords:
            if re.search(pattern, title_lower, re.IGNORECASE):
                return 'other'

        return 'headline'
