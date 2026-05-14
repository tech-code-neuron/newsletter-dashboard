"""
Publisher Email & V2 Publishing Routes

Routes:
- /send - Send newsletter via email (SES)
- /check-duplicates - Check for duplicate articles
- /publish-v2 - Publish edition to DynamoDB
- /save-draft, /get-draft, /delete-draft - Draft management
- /unpublish - Rollback published edition
"""
import boto3
import logging
import uuid
from datetime import datetime, timedelta
from typing import List, Optional
from flask import Blueprint, jsonify, request, render_template
from zoneinfo import ZoneInfo
from routes.auth_decorators import login_required
from services.publisher_service import get_publisher_service, apply_url_ordering, create_section_getter
from services.email_sender_service import get_email_sender_service
from config.email_styles import EMAIL_STYLES
from config.site_config import get_public_config
from config.newsletter_status import categorize_releases_for_template
from config.section_config import SECTIONS, SECTION_DYNAMO_KEYS
from config.company import COMPANY_ADDRESS

logger = logging.getLogger(__name__)

bp = Blueprint('publisher_email', __name__, url_prefix='/publisher/email')

# Email configuration
RECIPIENT_EMAIL = 'your-email@your-domain.com'
SENDER_EMAIL = 'alerts@your-domain.com'  # Verified in SES (same as email-forwarder)

ET = ZoneInfo('America/New_York')


def get_recent_newsletters(days: int = 7) -> List[dict]:
    """
    Get recently published newsletters with their included URLs.

    Args:
        days: Number of days to look back (default 7)

    Returns:
        List of newsletter metadata dicts
    """
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    table = dynamodb.Table('reitsheet-newsletters')

    cutoff = (datetime.now(ET) - timedelta(days=days)).strftime('%Y-%m-%d')

    try:
        # Scan for published newsletters since cutoff
        response = table.scan(
            FilterExpression='#status = :status AND #date >= :cutoff',
            ExpressionAttributeNames={'#status': 'status', '#date': 'date'},
            ExpressionAttributeValues={':status': 'published', ':cutoff': cutoff}
        )
        return response.get('Items', [])
    except Exception as e:
        logger.warning(f"Could not get recent newsletters: {e}")
        return []


