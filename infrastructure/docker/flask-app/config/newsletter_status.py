"""
Newsletter Status and Section Configuration

Single source of truth for all newsletter statuses and sections.
Eliminates hardcoded values in templates.

SOLID Principle: Open/Closed - add new statuses/sections without modifying templates.
"""

from config.design_tokens import COLORS
from config.section_config import SECTION_DYNAMO_KEYS


# =============================================================================
# NEWSLETTER STATUSES
# =============================================================================

NEWSLETTER_STATUSES = {
    'ready': {
        'label': 'Ready',
        'label_short': 'Ready',
        'color': COLORS['success'],
        'bg': COLORS['success_bg'],
        'text': COLORS['success_text'],
        'border': COLORS['success_border'],
        'icon': None,
        'order': 1,
        'css_class': 'status-ready',
        'is_actionable': True,
    },
    'needs_review': {
        'label': 'Needs Review',
        'label_short': 'Review',
        'color': COLORS['warning'],
        'bg': COLORS['warning_bg'],
        'text': COLORS['warning_text'],
        'border': COLORS['warning_border'],
        'icon': None,
        'order': 2,
        'css_class': 'status-needs-review',
        'is_actionable': True,
    },
    'published': {
        'label': 'Published',
        'label_short': 'Published',
        'color': COLORS['info'],
        'bg': COLORS['info_bg'],
        'text': COLORS['info_text'],
        'border': COLORS['info_border'],
        'icon': None,
        'order': 3,
        'css_class': 'status-published',
        'is_actionable': False,
    },
    'excluded': {
        'label': 'Excluded',
        'label_short': 'Exclude',
        'color': COLORS['secondary'],
        'bg': COLORS['secondary_bg'],
        'text': COLORS['secondary_text'],
        'border': COLORS['border'],
        'icon': None,
        'order': 4,
        'css_class': 'status-excluded',
        'is_actionable': False,
    },
}


# =============================================================================
# NEWSLETTER SECTIONS
# =============================================================================

NEWSLETTER_SECTIONS = {
    'headline': {
        'label': 'Headline',
        'label_plural': 'Headlines',
        'order': 1,
        'css_class': 'section-headline',
        'color': COLORS['primary'],
        'is_primary': True,
    },
    'financing': {
        'label': 'Financing',
        'label_plural': 'Financings',
        'order': 2,
        'css_class': 'section-financing',
        'color': COLORS['info'],
        'is_primary': False,
    },
    'property': {
        'label': 'Property',
        'label_plural': 'Property Transactions',
        'order': 3,
        'css_class': 'section-property',
        'color': COLORS['success'],
        'is_primary': False,
    },
    'earnings': {
        'label': 'Earnings',
        'label_plural': 'Earnings Releases',
        'order': 4,
        'css_class': 'section-earnings',
        'color': COLORS['warning'],
        'is_primary': False,
    },
    'other': {
        'label': 'Other',
        'label_plural': 'Other Announcements',
        'order': 5,
        'css_class': 'section-other',
        'color': COLORS['secondary'],
        'is_primary': False,
    },
}


# =============================================================================
# SEC FILING STATUS (special case)
# =============================================================================

