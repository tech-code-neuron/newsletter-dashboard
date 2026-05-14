"""
Public Pages Routes

Serves public-facing pages for the newsletter website.
These pages are served from Flask but mirror the S3 static pages.

Routes:
    GET / - Home page (latest newsletter edition)
    GET /archive/<date>/ - Historical newsletter editions
    GET /check-email - Confirmation page after signup
    GET /subscribed - Success page after email verification
    GET /unsubscribed - Success page after unsubscribe

SOLID Principles:
    - Single Responsibility: Public page rendering only
    - Open/Closed: Add new pages without modifying existing code
"""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional, Dict, Any, List

from flask import Blueprint, render_template, request, abort, send_from_directory, current_app

# Eastern Time - must match publisher.py and publisher_email.py
ET = ZoneInfo('America/New_York')

from middleware.domain_router import public_only
from config.site_config import get_public_config, get_navigation_with_date
from config.newsletter_status import get_newsletter_config
from config.design_tokens import get_all_tokens
from config.section_config import SECTIONS, get_empty_sections, get_sections_from_data
from services.newsletter_service import NewsletterService, get_newsletter_service

logger = logging.getLogger(__name__)

public_bp = Blueprint('public', __name__)


@public_bp.route('/logo.png')
def serve_logo():
    """Serve the logo from static folder at /logo.png for public pages."""
    return send_from_directory(current_app.static_folder, 'logo.png')


@public_bp.route('/og-image.png')
def serve_og_image():
    """Serve OG image for social sharing previews (iMessage, etc.)."""
    return send_from_directory(current_app.static_folder, 'og-image.png')


def get_yesterday_url() -> str:
    """Get URL for yesterday's newsletter archive."""
    yesterday = datetime.now(ET) - timedelta(days=1)
    return f"https://reitsheet.co/news/archive/{yesterday.strftime('%Y-%m-%d')}/"


def get_current_date_formatted() -> str:
    """Get current date in readable format (e.g., 'Friday, March 28, 2026')."""
    return datetime.now(ET).strftime('%A, %B %d, %Y')


def format_edition_date(date_str: str) -> str:
    """
    Format a date string for display.

    Args:
        date_str: Date in YYYY-MM-DD format

    Returns:
        Formatted date string (e.g., 'Friday, March 28, 2026')
    """
    try:
        date = datetime.strptime(date_str, '%Y-%m-%d')
        return date.strftime('%A, %B %d, %Y')
    except (ValueError, TypeError):
        return date_str


def extract_sections_from_edition(edition: Dict[str, Any]) -> Dict[str, List[Dict]]:
    """
    Extract ALL categorized sections from a newsletter edition.

    Items within each section are sorted alphabetically by company name.
    Uses centralized section config from config/section_config.py.

    Args:
        edition: Newsletter edition from DynamoDB

    Returns:
        Dict with all sections using DynamoDB keys (headlines, financing_releases, etc.)
    """
    # Sort key for alphabetical ordering by company name
    def sort_key(item):
        return (item.get('company_name') or item.get('ticker') or '').lower()

    if not edition:
        return get_empty_sections()

    # Check for pre-categorized 'sections' field (from NewsletterPublisher)
    if 'sections' in edition:
        result = get_sections_from_data(edition['sections'])
        # Sort each section alphabetically
        for section_items in result.values():
            section_items.sort(key=sort_key)
        return result

    # Fallback: categorize from 'items' list
    items = edition.get('items', [])
    if not items:
        # Last resort: try separate section lists from edition root
        result = get_sections_from_data(edition)
        # Sort each section alphabetically
        for section_items in result.values():
            section_items.sort(key=sort_key)
        return result

    # Categorize items by section using centralized config
    # Build a dict mapping internal_key -> dynamo_key -> items list
    section_items = {internal_key: [] for internal_key, _, _ in SECTIONS}

    for item in items:
        section = item.get('section', 'other')
        if section in section_items:
            section_items[section].append(item)
        else:
            section_items['other'].append(item)

    # Convert to DynamoDB keys format
    result = get_sections_from_data(section_items)

    # Sort each section alphabetically
    for items_list in result.values():
        items_list.sort(key=sort_key)

    return result


def get_homepage_data() -> dict:
    """
    Get all data needed to render the homepage.

    Used by both the public homepage and the site editor preview.

    Returns:
        Dict with sections config, section_data, date, navigation, etc.
    """
    newsletter_service = get_newsletter_service()
    edition = newsletter_service.get_latest()

    if not edition:
        return {
            'sections': SECTIONS,
            'section_data': {key: [] for key, _, _ in SECTIONS},
            'current_date': get_current_date_formatted(),
            'preview_text': None,
            'archive_dates': []
        }

    sections_dict = extract_sections_from_edition(edition)
    prev_date = newsletter_service.get_previous_date(edition.get('date', ''))
    edition_date = edition.get('date', '')
    display_date = format_edition_date(edition_date) if edition_date else get_current_date_formatted()

    # Convert DynamoDB keys to internal keys for template
    section_data = {
        key: sections_dict.get(dynamo_key, [])
        for key, _, dynamo_key in SECTIONS
    }

    return {
        'edition': edition,
        'current_date': display_date,
        'sections': SECTIONS,
        'section_data': section_data,
        'preview_text': edition.get('preview_text'),
        'prev_date': prev_date,
        'yesterday_url': get_yesterday_url() if prev_date else None,
        'nav': get_navigation_with_date(prev_date) if prev_date else [],
        'newsletter': get_newsletter_config(),
        'tokens': get_all_tokens(),
    }