@bp.route('/send', methods=['POST'])
@login_required
def send_newsletter():
    """
    Send newsletter to email.

    Request body (JSON):
        date: Date string (YYYY-MM-DD)
        urls: List of URLs in display order
        mode: 'test' (default) or 'subscribers'

    Returns:
        JSON success/error response
    """
    try:
        data = request.get_json()
        date_str = data.get('date')
        url_order = data.get('urls', [])
        mode = data.get('mode', 'test')  # 'test' or 'subscribers'

        # Parse date
        try:
            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.now(ET).date()
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid date format'}), 400

        # Get all items (press releases + SEC filings)
        service = get_publisher_service()
        all_items = service.get_all_items_for_publisher(selected_date)

        # Filter to include 'ready' items AND same-day published items (allows republishing)
        selected_date_str = selected_date.isoformat()
        releases = [
            r for r in all_items
            if (r.newsletter_status or 'ready') == 'ready'
            or (r.newsletter_status == 'published' and r.published_for_date == selected_date_str)
        ]

        if not releases:
            return jsonify({'success': False, 'error': 'No press releases found for this date'}), 404

        # Reorder based on provided order (preserves ALL releases)
        ordered_releases = apply_url_ordering(releases, url_order)

        # Generate HTML using Jinja2 template (matches homepage design)
        section_getter = create_section_getter(service)
        title_getter = service.get_display_title

        # Categorize releases into sections for template
        sections_raw = categorize_releases_for_template(
            ordered_releases,
            section_getter,
            title_getter
        )

        # Build section_data dict (internal_key -> items) matching home.html pattern
        section_data = {
            key: sections_raw.get(SECTION_DYNAMO_KEYS[key], [])
            for key in [s[0] for s in SECTIONS]
        }

        # Use today's date (ET) for email display - matches homepage approach
        # selected_date still controls which releases to include
        email_date = datetime.now(ET).date()

        # Pre-format date in Python to avoid template filter timezone bug
        # (filter assumes UTC, converting April 10 00:00 UTC → April 9 20:00 ET)
        date_formatted = email_date.strftime('%A, %B %-d, %Y')

        # Build edition object for template (minimal - sections handled separately)
        edition = {
            'date': email_date.strftime('%Y-%m-%d'),  # String for any other template use
        }

        # Render email using Jinja2 template (dynamic sections like home.html)
        html = render_template(
            'newsletter/email.html',
            config=get_public_config(),
            styles=EMAIL_STYLES,
            edition=edition,
            sections=SECTIONS,
            section_data=section_data,
            company_address=COMPANY_ADDRESS,
            date_formatted=date_formatted  # Pre-formatted date for display
        )
        subject = f"The Press Release Pipeline - {date_formatted}"

        # Generate campaign ID for tracking
        campaign_id = str(uuid.uuid4())

        # Get email sender service
        email_service = get_email_sender_service()

        if mode == 'subscribers':
            # Send to all verified subscribers
            result = email_service.send_newsletter(
                campaign_id=campaign_id,
                subject=subject,
                html_content=html,
                test_mode=False
            )

            # Build response message that clearly shows success/failure
            if result['failed'] > 0:
                if result['successful'] == 0:
                    # All failed - this is an error
                    return jsonify({
                        'success': False,
                        'error': f"All {result['failed']} emails failed to send. Check server logs.",
                        'campaign_id': campaign_id,
                        'total': result['total_recipients'],
                        'successful': result['successful'],
                        'failed': result['failed']
                    }), 500
                else:
                    # Partial failure - warn but still success
                    message = f"Sent to {result['successful']}/{result['total_recipients']} subscribers ({result['failed']} failed)"
            else:
                message = f"Sent to {result['successful']} subscriber(s)"

            return jsonify({
                'success': True,
                'message': message,
                'campaign_id': campaign_id,
                'total': result['total_recipients'],
                'successful': result['successful'],
                'failed': result['failed']
            })
        else:
            # Test mode - send to test recipient only
            result = email_service.send_newsletter(
                campaign_id=campaign_id,
                subject=subject,
                html_content=html,
                test_mode=True,
                test_recipients=[RECIPIENT_EMAIL]
            )
            return jsonify({
                'success': True,
                'message': f'Test sent to {RECIPIENT_EMAIL}',
                'campaign_id': campaign_id
            })

    except Exception as e:
        logger.error(f"Error sending newsletter: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/check-duplicates', methods=['POST'])
@login_required
def check_duplicates():
    """
    Check for duplicate articles between current publish and recent archives.

    This helps prevent publishing articles that already appear in recent archives.

    Request body (JSON):
        date: Date string (YYYY-MM-DD) of newsletter being published
        urls: List of URLs to be published

    Returns:
        JSON with duplicate information:
        {
            success: bool,
            has_duplicates: bool,
            duplicates: [
                {
                    archive_date: str,
                    archive_url: str,
                    overlapping_articles: [{url: str, title: str}]
                }
            ]
        }
    """
    try:
        data = request.get_json()
        date_str = data.get('date')
        urls_to_publish = set(data.get('urls', []))

        if not urls_to_publish:
            return jsonify({'success': True, 'has_duplicates': False, 'duplicates': []})

        # Get recent newsletters (last 7 days)
        duplicates = []
        recent = get_recent_newsletters(days=7)

        service = get_publisher_service()

        for newsletter in recent:
            if newsletter.get('date') == date_str:
                continue  # Skip current date

            archived_urls = set(newsletter.get('included_urls', []))
            overlap = urls_to_publish & archived_urls

            if overlap:
                # Get titles for the overlapping URLs
                overlap_details = []
                for url in overlap:
                    release = service.pr_repo.get_by_url(url)
                    if release:
                        overlap_details.append({
                            'url': url,
                            'title': service.get_display_title(release)
                        })

                duplicates.append({
                    'archive_date': newsletter.get('date'),
                    'archive_url': newsletter.get('archive_url'),
                    'overlapping_articles': overlap_details
                })

        return jsonify({
            'success': True,
            'has_duplicates': len(duplicates) > 0,
            'duplicates': duplicates
        })

    except Exception as e:
        logger.error(f"Error checking duplicates: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# V2 Endpoints - Simplified Publishing (No S3/CloudFront)
# =============================================================================

@bp.route('/publish-v2', methods=['POST'])
@login_required
def publish_v2():
    """
    Publish newsletter using the simplified 3-step process.

    This replaces the old 11-step cascade (S3, CloudFront, archive regeneration)
    with a clean database-only workflow:
    1. Save edition to reitsheet-newsletter-editions
    2. Mark items as published in their source tables
    3. Done

    Request body (JSON):
        date: Date string (YYYY-MM-DD)
        urls: List of URLs in display order
        headline: Optional headline text (defaults to first headline item)

    Returns:
        JSON with success, edition metadata, items_published
    """
    from services.newsletter_publisher import get_newsletter_publisher
    from services.publisher_service import get_publisher_service

    try:
        data = request.get_json()
        date_str = data.get('date')
        url_order = data.get('urls', [])
        headline = data.get('headline')

        # Parse date
        try:
            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.now(ET).date()
            date_str = selected_date.isoformat()
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid date format'}), 400

        # Get publisher service for item fetching
        service = get_publisher_service()
        all_items = service.get_all_items_for_publisher(selected_date)

        # Filter to include 'ready' items AND same-day published items (allows republishing)
        releases = [
            r for r in all_items
            if (r.newsletter_status or 'ready') == 'ready'
            or (r.newsletter_status == 'published' and r.published_for_date == date_str)
        ]

        if not releases:
            return jsonify({'success': False, 'error': 'No press releases found for this date'}), 404

        # Reorder based on provided order (preserves ALL releases)
        ordered_releases = apply_url_ordering(releases, url_order)

        # Convert DTOs to dicts for storage
        title_getter = service.get_display_title
        section_getter = create_section_getter(service)

        items = []
        sections = {}

        for r in ordered_releases:
            section = section_getter(r)
            # Use sec_url for SEC filings (returns actual document URL, not index.htm)
            item = {
                'url': getattr(r, 'sec_url', None) or r.url,
                'ticker': r.ticker,
                'title': title_getter(r),
                'company_name': r.company.name if hasattr(r, 'company') and r.company else '',
                'section': section,
                'is_sec_filing': getattr(r, 'is_sec_filing', False),
                'is_public': r.company.is_public if hasattr(r, 'company') and r.company and hasattr(r.company, 'is_public') else True,
                'lead_sponsor': getattr(r.company, 'lead_sponsor', '') if hasattr(r, 'company') and r.company else ''
            }
            items.append(item)

            # Group into sections
            if section not in sections:
                sections[section] = []
            sections[section].append(item)

        # Publish using the new simplified publisher
        publisher = get_newsletter_publisher()
        result = publisher.publish(date_str, items, sections, headline)

        if result['success']:
            # Invalidate newsletter service cache so navigation reflects new edition
            from services.newsletter_service import get_newsletter_service
            newsletter_service = get_newsletter_service()
            newsletter_service.invalidate_cache()

            return jsonify({
                'success': True,
                'message': f"Published newsletter with {result['items_published']} items",
                'edition': result['edition'],
                'items_published': result['items_published']
            })
        else:
            return jsonify({'success': False, 'error': result.get('error', 'Unknown error')}), 500

    except Exception as e:
        logger.error(f"Error in publish-v2: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/save-draft', methods=['POST'])
@login_required
def save_draft():
    """
    Save newsletter as draft without publishing.

    Drafts can be edited and republished later.

    Request body (JSON):
        date: Date string (YYYY-MM-DD)
        urls: List of URLs in display order
        headline: Optional headline text

    Returns:
        JSON with success, edition metadata
    """
    from services.newsletter_publisher import get_newsletter_publisher
    from services.publisher_service import get_publisher_service

    try:
        data = request.get_json()
        date_str = data.get('date')
        url_order = data.get('urls', [])
        headline = data.get('headline')

        # Parse date
        try:
            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.now(ET).date()
            date_str = selected_date.isoformat()
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid date format'}), 400

        # Get publisher service for item fetching
        service = get_publisher_service()
        all_items = service.get_all_items_for_publisher(selected_date)

        # Filter to ready items
        releases = [
            r for r in all_items
            if (r.newsletter_status or 'ready') == 'ready'
        ]

        if not releases:
            return jsonify({'success': False, 'error': 'No press releases found for this date'}), 404

        # Reorder based on provided order (preserves ALL releases)
        ordered_releases = apply_url_ordering(releases, url_order)

        # Convert DTOs to dicts
        title_getter = service.get_display_title
        section_getter = create_section_getter(service)

        items = []
        sections = {}

        for r in ordered_releases:
            section = section_getter(r)
            # Use sec_url for SEC filings (returns actual document URL, not index.htm)
            item = {
                'url': getattr(r, 'sec_url', None) or r.url,
                'ticker': r.ticker,
                'title': title_getter(r),
                'company_name': r.company.name if hasattr(r, 'company') and r.company else '',
                'section': section,
                'is_sec_filing': getattr(r, 'is_sec_filing', False),
                'is_public': r.company.is_public if hasattr(r, 'company') and r.company and hasattr(r.company, 'is_public') else True,
                'lead_sponsor': getattr(r.company, 'lead_sponsor', '') if hasattr(r, 'company') and r.company else ''
            }
            items.append(item)

            if section not in sections:
                sections[section] = []
            sections[section].append(item)

        # Save draft
        publisher = get_newsletter_publisher()
        result = publisher.save_draft(date_str, items, sections, headline)

        if result['success']:
            return jsonify({
                'success': True,
                'message': f"Saved draft with {len(items)} items",
                'edition': result['edition']
            })
        else:
            return jsonify({'success': False, 'error': result.get('error', 'Unknown error')}), 500

    except Exception as e:
        logger.error(f"Error saving draft: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/get-draft/<date>', methods=['GET'])
@login_required
def get_draft(date: str):
    """
    Get a saved draft for a specific date.

    Args:
        date: Date string (YYYY-MM-DD)

    Returns:
        JSON with draft data or 404 if not found
    """
    from services.newsletter_publisher import get_newsletter_publisher

    try:
        publisher = get_newsletter_publisher()
        draft = publisher.get_draft(date)

        if draft:
            return jsonify({
                'success': True,
                'draft': draft
            })
        else:
            return jsonify({'success': False, 'error': 'Draft not found'}), 404

    except Exception as e:
        logger.error(f"Error getting draft {date}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/delete-draft/<date>', methods=['DELETE'])
@login_required
def delete_draft(date: str):
    """
    Delete a saved draft.

    Args:
        date: Date string (YYYY-MM-DD)

    Returns:
        JSON with success/error
    """
    from services.newsletter_publisher import get_newsletter_publisher

    try:
        publisher = get_newsletter_publisher()
        deleted = publisher.delete_draft(date)

        if deleted:
            return jsonify({
                'success': True,
                'message': f'Draft {date} deleted'
            })
        else:
            return jsonify({'success': False, 'error': 'Draft not found or not a draft'}), 404

    except Exception as e:
        logger.error(f"Error deleting draft {date}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/unpublish/<date>', methods=['POST'])
@login_required
def unpublish(date: str):
    """
    Unpublish an edition, reverting items to 'ready' status.

    This is a rollback operation - use with caution.

    Args:
        date: Date string (YYYY-MM-DD)

    Returns:
        JSON with success, items_reverted
    """
    from services.newsletter_publisher import get_newsletter_publisher

    try:
        publisher = get_newsletter_publisher()
        result = publisher.unpublish(date)

        if result['success']:
            # Invalidate cache
            from services.newsletter_service import get_newsletter_service
            newsletter_service = get_newsletter_service()
            newsletter_service.invalidate_cache()

            return jsonify({
                'success': True,
                'message': f"Unpublished edition {date}, reverted {result['items_reverted']} items",
                'items_reverted': result['items_reverted']
            })
        else:
            return jsonify({'success': False, 'error': result.get('error', 'Unknown error')}), 500

    except Exception as e:
        logger.error(f"Error unpublishing {date}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
