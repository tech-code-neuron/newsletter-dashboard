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

    # SEC EDGAR fields
    company.cik = form_data.get('cik') or None
    company.op_cik = form_data.get('op_cik') or None
    company.op_name = form_data.get('op_name') or None
    op_unique = form_data.get('op_has_unique_filings')
    if isinstance(op_unique, bool):
        company.op_has_unique_filings = op_unique
    else:
        company.op_has_unique_filings = op_unique == 'on'


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
        form_data: dict from form.data (Flask-WTF) or Flask request.form

    Returns:
        dict: Company data suitable for repo.create() or repo.update()
    """
    # Handle newswire provider "Other" special case
    newswire_provider = form_data.get('newswire_provider')
    if newswire_provider == 'Other':
        newswire_provider = form_data.get('custom_provider')

    # Handle active field - can be boolean (form.data) or string (request.form)
    active_val = form_data.get('active')
    if isinstance(active_val, bool):
        active = active_val
    else:
        active = active_val == 'on'

    data = {
        'name': form_data.get('name'),
        'ir_url': form_data.get('ir_url'),
        'press_release_url': form_data.get('press_release_url'),
        'rss_feed_url': form_data.get('rss_feed_url'),
        'company_rss_feed_url': form_data.get('company_rss_feed_url'),
        'ir_platform': form_data.get('ir_platform'),
        'scraper_variant': form_data.get('scraper_variant') or None,
        'sector': form_data.get('sector'),
        'active': active,
        'newswire_provider': newswire_provider,
        'newswire_id': form_data.get('newswire_id'),
    }

    # Include ticker if present (for add operations)
    if form_data.get('ticker'):
        data['ticker'] = form_data.get('ticker').upper()

    # Add Playwright fields if provided
    if form_data.get('playwright_url'):
        data['playwright_url'] = form_data.get('playwright_url')
    if form_data.get('playwright_selector'):
        data['playwright_selector'] = form_data.get('playwright_selector')
    if form_data.get('playwright_wait_for'):
        data['playwright_wait_for'] = form_data.get('playwright_wait_for')

    # Map ir_platform to url_construction_method for DynamoDB
    if form_data.get('ir_platform') == 'playwright_scraper':
        data['url_construction_method'] = 'playwright_scraper'
    elif form_data.get('ir_platform'):
        # For other platforms, use ir_platform value as-is
        # (this mapping can be extended as needed)
        data['url_construction_method'] = form_data.get('ir_platform')

    # Add SEC EDGAR fields if provided
    if form_data.get('cik'):
        data['cik'] = form_data.get('cik')
    if form_data.get('op_cik'):
        data['op_cik'] = form_data.get('op_cik')
    if form_data.get('op_name'):
        data['op_name'] = form_data.get('op_name')

    # Handle op_has_unique_filings - can be boolean or string
    op_unique = form_data.get('op_has_unique_filings')
    if op_unique:
        if isinstance(op_unique, bool):
            data['op_has_unique_filings'] = op_unique
        else:
            data['op_has_unique_filings'] = op_unique == 'on'

    # Handle is_public - convert string to boolean
    is_public_val = form_data.get('is_public')
    if is_public_val is not None:
        if isinstance(is_public_val, bool):
            data['is_public'] = is_public_val
        else:
            data['is_public'] = is_public_val == 'true'

    # Add sponsor fields - include even if empty to allow clearing
    # None values trigger REMOVE in DynamoDB when remove_none=True
    if 'lead_sponsor' in form_data:
        val = (form_data.get('lead_sponsor') or '').strip()
        data['lead_sponsor'] = val if val else None
    if 'second_sponsor' in form_data:
        val = (form_data.get('second_sponsor') or '').strip()
        data['second_sponsor'] = val if val else None

    return data