SEC_FILING_STATUS = {
    'label': 'SEC Filings',
    'color': COLORS['sec_purple'],
    'bg': COLORS['sec_bg'],
    'text': COLORS['sec_purple'],
    'css_class': 'status-sec',
    'default_section': 'financing',
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def get_all_section_keys() -> list[str]:
    """
    Return all section keys, dynamically derived from NEWSLETTER_SECTIONS.

    Single source of truth: NEWSLETTER_SECTIONS dictionary defines sections.
    This function extracts keys in order for validation and iteration.

    Returns:
        List of section keys sorted by order (e.g., ['headline', 'financing', ...])
    """
    return [
        key for key, _ in sorted(
            NEWSLETTER_SECTIONS.items(),
            key=lambda x: x[1]['order']
        )
    ]


def get_status_options(include_all: bool = True) -> list[tuple[str, str]]:
    """
    Returns status options for select dropdowns.

    Args:
        include_all: If True, include all statuses. If False, only actionable.

    Returns:
        List of (value, label) tuples sorted by order.
    """
    statuses = NEWSLETTER_STATUSES.items()
    if not include_all:
        statuses = [(k, v) for k, v in statuses if v['is_actionable']]

    return [
        (key, status['label'])
        for key, status in sorted(statuses, key=lambda x: x[1]['order'])
    ]


def get_status_options_mobile() -> list[tuple[str, str]]:
    """Returns status options with short labels for mobile."""
    return [
        (key, status['label_short'])
        for key, status in sorted(
            NEWSLETTER_STATUSES.items(),
            key=lambda x: x[1]['order']
        )
    ]


def get_section_options() -> list[tuple[str, str]]:
    """
    Returns section options for select dropdowns.

    Returns:
        List of (value, label) tuples sorted by order.
    """
    return [
        (key, section['label'])
        for key, section in sorted(
            NEWSLETTER_SECTIONS.items(),
            key=lambda x: x[1]['order']
        )
    ]


def get_section_labels() -> dict[str, str]:
    """Returns a dictionary mapping section keys to their labels."""
    return {key: section['label'] for key, section in NEWSLETTER_SECTIONS.items()}


def get_status_info(status_key: str) -> dict:
    """
    Get full status info by key.

    Args:
        status_key: The status key (e.g., 'ready', 'needs_review')

    Returns:
        Status dictionary or default to 'ready' if not found.
    """
    return NEWSLETTER_STATUSES.get(status_key, NEWSLETTER_STATUSES['ready'])


def get_section_info(section_key: str) -> dict:
    """
    Get full section info by key.

    Args:
        section_key: The section key (e.g., 'headline', 'earnings')

    Returns:
        Section dictionary or default to 'headline' if not found.
    """
    return NEWSLETTER_SECTIONS.get(section_key, NEWSLETTER_SECTIONS['headline'])


def get_status_css_class(status_key: str) -> str:
    """Get the CSS class for a status."""
    status = get_status_info(status_key)
    return status['css_class']


def get_section_css_class(section_key: str) -> str:
    """Get the CSS class for a section."""
    section = get_section_info(section_key)
    return section['css_class']


# =============================================================================
# TEMPLATE CONTEXT HELPERS
# =============================================================================

def get_newsletter_config() -> dict:
    """
    Get all newsletter configuration for template context.

    Usage in route:
        context = get_newsletter_config()
        return render_template('publisher.html', **context)

    Usage in template:
        {% for key, status in statuses.items() %}
            <option value="{{ key }}">{{ status.label }}</option>
        {% endfor %}
    """
    return {
        'statuses': NEWSLETTER_STATUSES,
        'sections': NEWSLETTER_SECTIONS,
        'status_options': get_status_options(),
        'section_options': get_section_options(),
        'section_labels': get_section_labels(),
        'sec_filing_status': SEC_FILING_STATUS,
    }


# =============================================================================
# SECTION TEMPLATE VARIABLE MAPPING
# =============================================================================

# Maps classifier section keys to template variable names
# Uses SECTION_DYNAMO_KEYS from section_config.py (single source of truth)
# This ensures all 8 sections are available: headline, financing, management,
# property, earnings, conference_call, dividend, other
SECTION_TEMPLATE_VARS = SECTION_DYNAMO_KEYS


def categorize_releases_for_template(releases, section_getter, title_getter=None):
    """
    Categorize releases into template-ready sections.

    Used by both email sending and homepage rendering to ensure
    consistent section naming across all templates.

    Items within each section are sorted alphabetically by company name.

    Args:
        releases: List of press release/disclosure objects (in display order)
        section_getter: Function to get section key for each release
        title_getter: Optional function to get display title

    Returns:
        Dict with template variable names as keys:
        {
            'headlines': [...],
            'financing_releases': [...],
            'property_transactions': [...],
            'earnings_releases': [...],
            'other_announcements': [...]
        }

    Example:
        from config.newsletter_status import categorize_releases_for_template
        sections = categorize_releases_for_template(releases, section_getter)
        return render_template('email.html', edition={'sections': sections, ...})
    """
    from core.title_utils import get_display_title

    # Initialize empty sections
    result = {var: [] for var in SECTION_TEMPLATE_VARS.values()}

    for release in releases:
        section_key = section_getter(release)
        template_var = SECTION_TEMPLATE_VARS.get(section_key, 'other_announcements')

        # Build item dict for template
        # Use sec_url for SEC filings (actual document, not index page)
        if getattr(release, 'is_sec_filing', False):
            url = getattr(release, 'sec_url', None) or getattr(release, 'url', None) or '#'
        else:
            url = getattr(release, 'url', None) or '#'

        item = {
            'url': url,
            'ticker': getattr(release, 'ticker', None) or (
                release.company.ticker if hasattr(release, 'company') and release.company else 'UNK'
            ),
            'company_name': getattr(release, 'company_name', None) or (
                release.company.name if hasattr(release, 'company') and release.company else ''
            ),
            'title': title_getter(release) if title_getter else get_display_title(release),
            'is_public': release.company.is_public if hasattr(release, 'company') and release.company and hasattr(release.company, 'is_public') else True,
            'lead_sponsor': getattr(release.company, 'lead_sponsor', '') if hasattr(release, 'company') and release.company else '',
        }
        result[template_var].append(item)

    # Sort each section alphabetically by company name
    for section_items in result.values():
        section_items.sort(key=lambda x: (x.get('company_name') or x.get('ticker') or '').lower())

    return result
