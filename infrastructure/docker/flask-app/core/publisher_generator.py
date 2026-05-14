"""
Publisher HTML Generator - Generate Beehiiv-ready HTML

SOLID Principles:
- Single Responsibility: Generates newsletter HTML only
- Open/Closed: Template can be customized via parameters

Generates clean, mobile-responsive HTML suitable for:
- Beehiiv newsletter editor (paste and publish)
- Email clients (inline styles for compatibility)
"""
import logging
import re
import json
import os
from datetime import datetime
from typing import List, Any, Dict, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Import design tokens (single source of truth)
from config.design_tokens import COLORS, TYPOGRAPHY, get_color, get_font

# Import title formatting from extracted module
from core.title_formatter import (
    smart_title_case,
    is_all_caps,
    PRESERVE_UPPER,
    KEEP_LOWER,
    COMPANY_PATTERNS,
)
# Import section classification from extracted module
from core.section_classifier import (
    detect_category,
    is_other_announcement,
    get_section_classification,
    CATEGORY_PATTERNS,
    CATEGORY_COLORS,
    EARNINGS_KEYWORDS,
    OTHER_ANNOUNCEMENTS_KEYWORDS,
    FINANCING_KEYWORDS,
    PROPERTY_TRANSACTION_KEYWORDS,
)
# Import centralized section config
from config.section_config import SECTION_DISPLAY_NAMES

ET = ZoneInfo('America/New_York')

# Legacy path - kept for backwards compatibility but DynamoDB is preferred
STYLE_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    'config',
    'newsletter_styles.json'
)

# New unified site config (single source of truth)
SITE_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    'config',
    'site_config.json'
)


