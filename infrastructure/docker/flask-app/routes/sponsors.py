"""
Sponsors Blueprint - Admin UI for sponsor management

Provides:
- List view of all canonical sponsors with usage counts
- Detection of non-canonical sponsors in database
- Migration preview page
- Rename sponsor across all companies
- JSON API for autocomplete
"""
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for

from services.sponsor_service import get_sponsor_service
from config.sponsors import SPONSORS, get_canonical_sponsor
from forms.sponsor_forms import RenameSponsorForm

sponsors_bp = Blueprint('sponsors', __name__)


@sponsors_bp.route('/sponsors')
def sponsors():
    """
    List all sponsors with usage statistics.

    Shows:
    - Canonical sponsors sorted by usage count
    - Warning panel for non-canonical sponsors found in database
    - Link to migration preview
    """
    service = get_sponsor_service()
    data = service.get_sponsors_for_display()

    return render_template('sponsors.html', **data)


@sponsors_bp.route('/sponsors/rename', methods=['POST'])
def rename_sponsor():
    """
    Rename a sponsor across all companies.

    Uses Flask-WTF form for CSRF protection and validation.
    """
    form = RenameSponsorForm()

    if not form.validate_on_submit():
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{error}', 'error')
        return redirect(url_for('sponsors.sponsors'))

    old_name = form.old_name.data.strip()
    new_name = form.new_name.data.strip()

    if old_name == new_name:
        flash('New name must be different from old name', 'error')
        return redirect(url_for('sponsors.sponsors'))

    service = get_sponsor_service()
    result = service.rename_sponsor(old_name, new_name)

    count = len(result['updated_tickers'])
    if count > 0:
        flash(f'Renamed "{old_name}" to "{new_name}" ({count} companies updated)', 'success')
    else:
        flash(f'No companies found with sponsor "{old_name}"', 'warning')

    return redirect(url_for('sponsors.sponsors'))


@sponsors_bp.route('/sponsors/preview-migration')
def preview_migration():
    """
    Preview what the migration script would change.

    Shows all companies with non-canonical sponsor values
    and what they would be changed to.
    """
    service = get_sponsor_service()
    changes = service.preview_migration()

    return render_template('sponsors_preview.html',
        changes=changes,
        change_count=len(changes),
        company_count=len(set(c['ticker'] for c in changes))
    )


@sponsors_bp.route('/api/sponsors')
def api_sponsors():
    """
    JSON API endpoint for sponsor list.

    Used by autocomplete in company forms.

    Query params:
        q: Search query (optional)
        limit: Max results (default 20)
    """
    query = request.args.get('q', '').strip()
    limit = request.args.get('limit', 20, type=int)

    if query:
        service = get_sponsor_service()
        results = service.search_sponsors(query, limit=limit)
    else:
        # Return all sponsors if no query
        results = sorted(SPONSORS)[:limit]

    return jsonify(results)


@sponsors_bp.route('/api/sponsors/canonical')
def api_canonical():
    """
    Get canonical name for a sponsor.

    Used by form validation to suggest corrections.

    Query params:
        name: Sponsor name to check

    Returns:
        JSON with canonical name and whether it was mapped
    """
    name = request.args.get('name', '').strip()
    canonical = get_canonical_sponsor(name)

    return jsonify({
        'original': name,
        'canonical': canonical,
        'is_mapped': canonical != name and bool(name),
        'is_canonical': canonical == name and bool(name)
    })
