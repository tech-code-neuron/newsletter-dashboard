"""
Public Site Configuration

Shared configuration between Flask app (app.your-domain.com) and
S3 static homepage (your-domain.com).

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
#   email_from = BRAND['email_from'] # "The Press Release Pipeline <alerts@your-domain.com>"
#

BRAND = {
    # Primary brand name - use this everywhere
    'name': 'The Press Release Pipeline',

    # Logo alt text (matches visual logo)
    'logo_alt': 'Press Release Pipeline',

    # Email sender display name
    'email_from_name': 'The Press Release Pipeline',
    'email_from_address': 'alerts@your-domain.com',
    'email_from': 'The Press Release Pipeline <alerts@your-domain.com>',

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
    'domain': 'your-domain.com',
    'app_domain': 'app.your-domain.com',
    'url': 'https://your-domain.com',
    'logo_url': 'https://your-domain.com/logo.png',
    'year': 2026,
}


# =============================================================================
# SIGNUP / SUBSCRIPTION
# =============================================================================

SIGNUP_CONFIG = {
    'headline': 'Get the daily brief before the open',
    'description': 'Daily real estate press releases, offerings, partnerships, and corporate news — all in one place.',
    'popup_desc': 'Delivered before the open.<br>Daily real estate press releases, financings, and corporate news.',
    'footer': 'Free. Unsubscribe anytime.',
    'button_text': 'Subscribe',
    'placeholder': 'you@example.com',
    'api_url': '/api/subscribe',  # AJAX endpoint (CSRF-exempt)
    'nav_cta': 'Get the Daily Sheet',  # Short CTA for nav bar
}


# =============================================================================
# SEO / META
# =============================================================================

META_CONFIG = {
    'description': 'Daily curated press releases from publicly traded REITs. Acquisitions, earnings, dividends, and more. Never miss a REIT release.',
    'keywords': 'REIT, real estate investment trust, press releases, earnings, dividends, acquisitions, commercial real estate',
    'og_image': 'https://your-domain.com/og-image.png',
    'og_image_width': 1200,
    'og_image_height': 630,
    'twitter_card': 'summary_large_image',
}


# =============================================================================
# FOOTER / LEGAL
# =============================================================================

FOOTER_CONFIG = {
    'privacy_url': 'https://your-domain.com/privacy.html',
    'contact_email': 'hello@your-domain.com',
    'copyright_text': f'© {SITE_CONFIG["year"]} {BRAND["legal_name"]}',
}


# =============================================================================
# SECTION HEADERS (for newsletter/homepage sections)
# =============================================================================

SECTION_HEADERS = {
    'headlines': 'Headlines',
    'financings': 'Financings and Offerings',
    'property': 'Property Transactions and Leases',
    'earnings': 'Earnings Releases',
    'other': 'Other Announcements',
}


# =============================================================================
# EMPTY STATES (when no content available)
# =============================================================================

EMPTY_STATES = {
    'no_releases': 'No press releases for today. Check back tomorrow!',
    'quiet_day': 'It was a quiet day in real estate. No major announcements.',
}


# =============================================================================
# PAGE TAGLINES
# =============================================================================

TAGLINES = {
    'homepage': 'Never Miss a REIT Release',
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
# EMAIL TEMPLATES (confirmation, welcome, etc.)
# =============================================================================

EMAIL_TEMPLATES = {
    # Confirmation email (double opt-in)
    'confirmation': {
        'subject': f"Confirm your {BRAND['name']} subscription",
        'heading': f"Confirm your {BRAND['name']} subscription",
        'body': f"Click the button below to confirm your subscription to the {BRAND['name']} daily newsletter:",
        'button_text': 'Confirm Subscription',
        'expiry_notice': 'This link expires in 24 hours.',
        'ignore_notice': f"If you didn't sign up for {BRAND['name']}, you can safely ignore this email.",
    },
    # Already subscribed notification
    'already_subscribed': {
        'subject': f"You're already subscribed to {BRAND['name']}",
        'heading': "You're already subscribed!",
        'body': f"Someone (hopefully you!) just tried to sign up for {BRAND['name']} using this email address. Since you're already on our list, there's nothing you need to do.",
        'cta_text': "Read Today's Edition",
    },
}


# =============================================================================
# SUBSCRIPTION PAGES (centralized copy for all subscription-related pages)
# =============================================================================

SUBSCRIPTION_PAGES = {
    # Check Email page (shown after signup)
    'check_email': {
        'title': 'Check Your Email',
        'heading': 'Almost there!',
        'message': "We've sent a confirmation email to your inbox. Click the link to start receiving The Press Release Pipeline.",
        'subtext': "If you don't see it, check your spam folder.",
    },
    # Verified page (shown after clicking email link)
    'verified': {
        'title': "You're Subscribed",
        'heading': 'Welcome to The Press Release Pipeline!',
        'message': "Your email has been verified. You'll receive our daily brief before the market opens.",
        'cta_text': "Read Today's Edition",
        'cta_url': 'https://your-domain.com',
    },
    # Unsubscribed page
    'unsubscribed': {
        'title': 'Unsubscribed',
        'heading': "You've been unsubscribed",
        'message': "You won't receive any more emails from The Press Release Pipeline.",
        'subtext': 'Changed your mind? You can always subscribe again.',
        'cta_text': 'View Latest Edition',
        'cta_url': 'https://your-domain.com',
    },
    # Error pages
    'verify_error': {
        'title': 'Verification Error',
        'heading': 'Link Expired',
        'message': 'This verification link has expired. Check your inbox for a newer email, or request a new one below.',
        'cta_text': 'Sign Up Again',
        'cta_url': '/subscribe',
    },
    'unsubscribe_error': {
        'title': 'Unsubscribe Error',
        'heading': 'Invalid Link',
        'message': 'This unsubscribe link is invalid.',
        'cta_text': 'View Latest Edition',
        'cta_url': 'https://your-domain.com',
    },
}


# =============================================================================
# COMBINED CONFIG FOR TEMPLATES
# =============================================================================

def _get_defaults() -> dict:
    """Get hardcoded default config values."""
    return {
        'brand': dict(BRAND),
        'site': dict(SITE_CONFIG),
        'signup': dict(SIGNUP_CONFIG),
        'subscription': {k: dict(v) for k, v in SUBSCRIPTION_PAGES.items()},
        'emails': {k: dict(v) for k, v in EMAIL_TEMPLATES.items()},
        'meta': dict(META_CONFIG),
        'footer': dict(FOOTER_CONFIG),
        'colors': dict(PUBLIC_COLORS),
        'fonts': dict(PUBLIC_FONTS),
        'sections': dict(SECTION_HEADERS),
        'empty_states': dict(EMPTY_STATES),
        'taglines': dict(TAGLINES),
    }


def get_public_config() -> dict:
    """
    Get complete public site configuration for template context.

    Merges hardcoded defaults with DynamoDB overrides from Site Editor.

    Usage in route:
        from config.site_config import get_public_config
        return render_template('public/index.html', config=get_public_config())

    Usage in template:
        {{ config.site.name }}
        {{ config.signup.headline }}
        {{ config.colors.primary }}
        {{ config.sections.headlines }}
    """
    try:
        # Lazy import to avoid circular dependency
        from services.site_editor_service import get_site_editor_service
        service = get_site_editor_service()
        return service.get_merged_config('active')
    except Exception:
        # Fallback to defaults if DynamoDB unavailable (local dev, etc.)
        return _get_defaults()


# =============================================================================
# NAVIGATION LINKS (for public pages)
# =============================================================================

PUBLIC_NAVIGATION = [
    {
        'label': 'Front Page',
        'url': 'https://your-domain.com',
        'is_external': False,
    },
    {
        'label': "Yesterday's Issue",
        'url_template': 'https://your-domain.com/news/archive/{date}/',
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
