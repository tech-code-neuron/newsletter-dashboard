"""
Publisher Blueprint - Newsletter Publishing Interface

Routes:
- /publisher - Main publisher page with date picker
- /publisher/preview - Live preview fragment (AJAX)
- /publisher/generate - Generate final HTML
- /publisher/update-status - Update press release status
- /publisher/update-title - Update newsletter display title
- /publisher/update-order - Save custom ordering (session-only for MVP)

SOLID Principles:
- Single Responsibility: HTTP handling only
- Dependency Inversion: Uses service abstractions
"""
import logging
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

from services.publisher_service import get_publisher_service, apply_url_ordering, create_section_getter

logger = logging.getLogger(__name__)
from core.publisher_generator import get_publisher_generator
from forms.publisher_forms import PublisherDateForm  # For pre-commit validation
from config.site_config import get_public_config
from config.design_tokens import get_all_tokens
from config.section_config import SECTIONS, SECTION_DISPLAY_NAMES

# Blueprint setup
publisher_bp = Blueprint('publisher', __name__)

# Services
service = get_publisher_service()
generator = get_publisher_generator()

# Eastern timezone
ET = ZoneInfo('America/New_York')


# =============================================================================
# Main Page
# =============================================================================

@publisher_bp.route('/publisher')
def publisher():
    """
    Main publisher page with date picker and editor interface.

    Query params:
        date: Optional date string (YYYY-MM-DD), defaults to today
    """
    logger.info(f"PUBLISHER: GET /publisher | date={request.args.get('date', 'today')}")

    # Parse selected date
    date_str = request.args.get('date')
    if date_str:
        try:
            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = datetime.now(ET).date()
    else:
        selected_date = datetime.now(ET).date()

    # Allow up to tomorrow (today + 1) for next-day preview/setup
    today = datetime.now(ET).date()
    max_date = today + timedelta(days=1)
    if selected_date > max_date:
        selected_date = max_date

    # Get time window description
    time_window = service.format_time_window(selected_date)

    # Get all items (press releases + SEC filings) for this date
    releases = service.get_all_items_for_publisher(selected_date)

    # Sort by ticker alphabetically
    releases.sort(key=lambda r: (r.ticker or '').upper())

    # Get counts by status (includes both press releases and SEC filings)
    status_counts = service.count_all_items_by_status(selected_date)

    selected_date_str = selected_date.isoformat()

    # Get ready releases for preview
    # Include: 'ready' items AND same-day published items (user may make changes)
    # Exclude: items published for a previous date (previously published)
    ready_releases = [
        r for r in releases
        if (r.newsletter_status or 'ready') == 'ready'
        or (r.newsletter_status == 'published' and r.published_for_date == selected_date_str)
    ]

    # Get custom ordering from session if available
    session_key = f'publisher_order_{selected_date.isoformat()}'
    custom_order = session.get(session_key, [])

    # Apply custom ordering (preserves ALL releases)
    ready_releases = apply_url_ordering(ready_releases, custom_order)

    # Compute section classifications for each item (ALL items, not just ready)
    section_info = {}
    for release in releases:
        # Use url property (works for both PressReleaseDTO and DisclosureDTO)
        item_url = release.url

        # SEC filings always go to 'financing' section
        if getattr(release, 'is_sec_filing', False):
            section_info[item_url] = {
                'auto': 'financing',
                'effective': 'financing',
                'override': None,
                'is_overridden': False,
                'is_sec_filing': True
            }
        else:
            auto_section = service.get_auto_section(release, service.get_display_title)
            effective_section = service.get_effective_section(release, service.get_display_title)
            is_overridden = release.newsletter_section is not None
            section_info[item_url] = {
                'auto': auto_section,
                'effective': effective_section,
                'override': release.newsletter_section,
                'is_overridden': is_overridden,
                'is_sec_filing': False
            }

    return render_template(
        'publisher.html',
        selected_date=selected_date,
        time_window=time_window,
        releases=releases,
        ready_releases=ready_releases,
        status_counts=status_counts,
        today=today,
        max_date=max_date,
        section_info=section_info,
        sections=SECTIONS,
        section_labels=SECTION_DISPLAY_NAMES
    )


# =============================================================================
# Preview (AJAX)
# =============================================================================

