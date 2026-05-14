"""
Publisher HTML Generator - MARCH 16, 2026 TEMPLATE BACKUP

This is a backup of the publisher template before implementing the Headlines/Other Announcements split.

Single-section format:
- All press releases in one list
- Company name + ticker format
- Alphabetically sorted

SOLID Principles:
- Single Responsibility: Generates newsletter HTML only
- Open/Closed: Template can be customized via parameters

Generates clean, mobile-responsive HTML suitable for:
- Beehiiv newsletter editor (paste and publish)
- Email clients (inline styles for compatibility)
"""
import re
import json
import os
from datetime import datetime
from typing import List, Any, Dict
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')

# Legacy path - kept for backwards compatibility but DynamoDB is preferred
STYLE_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    'config',
    'newsletter_styles.json'
)

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
COMPANY_PATTERNS = [
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

# Category detection patterns
CATEGORY_PATTERNS = {
    'EARNINGS': [
        r'\bearnings?\b', r'\bquarterly\b', r'\bQ[1-4]\b', r'\bresults?\b',
        r'\bfinancial results?\b', r'\breports? results?\b', r'\bfiscal\b'
    ],
    'ACQUISITION': [
        r'\bacquir(e|es|ed|ing|ition)\b', r'\bpurchas(e|es|ed|ing)\b',
        r'\bbuy(s|ing)?\b', r'\bmerger?\b', r'\btransaction\b', r'\bacquisition\b'
    ],
    'DIVIDEND': [
        r'\bdividend\b', r'\bdistribution\b', r'\bdeclare(s|d)?\b',
        r'\bpayable\b', r'\bquarterly (cash )?distribution\b'
    ],
    'FINANCING': [
        r'\boffering\b', r'\bnotes?\b', r'\bcredit facility\b',
        r'\bdebt\b', r'\bfinancing\b', r'\bunderwritten\b', r'\bsecondary offering\b'
    ],
}

# Category badge colors
CATEGORY_COLORS = {
    'EARNINGS': '#0066cc',      # Blue
    'ACQUISITION': '#28a745',   # Green
    'DIVIDEND': '#ffc107',      # Yellow/Gold
    'FINANCING': '#6f42c1',     # Purple
    'OTHER': '#6c757d',         # Gray
}


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


def is_all_caps(text: str) -> bool:
    """Check if text is entirely uppercase (ignoring punctuation/numbers)."""
    letters = re.sub(r'[^a-zA-Z]', '', text)
    return letters.isupper() if letters else False


def load_style_config() -> Dict[str, Dict[str, str]]:
    """
    Load style configuration from DynamoDB (preferred) or local file (fallback).

    Priority:
    1. DynamoDB (reitsheet-app-settings table)
    2. Local JSON file (legacy, for development)
    3. Default styles (hardcoded fallback)
    """
    # Default styles
    default_styles = {
        'logo': {'fontFamily': 'Arial, sans-serif', 'fontSize': '24px', 'fontWeight': 'bold', 'color': '#0066cc'},
        'date': {'fontFamily': 'Georgia, serif', 'fontSize': '14px', 'fontStyle': 'italic', 'color': '#666'},
        'company': {'fontFamily': 'Arial, sans-serif', 'fontSize': '11px', 'fontWeight': 'bold', 'color': '#0066cc'},
        'title': {'fontFamily': 'Georgia, serif', 'fontSize': '16px', 'color': '#333'},
        'source': {'fontFamily': 'Georgia, serif', 'fontSize': '11px', 'color': '#999'},
        'footer': {'fontFamily': 'Georgia, serif', 'fontSize': '12px', 'color': '#999'},
    }

    # Try DynamoDB first (production)
    try:
        import boto3
        from botocore.exceptions import ClientError

        table_name = os.environ.get('APP_SETTINGS_TABLE', 'reitsheet-app-settings')
        region = os.environ.get('AWS_REGION', 'us-east-1')
        dynamodb = boto3.resource('dynamodb', region_name=region)
        table = dynamodb.Table(table_name)

        response = table.get_item(Key={'setting_key': 'newsletter_styles'})
        if 'Item' in response and 'styles' in response['Item']:
            return response['Item']['styles']
    except Exception:
        # DynamoDB not available - fall through to file/defaults
        pass

    # Try local file (development/fallback)
    try:
        with open(STYLE_CONFIG_PATH, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    # Return defaults
    return default_styles


def style_dict_to_css(style_dict: Dict[str, str]) -> str:
    """Convert style dictionary to inline CSS string."""
    css_parts = []

    # Map JSON keys to CSS properties
    key_map = {
        'fontFamily': 'font-family',
        'fontSize': 'font-size',
        'fontWeight': 'font-weight',
        'fontStyle': 'font-style',
        'textDecoration': 'text-decoration',
        'color': 'color',
        'letterSpacing': 'letter-spacing',
        'textTransform': 'text-transform',
        'lineHeight': 'line-height',
    }

    for json_key, css_key in key_map.items():
        if json_key in style_dict:
            value = style_dict[json_key]
            # Convert 'bold' to '700', 'normal' to '400' for font-weight
            if json_key == 'fontWeight':
                if value == 'bold':
                    value = '700'
                elif value == 'normal':
                    value = '400'
            # Auto-add 'px' to numeric fontSize values
            elif json_key == 'fontSize':
                if value and value.replace('.', '').replace('-', '').isdigit():
                    value = f'{value}px'
            css_parts.append(f'{css_key}: {value}')

    return '; '.join(css_parts) + ';'


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


class PublisherGenerator:
    """
    Generates Beehiiv-ready HTML from press releases.

    Output format:
    - Logo/masthead (placeholder)
    - Date header
    - List of press releases (company + ticker, title as link)
    - Mobile-responsive styling
    - Georgia font (classic publication serif)
    """

    def __init__(self):
        """Initialize generator."""
        pass

    def _load_styles(self):
        """Load and build styles from config (called on each generation)."""
        # Load fresh style configuration
        style_config = load_style_config()

        # Build inline CSS styles from config
        return {
            'container': 'max-width: 600px; margin: 0 auto; font-family: Georgia, "Times New Roman", Times, serif; color: #1a1a1a;',
            'header': 'text-align: center; padding: 32px 0; border-bottom: 2px solid #e5e5e5;',
            'logo': style_dict_to_css(style_config['logo']),
            'date': style_dict_to_css(style_config['date']) + ' margin-top: 12px;',
            'content': 'padding: 0 16px;',
            'item': 'padding: 20px 0; border-bottom: 1px solid #e8e8e8;',
            'item_last': 'padding: 20px 0;',
            'company_row': 'margin-bottom: 4px;',
            'company': style_dict_to_css(style_config['company']),
            'title': style_dict_to_css(style_config['title']) + ' margin-top: 5px;',
            'title_link': style_dict_to_css(style_config['title']) + ' text-decoration: none; display: block; margin-top: 5px;',
            'source_link': style_dict_to_css(style_config['source']) + ' text-decoration: none; margin-left: 6px;',
            'footer': style_dict_to_css(style_config['footer']) + ' text-align: center; padding: 24px 0; border-top: 1px solid #eee; margin-top: 16px;',
            'footer_link': 'color: #999; text-decoration: none;',
        }

    def _generate_preview_text(self, releases: List[Any]) -> str:
        """
        Generate preview text for email inbox (first 50-100 characters).

        Args:
            releases: List of press releases

        Returns:
            Preview text string
        """
        if not releases:
            return "Today's REIT press releases"

        # Get first 3 company names
        companies = []
        for release in releases[:3]:
            if release.company:
                companies.append(release.company.name)

        if not companies:
            return f"{len(releases)} press release{'s' if len(releases) != 1 else ''}"

        company_list = ', '.join(companies)
        if len(releases) > 3:
            return f"{len(releases)} updates: {company_list}, and more"
        else:
            return f"{len(releases)} update{'s' if len(releases) != 1 else ''}: {company_list}"

    def generate_html(
        self,
        releases: List[Any],
        newsletter_date: datetime.date,
        title_getter=None
    ) -> str:
        """
        Generate newsletter HTML from press releases.

        Args:
            releases: List of press release objects (in display order)
            newsletter_date: Date for the newsletter header
            title_getter: Optional function to get display title (release -> str)

        Returns:
            HTML string ready for Beehiiv
        """
        # Load fresh styles on each generation
        self.STYLES = self._load_styles()

        if title_getter is None:
            title_getter = lambda r: r.newsletter_title or r.title

        # Sort releases alphabetically by company name
        sorted_releases = sorted(
            releases,
            key=lambda r: (r.company.name if r.company else '').lower()
        )

        # Format date
        date_str = newsletter_date.strftime('%A, %B %-d, %Y')

        # Build press release items
        items_html = []
        for i, release in enumerate(sorted_releases):
            is_last = (i == len(sorted_releases) - 1)
            item_html = self._generate_item(release, title_getter, is_last)
            items_html.append(item_html)

        items_content = '\n'.join(items_html)

        # Generate preview text for inbox
        preview_text = self._generate_preview_text(sorted_releases)

        # Assemble full HTML
        html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>The Press Release Pipeline - {date_str}</title>
</head>
<body style="margin: 0; padding: 16px; background: #f9f9f9;">
    <!-- Preview text (hidden but shows in inbox) -->
    <div style="display:none;max-height:0px;overflow:hidden;mso-hide:all;">
        {preview_text}
    </div>

    <div style="{self.STYLES['container']}">
        <!-- Header -->
        <div style="{self.STYLES['header']}">
            <div style="{self.STYLES['logo']}">THE REIT SHEET</div>
            <div style="{self.STYLES['date']}">{date_str}</div>
        </div>

        <!-- Content -->
        <div style="{self.STYLES['content']}">
{items_content}
        </div>

        <!-- Footer -->
        <div style="{self.STYLES['footer']}">
            <div style="margin-bottom: 12px;">
                <a href="https://reitsheet.co" style="{self.STYLES['footer_link']}">reitsheet.co</a>
            </div>
            <div style="font-size: 11px;">
                <a href="{{{{unsubscribe_url}}}}" style="{self.STYLES['footer_link']}">Unsubscribe</a> ·
                <a href="{{{{preferences_url}}}}" style="{self.STYLES['footer_link']}">Email Preferences</a>
            </div>
        </div>
    </div>
</body>
</html>'''

        return html

    def _generate_item(self, release, title_getter, is_last: bool) -> str:
        """
        Generate HTML for a single press release item.

        Args:
            release: Press release object
            title_getter: Function to get display title
            is_last: Whether this is the last item (no bottom border)

        Returns:
            HTML string for the item
        """
        # Get company info
        ticker = release.company.ticker if release.company else release.ticker or 'UNK'
        company_name = release.company.name if release.company else ''

        # Get title and apply smart title case formatting
        raw_title = title_getter(release)
        title = smart_title_case(raw_title)

        # Get URL
        url = release.url or '#'

        # Select style (no border on last item)
        item_style = self.STYLES['item_last'] if is_last else self.STYLES['item']

        # Generate HTML (entire row is clickable)
        return f'''            <div style="{item_style}">
                <div style="{self.STYLES['company_row']}">
                    <a href="{url}" style="{self.STYLES['company']}" target="_blank">{company_name} ({ticker})</a>
                </div>
                <a href="{url}" style="{self.STYLES['title_link']}" target="_blank">{title}</a>
            </div>'''

    def generate_preview_html(
        self,
        releases: List[Any],
        newsletter_date: datetime.date,
        title_getter=None
    ) -> str:
        """
        Generate preview HTML (same as full HTML but for display in iframe).

        Args:
            releases: List of press release objects
            newsletter_date: Date for header
            title_getter: Optional function to get display title

        Returns:
            HTML string for preview
        """
        return self.generate_html(releases, newsletter_date, title_getter)


# =============================================================================
# Factory
# =============================================================================

_generator_instance = None


def get_publisher_generator() -> PublisherGenerator:
    """Get or create publisher generator instance."""
    global _generator_instance
    if _generator_instance is None:
        _generator_instance = PublisherGenerator()
    return _generator_instance
