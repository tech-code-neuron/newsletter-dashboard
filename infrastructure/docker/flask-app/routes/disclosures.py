"""
Disclosures Blueprint - 8-K SEC Filing Display

Simplified read-only interface:
- /disclosures - List view (ticker, date, title)
- /disclosures/<filing_url> - Detail view (title, summary, SEC link, related PR)

No editing, no duplication filtering - just display.
"""
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_wtf import FlaskForm  # For CSRF validation on form endpoint
from urllib.parse import unquote, quote

from services.disclosure_service import DisclosureService

# Blueprint setup
disclosures_bp = Blueprint('disclosures', __name__)

# Service instance
service = DisclosureService()


@disclosures_bp.route('/disclosures')
def disclosure_list():
    """
    List 8-K filings with simple filtering.

    Query params:
        days: Days to look back (default 7)
        page: Page number
    """
    days = request.args.get('days', 7, type=int)
    page = request.args.get('page', 1, type=int)
    per_page = 50

    # Get disclosures (simplified - no status filtering)
    disclosures, total = service.get_disclosures_for_list(
        days=days,
        page=page,
        per_page=per_page
    )

    # Calculate pagination
    total_pages = (total + per_page - 1) // per_page

    return render_template(
        'disclosures.html',
        disclosures=disclosures,
        days=days,
        page=page,
        total_pages=total_pages,
        total=total
    )


@disclosures_bp.route('/disclosures/<path:filing_url>')
def disclosure_detail(filing_url):
    """
    Detail view for a single disclosure.

    Shows: title, summary, SEC document link, related PR link
    """
    disclosure, matched_pr = service.get_disclosure_detail(filing_url)

    if not disclosure:
        return render_template('404.html', message='Disclosure not found'), 404

    return render_template(
        'disclosure_detail.html',
        disclosure=disclosure,
        matched_pr=matched_pr
    )


@disclosures_bp.route('/disclosures/update-title', methods=['POST'])
def update_disclosure_title():
    """
    AJAX endpoint to update disclosure title.

    Request body (JSON):
        filing_url: Filing URL (primary key)
        title: New title (empty to clear)

    Returns:
        JSON {success: bool, error?: string}
    """
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Missing JSON body'}), 400

    filing_url = data.get('filing_url')
    title = data.get('title', '').strip()

    if not filing_url:
        return jsonify({'success': False, 'error': 'Missing filing_url'}), 400

    success, error = service.update_disclosure_title(filing_url, title)

    if success:
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': error}), 400


@disclosures_bp.route('/disclosures/update-title-form', methods=['POST'])
def update_disclosure_title_form():
    """
    Form endpoint for mobile (non-AJAX) title update.

    Form data:
        filing_url: Filing URL (primary key)
        title: New title

    Returns:
        Redirect back to disclosure detail
    """
    filing_url = request.form.get('filing_url')
    title = request.form.get('title', '').strip()

    if not filing_url:
        flash('Missing filing URL', 'error')
        return redirect(url_for('disclosures.disclosure_list'))

    success, error = service.update_disclosure_title(filing_url, title)

    if not success:
        flash(f'Error updating title: {error}', 'error')
    else:
        flash('Title updated successfully', 'success')

    # Redirect back to detail page
    return redirect(url_for('disclosures.disclosure_detail', filing_url=quote(filing_url, safe='')))
