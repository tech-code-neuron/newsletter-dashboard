"""
Email Routes - Email viewer interface

SOLID Principles:
- Single Responsibility: HTTP handling only
- Dependency Inversion: Depends on EmailService abstraction

Routes:
- GET /emails - Email list with filters
- GET /emails/<email_id> - Email detail (AJAX/JSON)
- GET /emails/<email_id>/raw - Download raw email
"""
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, session
from datetime import datetime, timedelta, timezone
import logging

from services.email_service import get_email_service
from utils.datetime_utils import TIMEZONE_EASTERN, TIMEZONE_UTC

logger = logging.getLogger(__name__)

# Blueprint configuration
emails_bp = Blueprint('emails', __name__)

# Get service instance
service = get_email_service()


@emails_bp.route('/emails')
def email_list():
    """
    Email list page with filters and search.

    Query params:
        start_date: YYYY-MM-DD (default: 7 days ago)
        end_date: YYYY-MM-DD (default: today)
        search: Search query
        status: Filter by pipeline status ('failed', 'stuck', 'all')
        continuation: S3 continuation token for pagination
    """
    # Parse date filters from query params
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=7)

    if request.args.get('start_date'):
        try:
            # Interpret as Eastern Time (user's timezone), start of day
            start_date = datetime.strptime(request.args['start_date'], '%Y-%m-%d')
            start_date = start_date.replace(hour=0, minute=0, second=0, tzinfo=TIMEZONE_EASTERN)
            start_date = start_date.astimezone(TIMEZONE_UTC)
        except ValueError:
            pass

    if request.args.get('end_date'):
        try:
            # Interpret as Eastern Time, end of day
            end_date = datetime.strptime(request.args['end_date'], '%Y-%m-%d')
            end_date = end_date.replace(hour=23, minute=59, second=59, tzinfo=TIMEZONE_EASTERN)
            end_date = end_date.astimezone(TIMEZONE_UTC)
        except ValueError:
            pass

    search_query = request.args.get('search', '').strip()
    status_filter = request.args.get('status', '').strip()
    continuation_token = request.args.get('continuation')

    # Get failed/stuck emails from tracking table
    failed_stuck_map = {}
    pipeline_stats = {}
    try:
        failed_stuck_map = service.get_failed_and_stuck_emails(hours=72)
        pipeline_stats = service.get_pipeline_stats(hours=24)
    except Exception as e:
        logger.warning(f"Error getting pipeline status: {e}")

    # Get emails from service
    try:
        data = service.get_emails_for_display(
            start_date=start_date,
            end_date=end_date,
            search_query=search_query,
            continuation_token=continuation_token,
            limit=50
        )
    except Exception as e:
        logger.error(f"Error getting emails: {e}")
        data = {
            'emails': [],
            'total_count': 0,
            'has_more': False,
            'next_token': None,
            'filters': {
                'start_date': start_date,
                'end_date': end_date,
                'search_query': search_query
            },
            'error': str(e)
        }

    # Enrich emails with pipeline status
    for email in data['emails']:
        # Try to match by message_id or subject+ticker
        email.pipeline_status = None
        for key, info in failed_stuck_map.items():
            # Match by subject (rough match)
            if info.get('subject') and email.subject and info['subject'][:50] in email.subject:
                email.pipeline_status = info
                break
            # Match by ticker if available
            if info.get('ticker') and email.ticker and info['ticker'] == email.ticker:
                if info.get('subject') and email.subject[:30] in info['subject']:
                    email.pipeline_status = info
                    break

    # Filter by status if requested
    if status_filter in ['failed', 'stuck']:
        data['emails'] = [e for e in data['emails'] if e.pipeline_status and e.pipeline_status.get('status') == status_filter]
        data['total_count'] = len(data['emails'])
    elif status_filter == 'problems':
        data['emails'] = [e for e in data['emails'] if e.pipeline_status]
        data['total_count'] = len(data['emails'])

    # Count problems
    problem_count = len([e for e in data['emails'] if e.pipeline_status]) if status_filter != 'problems' else data['total_count']

    # Store continuation token in session for "Load More" button
    if data.get('next_token'):
        session['email_list_continuation'] = data['next_token']

    logger.info(f"Rendering template with {len(data['emails'])} emails")

    return render_template(
        'emails.html',
        emails=data['emails'],
        total_count=data['total_count'],
        has_more=data.get('has_more', False),
        next_token=data.get('next_token'),
        filters=data['filters'],
        status_filter=status_filter,
        pipeline_stats=pipeline_stats,
        problem_count=problem_count,
        error=data.get('error')
    )


@emails_bp.route('/emails/<path:email_id>')
def email_detail(email_id: str):
    """
    Get single email detail (AJAX endpoint for modal).

    Returns JSON:
        - metadata: {from, date, subject, message_id, headers}
        - body_html: HTML body content
        - body_text: Plain text fallback
        - raw_url: S3 download URL
    """
    # Get email from service
    email_dto = service.get_email_by_id(email_id)

    if not email_dto:
        return jsonify({
            'error': 'Email not found'
        }), 404

    # Generate presigned download URL
    raw_url = service.generate_presigned_download_url(email_id)

    # Build response
    response = {
        'id': email_dto.id,
        'metadata': {
            'message_id': email_dto.message_id,
            'subject': email_dto.subject,
            'from': email_dto.display_from,
            'from_email': email_dto.from_email,
            'from_domain': email_dto.from_domain,
            'to': email_dto.to_header,
            'date': email_dto.display_date.isoformat() if email_dto.display_date else None,
            'date_display': email_dto.display_date.strftime('%B %d, %Y at %I:%M %p %Z') if email_dto.display_date else 'Unknown',
            'size': email_dto.size_kb,
            'ticker': email_dto.ticker,
            'has_attachments': email_dto.has_attachments,
            'attachment_count': email_dto.attachment_count,
        },
        'body_html': email_dto.body_html,
        'body_text': email_dto.body_text,
        'has_html': email_dto.has_html,
        'raw_url': raw_url,
        'headers': email_dto.headers
    }

    return jsonify(response)


@emails_bp.route('/emails/<path:email_id>/preview')
def email_preview(email_id: str):
    """
    Render email HTML for iframe display.
    Matches publisher.py pattern for robust iframe loading.

    Returns:
        HTML content for iframe rendering
    """
    email_dto = service.get_email_by_id(email_id)

    if not email_dto:
        return '<p>Email not found</p>', 404

    # Return raw HTML (browser renders in iframe)
    return email_dto.body_html or email_dto.body_text or '<p>No content</p>'


@emails_bp.route('/emails/<path:email_id>/raw')
def email_raw(email_id: str):
    """
    Download raw email file from S3.

    Returns:
        Redirect to S3 presigned URL (expires in 5 minutes)
    """
    # Generate presigned URL
    url = service.generate_presigned_download_url(email_id, expires_in=300)

    if not url:
        return jsonify({
            'error': 'Email not found or error generating download URL'
        }), 404

    # Redirect to presigned URL
    return redirect(url)