@publisher_bp.route('/publisher/preview')
def publisher_preview():
    """
    Generate live preview HTML fragment.

    Query params:
        date: Date string (YYYY-MM-DD)

    Returns:
        HTML fragment for preview iframe
    """
    logger.info(f"PUBLISHER: GET /publisher/preview | date={request.args.get('date')}")
    date_str = request.args.get('date')

    # Parse date
    try:
        selected_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.now(ET).date()
    except ValueError:
        selected_date = datetime.now(ET).date()

    # Get all items (press releases + SEC filings) for the date window
    all_items = service.get_all_items_for_publisher(selected_date)

    # Filter to ready items + same-day published items
    # Exclude items published for a previous date
    selected_date_str = selected_date.isoformat()
    releases = [
        r for r in all_items
        if (r.newsletter_status or 'ready') == 'ready'
        or (r.newsletter_status == 'published' and r.published_for_date == selected_date_str)
    ]

    # Apply custom order from session (preserves ALL releases)
    session_key = f'publisher_order_{selected_date.isoformat()}'
    url_order = session.get(session_key, [])
    releases = apply_url_ordering(releases, url_order)

    # Create section getter (SEC filings always go to 'financing')
    section_getter = create_section_getter(service)

    # Generate preview HTML
    html = generator.generate_preview_html(
        releases=releases,
        newsletter_date=selected_date,
        title_getter=service.get_display_title,
        section_getter=section_getter
    )

    return html


# =============================================================================
# Web Preview (Uses Public Templates)
# =============================================================================

@publisher_bp.route('/publisher/preview-web')
def publisher_preview_web():
    """
    Generate web preview using public templates (matches live site exactly).

    Uses the same templates as the public homepage for pixel-perfect preview.
    """
    logger.info(f"PUBLISHER: GET /publisher/preview-web | date={request.args.get('date')}")
    date_str = request.args.get('date')

    # Parse date
    try:
        selected_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.now(ET).date()
    except ValueError:
        selected_date = datetime.now(ET).date()

    # Get all items for the date window
    all_items = service.get_all_items_for_publisher(selected_date)

    # Filter to ready items + same-day published items
    selected_date_str = selected_date.isoformat()
    releases = [
        r for r in all_items
        if (r.newsletter_status or 'ready') == 'ready'
        or (r.newsletter_status == 'published' and r.published_for_date == selected_date_str)
    ]

    # Apply custom order from session (preserves ALL releases)
    session_key = f'publisher_order_{selected_date.isoformat()}'
    url_order = session.get(session_key, [])
    releases = apply_url_ordering(releases, url_order)

    # Categorize into sections dynamically using section_config
    section_getter = create_section_getter(service)
    section_buckets = {key: [] for key, _, _ in SECTIONS}

    for release in releases:
        # Get section classification (SEC filings always go to 'financing')
        section = section_getter(release)

        # Convert to dict format expected by template
        # Use sec_url for SEC filings (returns actual document URL, not index.htm)
        item = {
            'url': getattr(release, 'sec_url', None) or release.url,
            'title': service.get_display_title(release),
            'ticker': release.ticker,
            'company_name': (
                getattr(release, 'company_name', None) or
                (release.company.name if hasattr(release, 'company') and release.company else '') or
                release.ticker
            ),
            'is_public': getattr(release.company, 'is_public', True) if hasattr(release, 'company') and release.company else True,
            'lead_sponsor': getattr(release.company, 'lead_sponsor', '') if hasattr(release, 'company') and release.company else '',
        }

        # Route to appropriate section (fallback to 'other' if unknown)
        if section in section_buckets:
            section_buckets[section].append(item)
        else:
            section_buckets['other'].append(item)

    # Sort each section alphabetically by company name
    def sort_key(item):
        return (item.get('company_name') or item.get('ticker') or '').lower()

    for items in section_buckets.values():
        items.sort(key=sort_key)

    # Format date for display
    display_date = selected_date.strftime('%A, %B %-d, %Y')

    # Get config
    config = get_public_config()

    return render_template(
        'public/pages/home.html',
        config=config,
        current_date=display_date,
        sections=SECTIONS,
        section_data=section_buckets,
        prev_date=None,  # No navigation in preview
        preview_text=None,
        tokens=get_all_tokens(),
    )


# =============================================================================
# Generate Final HTML
# =============================================================================

