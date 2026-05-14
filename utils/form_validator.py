"""
Form validation and data utilities.
Centralizes form processing logic and platform configuration.
"""
from config.platform_config import PLATFORM_LABELS


# ------------------------------------------------------------------
# PLATFORM OPTIONS - Data-Driven Configuration
# ------------------------------------------------------------------

def get_platform_options():
    """
    Generate platform options from PLATFORM_LABELS configuration.
    Data-driven approach ensures single source of truth (DRY principle).

    Returns:
        list: Grouped platform options for form select
              [('Group Name', [('key', 'Label'), ...]), ...]
    """
    # Platform grouping configuration (Open/Closed: add new groups here)
    platform_groups = {
        'GCS Platforms': ['gcs', 'gcs_with_dates'],
        'Q4 Platforms': ['q4_drupal', 'q4_js', 'q4_detail', 'q4_pdf'],
        'Other Platforms': [
            'investis', 'apollo_accordion', 'date_slug',
            'welltower', 'olp_pdf', 'wordpress_pdf', 'custom'
        ]
    }

    # Build grouped options from PLATFORM_LABELS
    options = []
    for group_name, platform_keys in platform_groups.items():
        group_options = []
        for key in platform_keys:
            if key in PLATFORM_LABELS:
                label = PLATFORM_LABELS[key][0]  # Extract label from (label, color) tuple
                group_options.append((key, label))

        if group_options:  # Only include non-empty groups
            options.append((group_name, group_options))

    return options


def get_sectors_from_db(db):
    """
    Fetch distinct sectors from database.

    Args:
        db: Database session

    Returns:
        list: Sorted list of sector names
    """
    from core.models import Company

    sectors = db.query(Company.sector).distinct().filter(
        Company.sector.isnot(None)
    ).order_by(Company.sector).all()

    return [s[0] for s in sectors]  # Extract from tuples


# ------------------------------------------------------------------
# FORM PROCESSING - Single Responsibility
# ------------------------------------------------------------------

def _apply_company_form_fields(company, form_data):
    """
    Apply form data to company object (shared logic).
    Private helper to eliminate duplication between create/update.

    Args:
        company: Company model instance to update
        form_data: Flask request.form object

    Returns:
        None (modifies company in-place)
    """
    # Basic fields
    company.name = form_data.get('name')
    company.ir_url = form_data.get('ir_url')
    company.press_release_url = form_data.get('press_release_url')
    company.rss_feed_url = form_data.get('rss_feed_url')
    company.company_rss_feed_url = form_data.get('company_rss_feed_url')
    company.ir_platform = form_data.get('ir_platform')
    company.scraper_variant = form_data.get('scraper_variant') or None
    company.sector = form_data.get('sector')
    company.active = form_data.get('active') == 'on'

    # Newswire provider (handle "Other" special case)
    newswire_provider = form_data.get('newswire_provider')
    if newswire_provider == 'Other':
        company.newswire_provider = form_data.get('custom_provider')
    else:
        company.newswire_provider = newswire_provider

    company.newswire_id = form_data.get('newswire_id')


def process_company_form(company, form_data):
    """
    Update company object from form data.
    Centralizes form processing logic to eliminate duplication.

    Args:
        company: Company model instance to update
        form_data: Flask request.form object

    Returns:
        None (modifies company in-place)
    """
    _apply_company_form_fields(company, form_data)


def create_company_from_form(form_data):
    """
    Create new Company instance from form data.

    Args:
        form_data: Flask request.form object

    Returns:
        Company: New company instance (not yet added to session)
    """
    from core.models import Company

    ticker = form_data.get('ticker', '').strip().upper()

    # Create company with just ticker
    company = Company(ticker=ticker)

    # Apply all form fields using shared logic
    _apply_company_form_fields(company, form_data)

    return company


def process_company_form_data(form_data):
    """
    Extract company data from form as a dictionary.
    Used with repository pattern (DynamoDB/SQLite abstraction).

    Args:
        form_data: Flask request.form object

    Returns:
        dict: Company data suitable for repo.create() or repo.update()
    """
    # Handle newswire provider "Other" special case
    newswire_provider = form_data.get('newswire_provider')
    if newswire_provider == 'Other':
        newswire_provider = form_data.get('custom_provider')

    return {
        'name': form_data.get('name'),
        'ir_url': form_data.get('ir_url'),
        'press_release_url': form_data.get('press_release_url'),
        'rss_feed_url': form_data.get('rss_feed_url'),
        'company_rss_feed_url': form_data.get('company_rss_feed_url'),
        'ir_platform': form_data.get('ir_platform'),
        'scraper_variant': form_data.get('scraper_variant') or None,
        'sector': form_data.get('sector'),
        'active': form_data.get('active') == 'on',
        'newswire_provider': newswire_provider,
        'newswire_id': form_data.get('newswire_id'),
    }