def load_style_config() -> Dict[str, Dict[str, str]]:
    """
    Load style configuration from DynamoDB (preferred) or local file (fallback).

    Priority:
    1. DynamoDB (reitsheet-app-settings table)
    2. Local JSON file (legacy, for development)
    3. Default styles (hardcoded fallback)
    """
    # Default styles - use EMAIL_STYLES from design tokens
    default_styles = {
        'logo': {'fontFamily': get_font('ui'), 'fontSize': '24px', 'fontWeight': 'bold', 'color': get_color('primary')},
        'date': {'fontFamily': get_font('body'), 'fontSize': '14px', 'fontStyle': 'italic', 'color': get_color('text_muted')},
        'company': {'fontFamily': get_font('ui'), 'fontSize': '11px', 'fontWeight': 'bold', 'color': get_color('primary')},
        'title': {'fontFamily': get_font('body'), 'fontSize': '16px', 'color': get_color('text')},
        'source': {'fontFamily': get_font('body'), 'fontSize': '11px', 'color': get_color('text_light')},
        'footer': {'fontFamily': get_font('body'), 'fontSize': '12px', 'color': get_color('text_light')},
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
            logger.info("GENERATOR: Loaded styles from DynamoDB")
            return response['Item']['styles']
    except Exception as e:
        # DynamoDB not available - fall through to file/defaults
        logger.debug(f"GENERATOR: DynamoDB styles not available: {e}")
        pass

    # Try local file (development/fallback)
    try:
        with open(STYLE_CONFIG_PATH, 'r') as f:
            logger.info("GENERATOR: Loaded styles from local file")
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    # Return defaults
    logger.info("GENERATOR: Using default styles")
    return default_styles


def load_site_config() -> Dict[str, Any]:
    """
    Load unified site configuration from site_config.json.

    Returns:
        Site configuration dictionary with fonts, colors, signup text, etc.
    """
    try:
        with open(SITE_CONFIG_PATH, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Fallback defaults - use EMAIL_STYLES from design tokens
        return {
            'fonts': {
                'body': get_font('body'),
                'ui': get_font('ui')
            },
            'colors': {
                'primary': get_color('primary'),
                'primary_hover': get_color('primary_hover'),
                'background': get_color('bg'),
                'card_bg': get_color('bg_card'),
                'bg_white': get_color('bg_white'),
                'border': get_color('border'),
                'border_section': get_color('border_section'),
                'border_item': get_color('border_item'),
                'border_footer': get_color('border_footer'),
                'text': get_color('text_dark'),
                'text_secondary': get_color('text_muted'),
                'text_muted': get_color('text_light'),
            },
            'signup': {
                'headline': 'Get the daily brief before the open',
                'description': 'Daily real estate press releases, offerings, partnerships, and corporate news — all in one place.',
                'footer': 'Free. Unsubscribe anytime.',
                'api_url': '/api/subscribe'  # AJAX endpoint (CSRF-exempt)
            },
            'footer': {
                'tagline': 'Never miss a REIT release',
                'contact_email': 'hello@reitsheet.co',
                'privacy_url': 'https://reitsheet.co/privacy.html'
            },
            'site': {
                'name': 'The Press Release Pipeline',
                'url': 'https://reitsheet.co',
                'logo_url': 'https://reitsheet.co/logo.png'
            }
        }


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

        # Build inline CSS styles from config - using design tokens for colors
        primary = get_color('primary')
        text_dark = get_color('text_dark')
        text_color = get_color('text')
        text_muted = get_color('text_muted')
        text_light = get_color('text_light')
        font_body = get_font('body')
        font_ui = get_font('ui')

        # Email-specific border colors (match reitsheet.co website)
        border_section = get_color('border_section')  # #e5e5e5 - section header underlines
        border_item = get_color('border_item')        # #f0f0f0 - item row separators
        border_footer = get_color('border_footer')    # #cccccc - footer separator

        return {
            'container': f'max-width: 600px; margin: 0 auto; font-family: {font_body}; color: {text_dark};',
            'header': 'text-align: center; padding: 32px 0;',
            'logo': style_dict_to_css(style_config['logo']),
            'tagline': f'font-family: {font_body}; font-size: 14px; font-style: italic; color: {text_muted}; margin-top: 4px;',
            'date': style_dict_to_css(style_config['date']) + ' margin-top: 4px;',
            'content': 'padding: 0 16px;',
            'section_header': f'font-family: {font_ui}; font-size: 18px; font-weight: bold; color: {text_color}; margin-top: 24px; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 2px solid {border_section};',
            'item': f'padding: 20px 0; border-bottom: 1px solid {border_item};',
            'item_last': 'padding: 20px 0;',
            'company_row': 'margin-bottom: 4px;',
            'company': style_dict_to_css(style_config['company']),
            'title': style_dict_to_css(style_config['title']) + ' margin-top: 5px;',
            'title_link': style_dict_to_css(style_config['title']) + ' text-decoration: none; display: block; margin-top: 5px;',
            'source_link': style_dict_to_css(style_config['source']) + ' text-decoration: none; margin-left: 6px;',
            # Other Announcements styles (condensed format)
            'other_item': f'padding: 8px 0; border-bottom: 1px solid {border_item};',
            'other_item_last': 'padding: 8px 0;',
            'other_ticker': f'font-family: {font_ui}; font-size: 11px; font-weight: bold; color: {primary}; text-decoration: none;',
            'other_title_link': f'font-family: {font_body}; font-size: 13px; color: {text_muted}; text-decoration: none; display: inline;',
            'footer': style_dict_to_css(style_config['footer']) + f' text-align: center; padding: 24px 0; margin-top: 16px;',
            'footer_link': f'color: {text_light}; text-decoration: none;',
            'footer_separator': f'color: {border_footer}; margin: 0 8px;',
            # Headlines - matches public.css .section-header-primary (18px, 3px blue border)
            'headlines_section_header': f'font-family: {font_ui}; font-size: 18px; font-weight: bold; color: {text_dark}; margin-top: 24px; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 3px solid {primary};',
            'headline_item': f'padding: 16px 0; border-bottom: 1px solid {border_item};',
            'headline_item_last': f'padding: 16px 0 24px 0; border-bottom: 3px solid {primary};',
            'headline_title_link': f'font-family: {font_body}; font-size: 16px; color: {text_color}; text-decoration: none; display: block; margin-top: 5px;',
            # Secondary sections - DEMOTED styling (smaller, lighter)
            'secondary_section_header': f'font-family: {font_ui}; font-size: 14px; font-weight: bold; color: {text_muted}; margin-top: 24px; margin-bottom: 12px; padding-bottom: 6px; border-bottom: 1px solid {border_section};',
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

    def _generate_archive_banner(self) -> str:
        """
        Generate archive banner for archived newsletters.

        Returns:
            HTML string for the archive banner
        """
        banner_style = (
            f'background-color: {get_color("bg")}; '
            'padding: 10px 16px; '
            'text-align: center; '
            f'font-family: {get_font("ui")}; '
            'font-size: 13px; '
            f'color: {get_color("text_muted")}; '
            f'border-bottom: 1px solid {get_color("border")};'
        )
        link_style = f'color: {get_color("primary")}; text-decoration: none;'

        return f'''        <div style="{banner_style}">
            You are viewing an archived version ·
            <a href="https://reitsheet.co" style="{link_style}">View today's issue</a>
        </div>'''

    def _generate_archive_nav(self, prior_date: Optional[str], next_date: Optional[str]) -> str:
        """
        Generate prev/next navigation for archive pages.

        Args:
            prior_date: Prior newsletter date (YYYY-MM-DD) or None
            next_date: Next newsletter date (YYYY-MM-DD) or None

        Returns:
            HTML string for archive navigation (above Headlines)
        """
        from datetime import datetime

        link_style = f'color: {get_color("primary")}; text-decoration: none; font-family: {get_font("ui")}; font-size: 13px;'
        nav_style = 'display: flex; justify-content: space-between; padding: 16px 0 8px 0;'

        left_link = ''
        right_link = ''

        if prior_date:
            prior_dt = datetime.strptime(prior_date, '%Y-%m-%d').date()
            prior_label = prior_dt.strftime('%b %-d')
            left_link = f'<a href="https://reitsheet.co/news/archive/{prior_date}/" style="{link_style}">← Prior Issue ({prior_label})</a>'

        if next_date:
            next_dt = datetime.strptime(next_date, '%Y-%m-%d').date()
            next_label = next_dt.strftime('%b %-d')
            right_link = f'<a href="https://reitsheet.co/news/archive/{next_date}/" style="{link_style}">Next Issue ({next_label}) →</a>'

        # If no links, return empty
        if not left_link and not right_link:
            return ''

        return f'''            <div style="{nav_style}">
                <div>{left_link}</div>
                <div>{right_link}</div>
            </div>'''

    def _generate_navigation(self, newsletter_date: datetime.date, prior_date: Optional[str]) -> str:
        """
        Generate navigation links for newsletter with popup signup.

        Args:
            newsletter_date: Current newsletter date
            prior_date: Prior newsletter date (YYYY-MM-DD) or None

        Returns:
            HTML string for navigation
        """
        config = load_site_config()
        colors = config['colors']
        fonts = config['fonts']
        signup = config['signup']
        site = config['site']

        nav_style = f'text-align: center; padding: 12px 0; font-family: {fonts["ui"]}; font-size: 13px;'
        link_style = f'color: {colors["primary"]}; text-decoration: none; margin: 0 12px;'

        # Build prior issue link if available
        prior_link = ''
        if prior_date:
            from datetime import datetime as dt
            prior_dt = dt.strptime(prior_date, '%Y-%m-%d').date()
            day_diff = (newsletter_date - prior_dt).days
            if day_diff == 1:
                prior_label = f"Yesterday's Issue ({prior_dt.strftime('%b %-d')})"
            else:
                prior_label = f"Last Issue ({prior_dt.strftime('%b %-d')})"
            prior_link = f' | <a href="{site["url"]}/news/archive/{prior_date}/" style="{link_style}">{prior_label}</a>'

        # Popup signup HTML
        popup_html = f'''
            <span class="signup-wrapper" style="margin: 0 12px;">
                <input type="checkbox" id="nav-signup-toggle" class="signup-toggle">
                <label for="nav-signup-toggle" class="signup-trigger">{signup.get('nav_cta', 'Get the Daily Sheet')}</label>
                <div class="signup-popup">
                    <label for="nav-signup-toggle" class="signup-close-btn">&times;</label>
                    <div style="font-family: {fonts['body']}; font-size: 14px; color: {colors['text']}; margin-bottom: 12px; padding-right: 16px;">Subscribe to {site['name']}</div>
                    <form action="{signup['api_url']}" method="POST" class="popup-form" data-ajax="true" novalidate>
                        <input type="text" name="website" style="display:none;" tabindex="-1" autocomplete="off" aria-hidden="true">
                        <input type="text" name="email" placeholder="you@example.com" required>
                        <button type="submit">Subscribe</button>
                    </form>
                    <div style="margin-top: 10px; font-family: {fonts['body']}; font-size: 11px; color: {colors['text_secondary']}; text-align: center;">
                        {signup['footer']}
                    </div>
                    <div class="signup-message" style="display: none;"></div>
                </div>
            </span>'''

        return f'''        <div style="{nav_style}">
            <a href="{site['url']}" style="{link_style}">Front Page</a>{prior_link} |{popup_html}
        </div>'''

    def _generate_archive_signup_nav(self) -> str:
        """
        Generate signup-only navigation for archive pages (no Front Page link).

        Returns:
            HTML string for archive navigation with signup popup
        """
        config = load_site_config()
        colors = config['colors']
        fonts = config['fonts']
        signup = config['signup']
        site = config['site']

        nav_style = f'text-align: center; padding: 12px 0; font-family: {fonts["ui"]}; font-size: 13px;'

        return f'''        <div style="{nav_style}">
            <span class="signup-wrapper">
                <input type="checkbox" id="nav-signup-toggle" class="signup-toggle">
                <label for="nav-signup-toggle" class="signup-trigger">{signup.get('nav_cta', 'Get the Daily Sheet')}</label>
                <div class="signup-popup">
                    <label for="nav-signup-toggle" class="signup-close-btn">&times;</label>
                    <div style="font-family: {fonts['body']}; font-size: 14px; color: {colors['text']}; margin-bottom: 12px; padding-right: 16px;">Subscribe to {site['name']}</div>
                    <form action="{signup['api_url']}" method="POST" class="popup-form" data-ajax="true" novalidate>
                        <input type="text" name="website" style="display:none;" tabindex="-1" autocomplete="off" aria-hidden="true">
                        <input type="text" name="email" placeholder="you@example.com" required>
                        <button type="submit">Subscribe</button>
                    </form>
                    <div style="margin-top: 10px; font-family: {fonts['body']}; font-size: 11px; color: {colors['text_secondary']}; text-align: center;">
                        {signup['footer']}
                    </div>
                    <div class="signup-message" style="display: none;"></div>
                </div>
            </span>
        </div>'''

    def _generate_signup_section(self) -> str:
        """
        Generate signup form section for web pages.
        No JavaScript - uses HTML form POST with redirect.

        Returns:
            HTML string for signup form
        """
        config = load_site_config()
        fonts = config['fonts']
        colors = config['colors']
        signup = config['signup']

        return f'''        <!-- Signup Section -->
        <div id="signup" class="signup-box" style="border: 1px solid {colors['border']}; border-radius: 6px; margin-top: 32px; padding: 20px 24px; text-align: center; background: {colors['card_bg']};">
            <div style="font-family: {fonts['body']}; font-size: 17px; color: {colors['text']}; margin-bottom: 6px;">
                {signup['headline']}
            </div>
            <div style="font-family: {fonts['body']}; font-size: 13px; color: {colors['text_secondary']}; margin-bottom: 16px; line-height: 1.5;">
                {signup['description']}
            </div>
            <form action="{signup['api_url']}" method="POST" class="signup-form" data-ajax="true" style="display: flex; gap: 8px; justify-content: center; flex-wrap: wrap; max-width: 400px; margin: 0 auto;" novalidate>
                <input type="text" name="website" style="display:none;" tabindex="-1" autocomplete="off" aria-hidden="true">
                <input type="text" name="email" placeholder="you@example.com" required
                    style="flex: 1; min-width: 200px; padding: 10px 14px; font-size: 14px; font-family: {fonts['body']}; border: 1px solid {colors['border']}; border-radius: 4px;">
                <button type="submit"
                    style="padding: 10px 20px; background: {colors['primary']}; color: white; border: none; font-size: 14px; font-family: {fonts['body']}; cursor: pointer; border-radius: 4px;">
                    Subscribe
                </button>
            </form>
            <div style="font-family: {fonts['body']}; font-size: 11px; color: {colors['text_muted']}; margin-top: 12px;">
                {signup['footer']}
            </div>
            <div class="signup-message" style="display: none; margin-top: 12px; font-family: {fonts['body']}; font-size: 14px;"></div>
        </div>
'''

    def _generate_email_footer(self) -> str:
        """
        Generate footer for email newsletters.

        Email footer has:
        - Tagline (Never miss a REIT release)
        - Site link (reitsheet.co)
        - Privacy Policy | Unsubscribe links
        - Physical address (CAN-SPAM compliance)

        Uses hardcoded URLs to avoid relative path issues in emails.
        """
        from config.company import COMPANY_ADDRESS

        text_muted = get_color('text_muted')
        text_light = get_color('text_light')
        primary = get_color('primary')
        border_footer = get_color('border_footer')  # #cccccc - matches reitsheet.co
        font_body = get_font('body')
        font_ui = get_font('ui')

        return f'''
        <!-- Footer -->
        <div style="text-align: center; padding: 24px 0; margin-top: 16px;">
            <div style="font-family: {font_body}; font-size: 14px; font-style: italic; color: {text_muted};">Never miss a REIT release</div>
            <div style="margin-top: 8px;">
                <a href="https://reitsheet.co" style="font-family: {font_ui}; font-size: 12px; color: {primary}; text-decoration: none;">reitsheet.co</a>
            </div>
            <div style="margin-top: 12px; font-family: {font_ui}; font-size: 12px;">
                <a href="https://reitsheet.co/privacy.html" style="color: {text_light}; text-decoration: none;">Privacy Policy</a>
                <span style="color: {border_footer}; margin: 0 8px;">|</span>
                <a href="{{{{unsubscribe_url}}}}" style="color: {text_light}; text-decoration: none;">Unsubscribe</a>
            </div>
            <div style="margin-top: 16px; font-size: 11px; color: {text_light};">{COMPANY_ADDRESS}</div>
        </div>'''

    def generate_html(
        self,
        releases: List[Any],
        newsletter_date: datetime.date,
        prior_date: Optional[str] = None,
        next_date: Optional[str] = None,
        title_getter=None,
        section_getter=None,
        is_archive: bool = False,
        show_signup: bool = False
    ) -> str:
        """
        Generate newsletter HTML from press releases.

        Args:
            releases: List of press release objects (in display order)
            newsletter_date: Date for the newsletter header
            prior_date: Optional prior newsletter date (YYYY-MM-DD) for "Yesterday's Issue" link
            next_date: Optional next newsletter date (YYYY-MM-DD) for archive navigation
            title_getter: Optional function to get display title (release -> str)
            section_getter: Optional function to get section (release -> 'headline' or 'other')
                           If not provided, uses is_other_announcement() on title
            is_archive: If True, adds archive banner and prev/next navigation

        Returns:
            HTML string ready for Beehiiv
        """
        logger.info(f"GENERATOR: generate_html | date={newsletter_date} | releases={len(releases)} | is_archive={is_archive}")

        # Load fresh styles and config on each generation
        self.STYLES = self._load_styles()
        config = load_site_config()

        if title_getter is None:
            # Use centralized title priority from title_utils
            from core.title_utils import get_display_title
            title_getter = get_display_title

        if section_getter is None:
            # Default: use get_section_classification on title
            # Pass item so SEC filings auto-classify as 'financing'
            def section_getter(r):
                title = title_getter(r)
                return get_section_classification(title, item=r)

        # Split releases into 8 sections
        headlines = []
        financings = []
        management_changes = []
        property_transactions = []
        earnings = []
        conference_calls = []
        dividends = []
        other_announcements = []

        for release in releases:
            section = section_getter(release)
            if section == 'financing':
                financings.append(release)
            elif section == 'management':
                management_changes.append(release)
            elif section == 'property':
                property_transactions.append(release)
            elif section == 'earnings':
                earnings.append(release)
            elif section == 'conference_call':
                conference_calls.append(release)
            elif section == 'dividend':
                dividends.append(release)
            elif section == 'other':
                other_announcements.append(release)
            else:
                headlines.append(release)

        # Sort each section alphabetically by company name (with ticker fallback)
        # Handle both PressReleaseDTO (has .company) and DisclosureDTO (has .issuer_name)
        def sort_key(r):
            if hasattr(r, 'company') and r.company and hasattr(r.company, 'name') and r.company.name:
                return r.company.name.lower()
            elif hasattr(r, 'issuer_name') and r.issuer_name:
                return r.issuer_name.lower()
            return (r.ticker or '').lower()

        headlines = sorted(headlines, key=sort_key)
        financings = sorted(financings, key=sort_key)
        management_changes = sorted(management_changes, key=sort_key)
        property_transactions = sorted(property_transactions, key=sort_key)
        earnings = sorted(earnings, key=sort_key)
        conference_calls = sorted(conference_calls, key=sort_key)
        dividends = sorted(dividends, key=sort_key)
        other_announcements = sorted(other_announcements, key=sort_key)

        # Format date
        date_str = newsletter_date.strftime('%A, %B %-d, %Y')

        # Build Headlines section (premium styling)
        headlines_html = []
        headlines_html.append(f'            <div style="{self.STYLES["headlines_section_header"]}">{SECTION_DISPLAY_NAMES["headline"]}</div>')

        if headlines:
            for i, release in enumerate(headlines):
                is_last = (i == len(headlines) - 1)
                item_html = self._generate_headline_item(release, title_getter, is_last)
                headlines_html.append(item_html)
        else:
            # No headlines - show quiet day message
            quiet_day_message = f'            <div style="padding: 12px 0; font-style: italic; color: {config["colors"]["text_muted"]};">It was a quiet day in real estate. No major announcements.</div>'
            headlines_html.append(quiet_day_message)

        # Build Financings and Offerings section (secondary styling)
        # Includes both press releases and SEC filings (424B, FWP prospectuses)
        financings_html = []
        if financings:
            financings_html.append(f'            <div style="{self.STYLES["secondary_section_header"]}">{SECTION_DISPLAY_NAMES["financing"]}</div>')
            for i, release in enumerate(financings):
                is_last = (i == len(financings) - 1)
                # Use SEC-specific renderer for SEC filings
                if getattr(release, 'is_sec_filing', False):
                    item_html = self._generate_sec_item(release, title_getter, is_last)
                else:
                    item_html = self._generate_other_item(release, title_getter, is_last)
                financings_html.append(item_html)

        # Build Management and Board Changes section (secondary styling)
        management_html = []
        if management_changes:
            management_html.append(f'            <div style="{self.STYLES["secondary_section_header"]}">{SECTION_DISPLAY_NAMES["management"]}</div>')
            for i, release in enumerate(management_changes):
                is_last = (i == len(management_changes) - 1)
                item_html = self._generate_other_item(release, title_getter, is_last)
                management_html.append(item_html)

        # Build Property Transactions section (secondary styling)
        property_html = []
        if property_transactions:
            property_html.append(f'            <div style="{self.STYLES["secondary_section_header"]}">{SECTION_DISPLAY_NAMES["property"]}</div>')
            for i, release in enumerate(property_transactions):
                is_last = (i == len(property_transactions) - 1)
                item_html = self._generate_other_item(release, title_getter, is_last)
                property_html.append(item_html)

        # Build Earnings section (secondary styling)
        earnings_html = []
        if earnings:
            earnings_html.append(f'            <div style="{self.STYLES["secondary_section_header"]}">{SECTION_DISPLAY_NAMES["earnings"]}</div>')
            for i, release in enumerate(earnings):
                is_last = (i == len(earnings) - 1)
                item_html = self._generate_other_item(release, title_getter, is_last)
                earnings_html.append(item_html)

        # Build Conference Call Scheduling section (secondary styling)
        conference_html = []
        if conference_calls:
            conference_html.append(f'            <div style="{self.STYLES["secondary_section_header"]}">{SECTION_DISPLAY_NAMES["conference_call"]}</div>')
            for i, release in enumerate(conference_calls):
                is_last = (i == len(conference_calls) - 1)
                item_html = self._generate_other_item(release, title_getter, is_last)
                conference_html.append(item_html)

        # Build Dividends section (secondary styling)
        dividends_html = []
        if dividends:
            dividends_html.append(f'            <div style="{self.STYLES["secondary_section_header"]}">{SECTION_DISPLAY_NAMES["dividend"]}</div>')
            for i, release in enumerate(dividends):
                is_last = (i == len(dividends) - 1)
                item_html = self._generate_other_item(release, title_getter, is_last)
                dividends_html.append(item_html)

        # Build Other Announcements section (secondary styling)
        other_html = []
        if other_announcements:
            other_html.append(f'            <div style="{self.STYLES["secondary_section_header"]}">{SECTION_DISPLAY_NAMES["other"]}</div>')
            for i, release in enumerate(other_announcements):
                is_last = (i == len(other_announcements) - 1)
                item_html = self._generate_other_item(release, title_getter, is_last)
                other_html.append(item_html)

        # Generate preview text for inbox (use headlines for preview)
        preview_text = self._generate_preview_text(headlines if headlines else other_announcements)

        # Generate archive banner (only for archived issues)
        archive_banner = self._generate_archive_banner() if is_archive else ''

        # Generate navigation HTML (archives get signup-only, homepage gets full nav, emails get none)
        if not show_signup:
            # Email mode: no navigation
            nav_html = ''
        elif is_archive:
            nav_html = self._generate_archive_signup_nav()
        else:
            nav_html = self._generate_navigation(newsletter_date, prior_date)

        # Generate signup section (only for web pages, not emails)
        signup_section = self._generate_signup_section() if show_signup else ''

        # Generate footer (different for emails vs web pages)
        if show_signup:
            # Web page footer (with Contact Us, no Unsubscribe)
            footer_html = f'''
        <!-- Footer -->
        <div style="text-align: center; padding: 24px 0; margin-top: 16px;">
            <div style="font-family: {config['fonts']['body']}; font-size: 14px; font-style: italic; color: {config['colors']['text_secondary']};">{config['footer']['tagline']}</div>
            <div style="margin-top: 12px; font-family: {config['fonts']['ui']}; font-size: 12px;">
                <a href="{config['footer']['privacy_url']}" style="color: {config['colors']['text_muted']}; text-decoration: none;">Privacy Policy</a>
                <span style="color: {config['colors']['border_footer']}; margin: 0 8px;">|</span>
                <a href="mailto:{config['footer']['contact_email']}" style="color: {config['colors']['text_muted']}; text-decoration: none;">Contact Us</a>
            </div>
        </div>'''
        else:
            # Email footer (with reitsheet.co link, Unsubscribe, address)
            footer_html = self._generate_email_footer()

        # Generate archive prev/next navigation (only for archives, goes above Headlines)
        archive_nav = self._generate_archive_nav(prior_date, next_date) if is_archive else ''

        # Combine sections (archive nav goes before Headlines)
        # Order: Headlines -> Financings -> Management -> Property -> Earnings -> Conference Call -> Dividends -> Other
        all_content = []
        if archive_nav:
            all_content.append(archive_nav)
        all_content.extend(headlines_html)
        all_content.extend(financings_html)
        all_content.extend(management_html)
        all_content.extend(property_html)
        all_content.extend(earnings_html)
        all_content.extend(conference_html)
        all_content.extend(dividends_html)
        all_content.extend(other_html)
        items_content = '\n'.join(all_content)

        # Assemble full HTML
        html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>The Press Release Pipeline - Never Miss a REIT Release</title>

    <!-- SEO Meta Tags -->
    <meta name="description" content="Daily curated press releases from publicly traded REITs. Acquisitions, earnings, dividends, and more. Never miss a REIT release.">
    <meta name="keywords" content="REIT, real estate investment trust, press releases, earnings, dividends, acquisitions, commercial real estate">
    <meta name="author" content="The Press Release Pipeline">
    <meta name="robots" content="index, follow">
    <link rel="canonical" href="https://reitsheet.co">

    <!-- Open Graph for iMessage, WhatsApp, Slack, Facebook -->
    <meta property="og:title" content="The Press Release Pipeline - Never Miss a REIT Release">
    <meta property="og:description" content="Never miss a REIT release">
    <meta property="og:type" content="website">
    <meta property="og:url" content="https://reitsheet.co">
    <meta property="og:site_name" content="The Press Release Pipeline">
    <meta property="og:locale" content="en_US">
    <meta property="og:image" content="https://reitsheet.co/og-image.jpg">
    <meta property="og:image:width" content="1200">
    <meta property="og:image:height" content="630">
    <meta property="og:image:alt" content="The Press Release Pipeline logo">

    <!-- Twitter Card -->
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="The Press Release Pipeline - Never Miss a REIT Release">
    <meta name="twitter:description" content="Never miss a REIT release">
    <meta name="twitter:image" content="https://reitsheet.co/og-image.jpg">

    <!-- Structured Data for Google -->
    <script type="application/ld+json">
    {{
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": "The Press Release Pipeline",
        "url": "https://reitsheet.co",
        "description": "Daily curated press releases from publicly traded REITs"
    }}
    </script>
    <style>
    /* Signup popup - click/tap to toggle */
    .signup-wrapper {{ position: relative; display: inline-block; }}
    .signup-toggle {{ display: none; }}
    .signup-trigger {{ color: {config['colors']['primary']}; cursor: pointer; border-bottom: 1px dashed {config['colors']['primary']}; }}
    .signup-popup {{
        position: absolute; top: 100%; left: 50%; transform: translateX(-50%);
        margin-top: 10px; background: {config['colors']['bg_white']}; border: 1px solid {config['colors']['border']};
        border-radius: 6px; box-shadow: 0 4px 16px rgba(0,0,0,0.15);
        padding: 16px 20px; width: 280px; display: none; z-index: 100;
    }}
    .signup-popup::before {{
        content: ''; position: absolute; top: -8px; left: 50%; transform: translateX(-50%);
        border-left: 8px solid transparent; border-right: 8px solid transparent;
        border-bottom: 8px solid {config['colors']['border']};
    }}
    .signup-popup::after {{
        content: ''; position: absolute; top: -7px; left: 50%; transform: translateX(-50%);
        border-left: 7px solid transparent; border-right: 7px solid transparent;
        border-bottom: 7px solid {config['colors']['bg_white']};
    }}
    .signup-toggle:checked ~ .signup-popup {{ display: block; }}
    .signup-close-btn {{ position: absolute; top: 6px; right: 8px; font-size: 20px; color: {config['colors']['text_muted']}; cursor: pointer; line-height: 1; }}
    .signup-close-btn:hover {{ color: {config['colors']['text']}; }}
    .popup-form input[type="text"] {{
        width: 100%; padding: 10px 12px; font-size: 14px;
        font-family: {config['fonts']['body']}; border: 1px solid {config['colors']['border']};
        box-sizing: border-box; margin-bottom: 8px; border-radius: 4px;
    }}
    .popup-form button {{
        width: 100%; padding: 10px 16px; background: {config['colors']['primary']};
        color: white; border: none; font-size: 14px;
        font-family: {config['fonts']['body']}; cursor: pointer; border-radius: 4px;
    }}
    .popup-form button:hover {{ background: {config['colors']['primary_hover']}; }}
    </style>
</head>
<body style="margin: 0; padding: 16px; background: {config['colors']['background']};">
    <!-- Preview text (hidden but shows in inbox) -->
    <div style="display:none;max-height:0px;overflow:hidden;mso-hide:all;">
        {preview_text}
    </div>

    <div style="{self.STYLES['container']}">
        <!-- Header -->
        <div style="{self.STYLES['header']}">
            <a href="https://reitsheet.co" style="text-decoration: none;">
                <img src="https://reitsheet.co/logo.png" alt="THE REIT SHEET" style="max-width: 100%; width: 400px; height: auto; cursor: pointer;">
            </a>
            <div style="{self.STYLES['date']}">{date_str}</div>
        </div>

        <!-- Archive Banner -->
{archive_banner}

        <!-- Navigation -->
{nav_html}

        <!-- Content -->
        <div style="{self.STYLES['content']}">
{items_content}
        </div>

{signup_section}

{footer_html}
    </div>
    <script>
    (function() {{
        var emailRegex = /^[a-z0-9._%+-]+@[a-z0-9.-]+\\.[a-z]{{2,}}$/i;
        var dangerousChars = /[<>"'();\\\\`\\n\\r\\x00]/;
        function validateEmail(email) {{
            email = email.toLowerCase().trim();
            if (!email || email.length > 254) return false;
            if (dangerousChars.test(email)) return false;
            if ((email.match(/@/g) || []).length !== 1) return false;
            return emailRegex.test(email);
        }}
        function showMessage(container, message, isError) {{
            var msgDiv = container.querySelector('.signup-message');
            if (msgDiv) {{
                msgDiv.textContent = message;
                msgDiv.style.display = 'block';
                msgDiv.style.color = isError ? '{get_color("danger")}' : '{get_color("success")}';
            }}
        }}
        function showError(input, message) {{
            var existing = input.parentNode.querySelector('.email-error');
            if (existing) existing.remove();
            var error = document.createElement('div');
            error.className = 'email-error';
            error.style.cssText = 'color: {get_color("danger")}; font-size: 12px; margin-top: 6px;';
            error.textContent = message;
            input.parentNode.appendChild(error);
            input.style.borderColor = '{get_color("danger")}';
        }}
        function clearError(input) {{
            var existing = input.parentNode.querySelector('.email-error');
            if (existing) existing.remove();
            input.style.borderColor = '';
        }}
        document.querySelectorAll('form[action*="subscribe"]').forEach(function(form) {{
            var isAjax = form.dataset.ajax === 'true';
            var container = form.closest('.signup-box') || form.closest('.signup-popup');
            form.addEventListener('submit', function(e) {{
                var input = form.querySelector('input[name="email"]');
                var btn = form.querySelector('button[type="submit"]');
                var originalText = btn ? btn.textContent : 'Subscribe';
                if (!validateEmail(input.value)) {{
                    e.preventDefault();
                    showError(input, 'Please enter a valid email address.');
                    return false;
                }}
                clearError(input);
                if (isAjax) {{
                    e.preventDefault();
                    if (btn) {{ btn.disabled = true; btn.textContent = 'Subscribing...'; }}
                    var honeypot = form.querySelector('input[name="website"]');
                    var body = {{ email: input.value.trim() }};
                    if (honeypot) body.website = honeypot.value;
                    fetch(form.action, {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify(body)
                    }})
                    .then(function(r) {{ return r.json(); }})
                    .then(function(data) {{
                        if (data.success) {{
                            form.style.display = 'none';
                            showMessage(container, data.message || 'Check your email to confirm.', false);
                        }} else {{
                            showMessage(container, data.error || 'An error occurred. Please try again.', true);
                            if (btn) {{ btn.disabled = false; btn.textContent = originalText; }}
                        }}
                    }})
                    .catch(function() {{
                        showMessage(container, 'An error occurred. Please try again.', true);
                        if (btn) {{ btn.disabled = false; btn.textContent = originalText; }}
                    }});
                }}
            }});
            var input = form.querySelector('input[name="email"]');
            if (input) input.addEventListener('input', function() {{ clearError(input); }});
        }});
    }})();
    </script>
</body>
</html>'''

        return html

    def _make_link(self, url: str, text: str, style: str, check_paywall: bool = False) -> str:
        """Generate <a> tag with consistent behavior (same-tab navigation).

        Centralizes link generation for easy behavior changes.
        To open in new tab: add target="_blank" rel="noopener" to return value.
        """
        if check_paywall:
            from core.paywall_utils import get_access_indicator
            indicator = get_access_indicator(url)
            if indicator:
                # Always use 13px (non-headline size) so it's subtle even in 16px headlines
                text = f'{text} <span style="text-decoration: underline; font-size: 13px;">{indicator}</span>'
        return f'<a href="{url}" style="{style}">{text}</a>'

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
        company_link = self._make_link(url, f'{company_name} ({ticker})', self.STYLES['company'])
        title_link = self._make_link(url, title, self.STYLES['title_link'], check_paywall=True)
        return f'''            <div style="{item_style}">
                <div style="{self.STYLES['company_row']}">
                    {company_link}
                </div>
                {title_link}
            </div>'''

    def _generate_headline_item(self, release, title_getter, is_last: bool) -> str:
        """
        Generate HTML for a headline item with premium styling.

        Features blue title, left border accent, and subtle background.

        Args:
            release: Press release object
            title_getter: Function to get display title
            is_last: Whether this is the last item (no bottom border)

        Returns:
            HTML string for the headline item
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
        item_style = self.STYLES['headline_item_last'] if is_last else self.STYLES['headline_item']

        # Generate HTML with blue title
        company_link = self._make_link(url, f'{company_name} ({ticker})', self.STYLES['company'])
        title_link = self._make_link(url, title, self.STYLES['headline_title_link'], check_paywall=True)
        return f'''            <div style="{item_style}">
                <div style="{self.STYLES['company_row']}">
                    {company_link}
                </div>
                {title_link}
            </div>'''

    def _generate_other_item(self, release, title_getter, is_last: bool) -> str:
        """
        Generate HTML for a single "Other Announcements" item (condensed format).

        Format: TICKER: Title (smaller font, no company name)

        Args:
            release: Press release object
            title_getter: Function to get display title
            is_last: Whether this is the last item (no bottom border)

        Returns:
            HTML string for the item
        """
        # Get ticker
        ticker = release.company.ticker if release.company else release.ticker or 'UNK'

        # Get title and apply smart title case formatting
        raw_title = title_getter(release)
        title = smart_title_case(raw_title)

        # Get URL
        url = release.url or '#'

        # Select style (no border on last item)
        item_style = self.STYLES['other_item_last'] if is_last else self.STYLES['other_item']

        # Generate condensed HTML: TICKER: Title
        ticker_link = self._make_link(url, ticker, self.STYLES['other_ticker'])
        title_link = self._make_link(url, title, self.STYLES['other_title_link'], check_paywall=True)
        return f'''            <div style="{item_style}">
                {ticker_link}: {title_link}
            </div>'''

    def _generate_sec_item(self, disclosure, title_getter, is_last: bool) -> str:
        """
        Generate HTML for an SEC filing item in the Financings section.

        Format: TICKER [SEC]: Title (links to EDGAR)

        Args:
            disclosure: DisclosureDTO object
            title_getter: Function to get display title
            is_last: Whether this is the last item (no bottom border)

        Returns:
            HTML string for the SEC filing item
        """
        # Get ticker
        ticker = disclosure.ticker or 'UNK'

        # Get title - use ai_summary_title or form type
        raw_title = disclosure.display_title if hasattr(disclosure, 'display_title') else f'{ticker} {disclosure.form_type} Filing'
        title = smart_title_case(raw_title)

        # Get SEC URL (EDGAR link)
        url = disclosure.sec_url if hasattr(disclosure, 'sec_url') else disclosure.filing_url

        # Select style (no border on last item)
        item_style = self.STYLES['other_item_last'] if is_last else self.STYLES['other_item']

        # Generate condensed HTML: TICKER: Title (same format as other items)
        ticker_link = self._make_link(url, ticker, self.STYLES['other_ticker'])
        title_link = self._make_link(url, title, self.STYLES['other_title_link'])
        return f'''            <div style="{item_style}">
                {ticker_link}: {title_link}
            </div>'''

    def generate_preview_html(
        self,
        releases: List[Any],
        newsletter_date: datetime.date,
        title_getter=None,
        section_getter=None
    ) -> str:
        """
        Generate preview HTML for email newsletter.

        Shows exactly what the email will look like:
        - No navigation (Front Page | Yesterday's Issue)
        - No signup box
        - Has unsubscribe link and address in footer

        Args:
            releases: List of press release objects
            newsletter_date: Date for header
            title_getter: Optional function to get display title
            section_getter: Optional function to get section

        Returns:
            HTML string for email preview
        """
        logger.info(f"GENERATOR: generate_preview_html | date={newsletter_date} | releases={len(releases)}")
        # Email mode: no navigation, no signup
        return self.generate_html(
            releases,
            newsletter_date,
            prior_date=None,
            title_getter=title_getter,
            section_getter=section_getter,
            show_signup=False
        )


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