@publisher_bp.route('/publisher/generate', methods=['POST'])
def publisher_generate():
    """
    Generate final newsletter HTML and optionally mark items as published.

    Request body (JSON):
        date: Date string (YYYY-MM-DD)
        urls: List of URLs in display order
        mark_published: Boolean, whether to mark items as published

    Returns:
        JSON with generated HTML
    """
    data = request.get_json()
    logger.info(f"PUBLISHER: POST /publisher/generate | date={data.get('date')} | mark_published={data.get('mark_published')} | urls={len(data.get('urls', []))}")
    date_str = data.get('date')
    url_order = data.get('urls', [])
    mark_published = data.get('mark_published', False)

    # Parse date
    try:
        selected_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.now(ET).date()
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid date format'}), 400

    # Get all items (press releases + SEC filings) for the date window
    all_items = service.get_all_items_for_publisher(selected_date)

    # Filter to ready items + same-day published items
    selected_date_str = selected_date.isoformat()
    available_items = [
        r for r in all_items
        if (r.newsletter_status or 'ready') == 'ready'
        or (r.newsletter_status == 'published' and r.published_for_date == selected_date_str)
    ]

    # Apply custom order from provided URLs (preserves ALL releases)
    releases = apply_url_ordering(available_items, url_order)

    if not releases:
        return jsonify({'success': False, 'error': 'No items to include'}), 400

    # Create section getter (SEC filings always go to 'financing')
    section_getter = create_section_getter(service)

    # Generate HTML
    html = generator.generate_html(
        releases=releases,
        newsletter_date=selected_date,
        title_getter=service.get_display_title,
        section_getter=section_getter
    )

    # Mark as published if requested
    published_count = 0
    if mark_published:
        # Separate press releases and SEC filings
        pr_urls = [r.url for r in releases if not getattr(r, 'is_sec_filing', False)]
        sec_urls = [r.url for r in releases if getattr(r, 'is_sec_filing', False)]

        # Publish press releases
        if pr_urls:
            pr_success, _ = service.publish_for_date(pr_urls, selected_date_str)
            published_count += pr_success

        # Publish SEC filings
        if sec_urls:
            sec_success, _ = service.publish_disclosures_for_date(sec_urls, selected_date_str)
            published_count += sec_success

    return jsonify({
        'success': True,
        'html': html,
        'count': len(releases),
        'published_count': published_count
    })


# =============================================================================
# Status Management
# =============================================================================

@publisher_bp.route('/publisher/update-status', methods=['POST'])
def update_status():
    """
    Update newsletter status for a press release.

    Request body (JSON):
        url: Press release URL
        status: New status (ready, needs_review, published, excluded)
        date: Optional date string (YYYY-MM-DD) for published_for_date tracking

    Returns:
        JSON success response
    """
    data = request.get_json()
    url = data.get('url')
    status = data.get('status')
    logger.info(f"PUBLISHER: POST /publisher/update-status | url={url[:50] if url else None}... | status={status}")
    date_str = data.get('date')

    if not url or not status:
        return jsonify({'success': False, 'error': 'Missing url or status'}), 400

    try:
        # Build update data
        update_data = {
            'newsletter_status': status,
            'included_in_newsletter': (status == 'ready')
        }

        # Handle published_for_date and previously_published based on status
        if status == 'published' and date_str:
            # Setting to published - record the date and mark as previously published
            update_data['published_for_date'] = date_str
            update_data['previously_published'] = True
        elif status != 'published':
            # Changing away from published - clear the date and flag
            update_data['published_for_date'] = None
            update_data['previously_published'] = False

        service.pr_repo.update(url, update_data)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@publisher_bp.route('/publisher/unpublish', methods=['POST'])
