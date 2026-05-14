"""
Review Emails Blueprint - Email Review System Routes

Single Responsibility: Handles email review, Gmail scanning, and email-to-press-release conversion

Routes:
- GET  /review-emails                                    → Display email review dashboard
- POST /api/review/<int:review_id>/add-to-press-releases → Convert review email to press release
- POST /api/review/<int:review_id>/delete                → Delete email from Gmail and database
- POST /api/review/scan-inbox                            → Start Gmail inbox scan
- GET  /api/review/scan-progress                         → Get scan progress status
- POST /api/review/scan-abort                            → Abort current scan
- GET  /api/review/<int:review_id>/html                  → Get sanitized email HTML content

Uses Repository Pattern for database abstraction (DynamoDB in ECS, SQLite local).
"""
from flask import Blueprint, render_template, request, jsonify, make_response
import threading
import email as email_lib

from core.repositories import get_review_email_repo
from services.review_email_service import ReviewEmailService
from services.gmail_scan_service import GmailScanService
from services.scan_manager import get_scan_manager
from utils.review_constants import ReviewEmailErrors, ReviewEmailStatus
from utils.html_sanitizer import sanitize_email_html

# Create blueprint
review_emails_bp = Blueprint('review_emails', __name__)

# Constants for email display
EMAIL_PLAIN_TEXT_WRAPPER = '<pre style="font-family: sans-serif; white-space: pre-wrap; padding: 20px;">{content}</pre>'
EMAIL_NO_CONTENT_MESSAGE = '<p style="padding: 20px;">No content available</p>'
EMAIL_CSP_HEADER = "default-src 'none'; style-src 'unsafe-inline'; img-src 'none';"

# Scan manager instance (singleton)
scan_manager = get_scan_manager()


@review_emails_bp.route('/review-emails')
def review_emails():
    """Display emails flagged for review"""
    repo = get_review_email_repo()
    review_emails = repo.get_pending()
    return render_template('review_emails.html', review_emails=review_emails)


@review_emails_bp.route('/api/review/<int:review_id>/add-to-press-releases', methods=['POST'])
def add_review_to_press_releases(review_id):
    """
    Extract PR URL from review email and add to press releases.
    Runs scraper in background - does not block.

    REFACTORED: Clean separation - delegates to ReviewEmailService.process_review_in_background()
    """
    repo = get_review_email_repo()
    review = repo.get_by_id(review_id)

    # Validate review can be processed
    if not review:
        return jsonify({'success': False, 'error': ReviewEmailErrors.NOT_FOUND}), 404

    if review.status != ReviewEmailStatus.PENDING:
        return jsonify({'success': False, 'error': ReviewEmailErrors.ALREADY_PROCESSING.format(status=review.status)}), 400

    # Update status to processing
    repo.update_status(review_id, ReviewEmailStatus.PROCESSING)

    # Start background thread (delegates to service layer)
    thread = threading.Thread(
        target=ReviewEmailService.process_review_in_background,
        args=(review_id,)
    )
    thread.daemon = True
    thread.start()

    return jsonify({
        'success': True,
        'message': 'Processing in background. Page will update when complete.'
    })


@review_emails_bp.route('/api/review/<int:review_id>/delete', methods=['POST'])
def delete_review_email(review_id):
    """
    Delete email from Gmail inbox and remove from review database.
    If already deleted from Gmail, just remove from database.

    REFACTORED: Now uses ReviewEmailService for clean separation.
    """
    repo = get_review_email_repo()
    review = repo.get_by_id(review_id)

    if not review:
        return jsonify({'success': False, 'error': ReviewEmailErrors.NOT_FOUND}), 404

    # Try to delete from Gmail
    gmail_deleted = ReviewEmailService.delete_from_gmail(review.gmail_message_id)

    # Delete screenshot and mark as deleted
    ReviewEmailService.cleanup_review_resources(review)
    repo.update_status(review_id, ReviewEmailStatus.DELETED)

    return jsonify({
        'success': True,
        'gmail_deleted': gmail_deleted,
        'message': 'Email removed from review'
    })


@review_emails_bp.route('/api/review/scan-inbox', methods=['POST'])
def scan_inbox_for_review():
    """
    Start Gmail inbox scan in background with progress tracking.

    REFACTORED: Clean separation - delegates to GmailScanService.execute_scan()
    """
    # Check if scan already in progress
    if scan_manager.is_active():
        return jsonify({'success': False, 'error': ReviewEmailErrors.SCAN_IN_PROGRESS}), 400

    # Get time range filter
    time_range = request.json.get('range', 'all') if request.is_json else 'all'

    # Start new scan
    scan_manager.start_scan(time_range)

    # Start scan in background thread (delegates to service layer)
    thread = threading.Thread(
        target=GmailScanService.execute_scan,
        args=(time_range, scan_manager)
    )
    thread.daemon = True
    thread.start()

    return jsonify({'success': True, 'message': 'Scan started'})


@review_emails_bp.route('/api/review/scan-progress', methods=['GET'])
def get_scan_progress():
    """
    Get current scan progress.

    REFACTORED: Now uses ScanManager for thread-safe access.
    """
    progress = scan_manager.get_progress()
    return jsonify(progress)


@review_emails_bp.route('/api/review/scan-abort', methods=['POST'])
def abort_scan():
    """
    Abort current scan.

    REFACTORED: Now uses ScanManager.
    """
    if not scan_manager.is_active():
        return jsonify({'success': False, 'error': ReviewEmailErrors.NO_SCAN_IN_PROGRESS}), 400

    scan_manager.request_abort()
    return jsonify({'success': True, 'message': 'Aborting scan...'})


@review_emails_bp.route('/api/review/<int:review_id>/html', methods=['GET'])
def get_review_email_html(review_id):
    """Get HTML content of review email for modal display (sanitized)"""
    repo = get_review_email_repo()
    review = repo.get_by_id(review_id)

    if not review:
        return jsonify({'success': False, 'error': ReviewEmailErrors.NOT_FOUND}), 404

    try:
        # Parse raw email to extract HTML
        msg = email_lib.message_from_string(review.raw_email)

        html_content = None
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == 'text/html':
                    html_content = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    break
        else:
            if msg.get_content_type() == 'text/html':
                html_content = msg.get_payload(decode=True).decode('utf-8', errors='ignore')

        if not html_content:
            # Fallback to plain text if no HTML
            plain_text = None
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == 'text/plain':
                        plain_text = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                        break
            else:
                plain_text = msg.get_payload(decode=True).decode('utf-8', errors='ignore')

            if plain_text:
                # Escape HTML in plain text
                plain_text = plain_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                html_content = EMAIL_PLAIN_TEXT_WRAPPER.format(content=plain_text)

        # SECURITY: Sanitize HTML before sending to iframe
        if html_content:
            html_content = sanitize_email_html(html_content)

        response = make_response(jsonify({
            'success': True,
            'html': html_content or EMAIL_NO_CONTENT_MESSAGE
        }))

        # SECURITY: Content Security Policy - block ALL external resources
        response.headers['Content-Security-Policy'] = EMAIL_CSP_HEADER

        return response

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