# =============================================================================
# PUBLIC PAGES
# =============================================================================

@public_bp.route('/')
@public_only
def home():
    """
    Render the public home page (latest newsletter edition).

    Loads the latest published newsletter from DynamoDB and renders
    it with full content sections.
    """
    config = get_public_config()
    newsletter_service = get_newsletter_service()

    # Add site URL for proper linking
    config['site']['url'] = f"https://{config['site']['domain']}"
    config['site']['logo_url'] = f"https://{config['site']['domain']}/logo.png"

    # Get the latest published edition
    edition = newsletter_service.get_latest()

    if not edition:
        # No editions published yet - show empty state
        return render_template(
            'public/pages/home.html',
            config=config,
            current_date=get_current_date_formatted(),
            yesterday_url=get_yesterday_url(),
            sections=SECTIONS,
            section_data={key: [] for key, _, _ in SECTIONS},
            preview_text=None
        )

    # Extract sections from edition
    sections_dict = extract_sections_from_edition(edition)

    # Convert DynamoDB keys to internal keys for template
    section_data = {
        key: sections_dict.get(dynamo_key, [])
        for key, _, dynamo_key in SECTIONS
    }

    # Get previous date for navigation
    prev_date = newsletter_service.get_previous_date(edition.get('date', ''))

    # Format the edition date for display
    edition_date = edition.get('date', '')
    display_date = format_edition_date(edition_date) if edition_date else get_current_date_formatted()

    # Build navigation links
    nav = get_navigation_with_date(prev_date) if prev_date else []

    return render_template(
        'public/pages/home.html',
        config=config,
        edition=edition,
        current_date=display_date,
        yesterday_url=get_yesterday_url() if prev_date else None,
        sections=SECTIONS,
        section_data=section_data,
        preview_text=edition.get('preview_text'),
        prev_date=prev_date,
        nav=nav,
        newsletter=get_newsletter_config(),
        tokens=get_all_tokens(),
    )


@public_bp.route('/news/archive/<date>/')
@public_only
def archive(date: str):
    """
    Render an archived newsletter edition.

    Args:
        date: Date string in YYYY-MM-DD format

    Returns:
        Rendered archive page or 404 if not found
    """
    config = get_public_config()
    newsletter_service = get_newsletter_service()

    # Add site URL for proper linking
    config['site']['url'] = f"https://{config['site']['domain']}"
    config['site']['logo_url'] = f"https://{config['site']['domain']}/logo.png"

    # Validate date format
    try:
        datetime.strptime(date, '%Y-%m-%d')
    except ValueError:
        logger.warning(f"Invalid date format requested: {date}")
        abort(404)

    # Get the edition for this date
    edition = newsletter_service.get_by_date(date)

    if not edition:
        logger.info(f"Archive edition not found for date: {date}")
        abort(404)

    # Extract sections from edition (using sections_dict to avoid collision with SECTIONS import)
    sections_dict = extract_sections_from_edition(edition)

    # Convert DynamoDB keys to internal keys for template (same pattern as home())
    section_data = {
        key: sections_dict.get(dynamo_key, [])
        for key, _, dynamo_key in SECTIONS
    }

    # Get navigation (prev/next dates)
    prev_date, next_date = newsletter_service.get_navigation(date)

    # Format the edition date for display
    display_date = format_edition_date(date)

    # Build navigation links
    nav = get_navigation_with_date(prev_date) if prev_date else []

    # Get latest published date for navigation comparison
    published_dates = newsletter_service.list_published_dates()
    latest_date = published_dates[0] if published_dates else None

    return render_template(
        'public/pages/archive.html',
        config=config,
        edition=edition,
        current_date=display_date,
        sections=SECTIONS,
        section_data=section_data,
        preview_text=edition.get('preview_text'),
        prev_date=prev_date,
        next_date=next_date,
        latest_date=latest_date,
        is_archive=True,
        nav=nav,
        newsletter=get_newsletter_config(),
        tokens=get_all_tokens(),
    )


@public_bp.route('/check-email')
@public_only
def check_email():
    """
    Render the 'check your email' page shown after signup.

    Instructs user to check their inbox for confirmation link.
    """
    config = get_public_config()
    config['site']['url'] = f"https://{config['site']['domain']}"

    return render_template(
        'public/pages/check-email.html',
        config=config
    )


@public_bp.route('/subscribed')
@public_only
def subscribed():
    """
    Render the subscription success page.

    Shown after user clicks verification link in email.
    Handles 'already subscribed' case via query parameter.
    """
    config = get_public_config()
    config['site']['url'] = f"https://{config['site']['domain']}"

    # Check if already subscribed (query param from S3 version)
    already_subscribed = request.args.get('already') == 'true'

    return render_template(
        'public/pages/subscribed.html',
        config=config,
        already_subscribed=already_subscribed
    )


@public_bp.route('/unsubscribed')
@public_only
def unsubscribed():
    """
    Render the unsubscribe confirmation page.

    Shown after user unsubscribes from the newsletter.
    """
    config = get_public_config()
    config['site']['url'] = f"https://{config['site']['domain']}"

    return render_template(
        'public/pages/unsubscribed.html',
        config=config
    )
