"""
Public Site Configuration

Shared configuration between Flask app (app.reitsheet.co) and
S3 static homepage (reitsheet.co).

SOLID Principle: Single source of truth for all public-facing content.
"""

from config.design_tokens import COLORS, TYPOGRAPHY


# =============================================================================
# BRAND STANDARDS (Single Source of Truth)
# =============================================================================
#
# ALL brand references MUST use these constants. Do not hardcode brand names.
# This ensures consistency across emails, pages, tabs, and all UI.
#
# Usage:
#   from config.site_config import BRAND
#   title = BRAND['name']           # "The Press Release Pipeline"
#   email_from = BRAND['email_from'] # "The Press Release Pipeline <alerts@reitsheet.co>"
#

BRAND = {
    # Primary brand name - use this everywhere
    'name': 'The Press Release Pipeline',

    # Logo alt text (matches visual logo)
    'logo_alt': 'THE REIT SHEET',

    # Email sender display name
    'email_from_name': 'The Press Release Pipeline',
    'email_from_address': 'alerts@reitsheet.co',
    'email_from': 'The Press Release Pipeline <alerts@reitsheet.co>',

    # HTML <title> format: "{page} | The Press Release Pipeline" or just "The Press Release Pipeline"
    'title_suffix': 'The Press Release Pipeline',
    'title_format': '{page} | The Press Release Pipeline',  # Use .format(page='Archive')

    # Contact form subject prefix
    'contact_subject_prefix': 'Press Release Pipeline Contact',

    # Tagline
    'tagline': 'Never miss a REIT release',

    # Legal/copyright name
    'legal_name': 'The Press Release Pipeline',

    # Short reference (for tight spaces)
    'short_name': 'Press Release Pipeline',
}

# =============================================================================
# SITE IDENTITY
# =============================================================================

SITE_CONFIG = {
    'name': BRAND['name'],  # Reference brand standard
    'tagline': BRAND['tagline'],
    'domain': 'reitsheet.co',
    'app_domain': 'app.reitsheet.co',
    'url': 'https://reitsheet.co',
    'logo_url': 'https://reitsheet.co/logo.png',
    'year': 2026,
}


# =============================================================================
# SIGNUP / SUBSCRIPTION
# =============================================================================

SIGNUP_CONFIG = {
    'headline': 'Get the daily brief before the open',
    'description': 'Daily real estate press releases, offerings, partnerships, and corporate news — all in one place.',
    'footer': 'Free. Unsubscribe anytime.',
    'button_text': 'Subscribe',
    'placeholder': 'you@example.com',
    'api_url': 'https://fqlxgkv638.execute-api.us-east-1.amazonaws.com/prod/subscribe',
}


# =============================================================================
# SEO / META
# =============================================================================

META_CONFIG = {
    'description': 'Daily curated press releases from publicly traded REITs. Acquisitions, earnings, dividends, and more. Never miss a REIT release.',
    'keywords': 'REIT, real estate investment trust, press releases, earnings, dividends, acquisitions, commercial real estate',
    'og_image': 'https://reitsheet.co/og-image.jpg',
    'og_image_width': 1200,
    'og_image_height': 630,
    'twitter_card': 'summary_large_image',
}


# =============================================================================
# FOOTER / LEGAL
# =============================================================================

FOOTER_CONFIG = {
    'privacy_url': '/privacy.html',
    'contact_email': 'hello@reitsheet.co',
    'copyright_text': f'© {SITE_CONFIG["year"]} {BRAND["legal_name"]}',
}


# =============================================================================
# PUBLIC PAGE COLORS (for inline email styles)
# =============================================================================

PUBLIC_COLORS = {
    'primary': COLORS['primary'],
    'primary_hover': COLORS['primary_hover'],
    'text': COLORS['text_dark'],
    'text_secondary': COLORS['text_muted'],
    'text_muted': COLORS['text_light'],
    'border': '#ddd',
    'card_bg': '#fafafa',
    'body_bg': '#f9f9f9',
}


# =============================================================================
# PUBLIC PAGE FONTS
# =============================================================================

PUBLIC_FONTS = {
    'body': TYPOGRAPHY['font_body'],
    'heading': TYPOGRAPHY['font_heading'],
}


# =============================================================================
# COMBINED CONFIG FOR TEMPLATES
# =============================================================================

def get_public_config() -> dict:
    """
    Get complete public site configuration for template context.

    Usage in route:
        from config.site_config import get_public_config
        return render_template('public/index.html', config=get_public_config())

    Usage in template:
        {{ config.site.name }}
        {{ config.signup.headline }}
        {{ config.colors.primary }}
    """
    return {
        'brand': BRAND,
        'site': SITE_CONFIG,
        'signup': SIGNUP_CONFIG,
        'meta': META_CONFIG,
        'footer': FOOTER_CONFIG,
        'colors': PUBLIC_COLORS,
        'fonts': PUBLIC_FONTS,
    }


# =============================================================================
# NAVIGATION LINKS (for public pages)
# =============================================================================

PUBLIC_NAVIGATION = [
    {
        'label': 'Front Page',
        'url': 'https://reitsheet.co',
        'is_external': False,
    },
    {
        'label': "Yesterday's Issue",
        'url_template': 'https://reitsheet.co/news/archive/{date}/',
        'is_external': False,
    },
]


def get_navigation_with_date(yesterday_date: str) -> list:
    """
    Get navigation links with date filled in.

    Args:
        yesterday_date: Date string in YYYY-MM-DD format

    Returns:
        List of navigation link dictionaries
    """
    nav = []
    for item in PUBLIC_NAVIGATION:
        link = item.copy()
        if 'url_template' in link:
            link['url'] = link['url_template'].format(date=yesterday_date)
            del link['url_template']
        nav.append(link)
    return nav