def unpublish_article():
    """
    Reset a previously published article back to 'ready' status.

    This allows re-including an article that was published in a previous newsletter.
    Also clears the published_for_date so the article can appear in future newsletters.

    Request body (JSON):
        url: Press release URL

    Returns:
        JSON success response
    """
    data = request.get_json()
    url = data.get('url')
    logger.info(f"PUBLISHER: POST /publisher/unpublish | url={url[:50] if url else None}...")

    if not url:
        return jsonify({'success': False, 'error': 'Missing url'}), 400

    try:
        # Clear status, published_for_date, and previously_published flag
        service.pr_repo.update(url, {
            'newsletter_status': 'ready',
            'published_for_date': None,
            'previously_published': False,
            'included_in_newsletter': True
        })
        return jsonify({'success': True, 'message': 'Article unpublished and ready for inclusion'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@publisher_bp.route('/publisher/update-section', methods=['POST'])
def update_section():
    """
    Update newsletter section classification for a press release.

    Request body (JSON):
        url: Press release URL
        section: New section ('headline', 'financing', 'property', 'other', 'auto')

    Returns:
        JSON success response
    """
    data = request.get_json()
    url = data.get('url')
    section = data.get('section')
    logger.info(f"PUBLISHER: POST /publisher/update-section | url={url[:50] if url else None}... | section={section}")

    if not url or not section:
        return jsonify({'success': False, 'error': 'Missing url or section'}), 400

    success, error = service.update_newsletter_section(url, section)

    if success:
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': error}), 400


@publisher_bp.route('/publisher/update-disclosure-section', methods=['POST'])
def update_disclosure_section():
    """
    Update newsletter section for an SEC disclosure.

    Request body (JSON):
        filing_url: SEC filing URL
        section: New section ('headline', 'financing', 'property', 'earnings', 'other', 'auto')

    Returns:
        JSON success response
    """
    data = request.get_json()
    filing_url = data.get('filing_url')
    section = data.get('section')
    logger.info(f"PUBLISHER: POST /publisher/update-disclosure-section | filing_url={filing_url[:50] if filing_url else None}... | section={section}")

    if not filing_url or not section:
        return jsonify({'success': False, 'error': 'Missing filing_url or section'}), 400

    try:
        # 'auto' means use default (financing), store as None
        section_value = None if section == 'auto' else section
        service.disclosure_repo.update(filing_url, {'newsletter_section': section_value})
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@publisher_bp.route('/publisher/update-title', methods=['POST'])
def update_title():
    """
    Update newsletter display title for a press release.

    Request body (JSON):
        url: Press release URL
        title: New newsletter title (empty to clear)

    Returns:
        JSON success response
    """
    data = request.get_json()
    url = data.get('url')
    title = data.get('title', '')
    logger.info(f"PUBLISHER: POST /publisher/update-title | url={url[:50] if url else None}... | title={title[:30] if title else 'clear'}...")

    if not url:
        return jsonify({'success': False, 'error': 'Missing url'}), 400

    success, error = service.update_newsletter_title(url, title)

    if success:
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': error}), 400


# =============================================================================
# SEC Disclosure Status Management
# =============================================================================

@publisher_bp.route('/publisher/update-disclosure-status', methods=['POST'])
def update_disclosure_status():
    """
    Update newsletter status for an SEC disclosure.

    Request body (JSON):
        filing_url: SEC filing URL
        status: New status (ready, needs_review, published, excluded)
        date: Optional date string (YYYY-MM-DD) for published_for_date tracking

    Returns:
        JSON success response
    """
    data = request.get_json()
    filing_url = data.get('filing_url')
    status = data.get('status')
    date_str = data.get('date')
    logger.info(f"PUBLISHER: POST /publisher/update-disclosure-status | filing_url={filing_url[:50] if filing_url else None}... | status={status}")

    if not filing_url or not status:
        return jsonify({'success': False, 'error': 'Missing filing_url or status'}), 400

    try:
        # Build update data
        update_data = {'newsletter_status': status}

        # Handle published_for_date and previously_published based on status
        if status == 'published' and date_str:
            update_data['published_for_date'] = date_str
            update_data['previously_published'] = True
        elif status != 'published':
            update_data['published_for_date'] = None
            update_data['previously_published'] = False

        service.disclosure_repo.update(filing_url, update_data)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@publisher_bp.route('/publisher/delete-disclosure', methods=['POST'])
def delete_disclosure():
    """Permanently delete an SEC disclosure."""
    data = request.get_json()
    filing_url = data.get('filing_url')

    if not filing_url:
        return jsonify({'success': False, 'error': 'Missing filing_url'}), 400

    logger.info(f"PUBLISHER: POST /publisher/delete-disclosure | filing_url={filing_url[:50] if filing_url else None}...")

    try:
        success = service.disclosure_repo.hard_delete(filing_url)
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Delete failed'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


# =============================================================================
# Order Management (Session-based for MVP)
# =============================================================================

@publisher_bp.route('/publisher/update-order', methods=['POST'])
def update_order():
    """
    Save custom ordering for the current session.

    Request body (JSON):
        date: Date string (YYYY-MM-DD)
        urls: List of URLs in desired order

    Returns:
        JSON success response
    """
    data = request.get_json()
    date_str = data.get('date')
    url_order = data.get('urls', [])
    logger.info(f"PUBLISHER: POST /publisher/update-order | date={date_str} | urls={len(url_order)}")

    if not date_str:
        return jsonify({'success': False, 'error': 'Missing date'}), 400

    # Store in session
    session_key = f'publisher_order_{date_str}'
    session[session_key] = url_order

    return jsonify({'success': True})


# =============================================================================
# Mobile Form-Based Routes
# =============================================================================

@publisher_bp.route('/publisher/move', methods=['POST'])
def move_release():
    """
    Move a release up or down in the order (form-based for mobile).

    Form data:
        url: Press release URL
        direction: 'up' or 'down'
        date: Date string (YYYY-MM-DD)

    Returns:
        Redirect back to publisher page
    """
    url = request.form.get('url')
    direction = request.form.get('direction')
    date_str = request.form.get('date')
    logger.info(f"PUBLISHER: POST /publisher/move | direction={direction} | date={date_str}")

    if not url or not direction or not date_str:
        return redirect(url_for('publisher.publisher', date=date_str or ''))

    # Get current order from session (or initialize from releases)
    session_key = f'publisher_order_{date_str}'
    url_order = session.get(session_key)

    # If no session order, build from current releases
    if not url_order:
        try:
            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return redirect(url_for('publisher.publisher', date=date_str))

        releases = service.get_ready_releases_for_publisher(selected_date)
        url_order = [r.url for r in releases]

    # Perform the move
    if url in url_order:
        idx = url_order.index(url)
        if direction == 'up' and idx > 0:
            url_order[idx], url_order[idx - 1] = url_order[idx - 1], url_order[idx]
        elif direction == 'down' and idx < len(url_order) - 1:
            url_order[idx], url_order[idx + 1] = url_order[idx + 1], url_order[idx]
        session[session_key] = url_order

    return redirect(url_for('publisher.publisher', date=date_str))


@publisher_bp.route('/publisher/status-form', methods=['POST'])
def update_status_form():
    """
    Update status via form (mobile-friendly, no AJAX).

    Form data:
        url: Press release URL
        status: New status
        date: Date string (YYYY-MM-DD)

    Returns:
        Redirect back to publisher page
    """
    url = request.form.get('url')
    status = request.form.get('status')
    date_str = request.form.get('date')
    logger.info(f"PUBLISHER: POST /publisher/status-form | status={status} | date={date_str}")

    if url and status:
        if 'sec.gov' in url:
            # SEC disclosure - update disclosure repo
            update_data = {'newsletter_status': status}
            if status != 'published':
                update_data['published_for_date'] = None
            service.disclosure_repo.update(url, update_data)
        else:
            # Press release
            service.update_newsletter_status(url, status)

    return redirect(url_for('publisher.publisher', date=date_str or ''))


@publisher_bp.route('/publisher/section-form', methods=['POST'])
def update_section_form():
    """
    Update section via form (mobile-friendly, no AJAX).

    Form data:
        url: Press release URL
        section: New section ('headline', 'financing', 'property', 'other', 'auto')
        date: Date string (YYYY-MM-DD)

    Returns:
        Redirect back to publisher page
    """
    url = request.form.get('url')
    section = request.form.get('section')
    date_str = request.form.get('date')
    logger.info(f"PUBLISHER: POST /publisher/section-form | section={section} | date={date_str}")

    if url and section:
        section_value = None if section == 'auto' else section
        if 'sec.gov' in url:
            # SEC filing - update disclosure repo
            service.disclosure_repo.update(url, {'newsletter_section': section_value})
        else:
            # Press release
            service.update_newsletter_section(url, section)

    return redirect(url_for('publisher.publisher', date=date_str or ''))


@publisher_bp.route('/publisher/title-form', methods=['POST'])
def update_title_form():
    """
    Update newsletter title via form (mobile-friendly, no AJAX).

    Form data:
        url: Press release URL
        title: New newsletter title
        date: Date string (YYYY-MM-DD)

    Returns:
        Redirect back to publisher page
    """
    url = request.form.get('url')
    title = request.form.get('title', '')
    date_str = request.form.get('date')
    logger.info(f"PUBLISHER: POST /publisher/title-form | title={title[:30] if title else 'clear'}... | date={date_str}")

    if url:
        service.update_newsletter_title(url, title)

    return redirect(url_for('publisher.publisher', date=date_str or ''))


# =============================================================================
# Debug Endpoint
# =============================================================================

@publisher_bp.route('/publisher/debug')
def publisher_debug():
    """Debug endpoint showing publisher state for a date."""
    date_str = request.args.get('date')
    try:
        selected_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.now(ET).date()
    except ValueError:
        selected_date = datetime.now(ET).date()

    items = service.get_all_items_for_publisher(selected_date)
    counts = service.count_all_items_by_status(selected_date)

    logger.info(f"PUBLISHER: GET /publisher/debug | date={selected_date} | items={len(items)}")

    return jsonify({
        'date': selected_date.isoformat(),
        'time_window': service.format_time_window(selected_date),
        'counts': counts,
        'items': [{
            'url': i.url[:80],
            'ticker': getattr(i, 'ticker', 'SEC'),
            'status': i.newsletter_status,
            'section': getattr(i, 'newsletter_section', None),
            'published_for_date': i.published_for_date,
            'is_sec_filing': getattr(i, 'is_sec_filing', False)
        } for i in items]
    })
