"""
Companies Blueprint - Thin Controllers (REFACTORED)

SOLID Principles:
- Single Responsibility: HTTP handling only
- Dependency Inversion: Depends on CompanyService abstraction
- Open/Closed: Business logic changes don't affect routes

Architecture:
Routes → CompanyService → Repositories → Database
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify

from services.company_service import get_company_service
from services.sponsor_service import get_sponsor_service
from forms.company_forms import AddCompanyForm, EditCompanyForm
from utils.form_validator import process_company_form_data, get_platform_options
from config.sectors import SECTORS
from config.sponsors import SPONSOR_ALIASES

def get_sector_choices():
    """
    Get sector choices from canonical list (single source of truth).

    Uses config/sectors.py instead of querying database to ensure:
    - Consistent dropdown options across all forms
    - No duplicates from database inconsistencies
    - Predictable ordering (alphabetical)
    """
    choices = [('', 'Select Sector')]
    choices.extend([(s, s) for s in SECTORS])
    return choices

# Blueprint configuration
companies_bp = Blueprint('companies', __name__)

# Get service instance
service = get_company_service()


# =============================================================================
# LIST & SEARCH
# =============================================================================

@companies_bp.route('/companies')
def companies():
    """
    Display all companies with search, sort, and status filtering.

    Query parameters:
        - search: Search query
        - sort: Sort by field (ticker, name, sector, source, emails)
        - order: Sort order (asc, desc)
    """
    search = request.args.get('search', '')
    sort_by = request.args.get('sort', 'ticker')
    order = request.args.get('order', 'asc')

    # Get data from service
    data = service.get_companies_for_display(
        search=search,
        sort_by=sort_by,
        order=order
    )

    return render_template('companies.html', **data)


# =============================================================================
# DETAIL PAGE
# =============================================================================

@companies_bp.route('/company/<ticker>')
def company_detail(ticker):
    """
    Company detail page with recent press releases.

    Args:
        ticker: Company ticker symbol
    """
    data = service.get_company_with_releases(ticker)

    if not data:
        flash(f'Company not found: {ticker}', 'error')
        return redirect(url_for('companies.companies'))

    return render_template('company_detail.html', **data)


# =============================================================================
# EDIT
# =============================================================================

@companies_bp.route('/company/<ticker>/edit', methods=['GET', 'POST'])
def edit_company(ticker):
    """
    Edit company information.

    Args:
        ticker: Company ticker symbol
    """
    data = service.get_company_with_releases(ticker)

    if not data:
        flash(f'Company not found: {ticker}', 'error')
        return redirect(url_for('companies.companies'))

    company = data['company']
    form = EditCompanyForm(obj=company)

    # Convert is_public from boolean to string for SelectField choices
    # Must set this explicitly because SelectField choices are strings
    form.is_public.data = 'true' if company.is_public else 'false'

    # Populate dropdown choices (must be done before validation)
    form.sector.choices = get_sector_choices()
    form.ir_platform.choices = [('', 'Select Platform')] + [
        (key, label) for group_name, options in get_platform_options() for key, label in options
    ]

    if form.validate_on_submit():
        form_data = process_company_form_data(form.data)
        new_ticker = form_data.get('ticker', ticker)

        success = service.update_company(
            ticker=ticker,
            data=form_data,
            new_ticker=new_ticker if new_ticker.upper() != ticker.upper() else None
        )

        if success:
            flash('Company updated successfully!', 'success')
            redirect_ticker = new_ticker if new_ticker else ticker
            filters = request.form.get('filters', '')

            # Redirect to companies list with filters preserved
            params = {'highlight': redirect_ticker}
            if filters:
                params['filters'] = filters
            return redirect(url_for('companies.companies', **params))
        else:
            flash('Error updating company (ticker may already exist)', 'error')

    sponsor_service = get_sponsor_service()
    return render_template('edit_company.html', company=company, form=form, sponsors=sponsor_service.get_all_sponsors_for_autocomplete(), sponsor_aliases=SPONSOR_ALIASES)


# =============================================================================
# ADD NEW COMPANY
# =============================================================================

@companies_bp.route('/company/add', methods=['GET', 'POST'])
def add_company():
    """
    Add a new company.
    """
    form = AddCompanyForm()

    # Populate dropdown choices dynamically from config
    form.sector.choices = get_sector_choices()
    form.ir_platform.choices = [('', 'Select Platform')] + [
        (key, label) for group_name, options in get_platform_options() for key, label in options
    ]

    if form.validate_on_submit():
        form_data = process_company_form_data(form.data)

        success = service.add_company(data=form_data)

        if success:
            flash('Company added successfully!', 'success')
            return redirect(url_for('companies.company_detail', ticker=form_data['ticker'].upper()))
        else:
            flash('Error adding company (may already exist)', 'error')

    sponsor_service = get_sponsor_service()
    return render_template('add_company.html', form=form, sponsors=sponsor_service.get_all_sponsors_for_autocomplete(), sponsor_aliases=SPONSOR_ALIASES)


# =============================================================================
# DELETE COMPANY
# =============================================================================

@companies_bp.route('/company/<ticker>/delete', methods=['POST'])
def delete_company(ticker):
    """
    Delete a company permanently.

    Args:
        ticker: Company ticker symbol
    """
    filters = request.form.get('filters', '')
    next_ticker = request.form.get('next_ticker', '')

    success = service.delete_company(ticker)
    if success:
        flash(f'Company {ticker} has been deleted.', 'success')
    else:
        flash(f'Failed to delete company {ticker}.', 'error')

    params = {}
    if filters:
        params['filters'] = filters
    if next_ticker:
        params['highlight'] = next_ticker

    return redirect(url_for('companies.companies', **params))


# =============================================================================
# API ENDPOINTS
# =============================================================================

@companies_bp.route('/api/companies.json')
def get_companies_json():
    """
    Get all companies as JSON (for autocomplete/API).

    Returns:
        JSON: List of companies with ticker and name
    """
    data = service.get_companies_for_display()
    companies = data['active_companies'] + data['inactive_companies']

    # Serialize for JSON
    result = [{
        'id': c.id,
        'ticker': c.ticker,
        'name': c.name,
        'sector': c.sector,
        'press_release_url': c.press_release_url
    } for c in companies]

    return jsonify(result)


@companies_bp.route('/api/company/<ticker>/toggle-emails', methods=['POST'])
def toggle_emails_activated(ticker):
    """
    Toggle email notifications for a company.

    Args:
        ticker: Company ticker

    Returns:
        JSON: New emails_activated state
    """
    new_state = service.toggle_emails_activated(ticker)

    if new_state is None:
        return jsonify({
            'success': False,
            'error': f'Company not found: {ticker}'
        }), 404

    return jsonify({
        'success': True,
        'emails_activated': new_state
    })


@companies_bp.route('/api/company/<ticker>/toggle-ignore-rss', methods=['POST'])
def toggle_ignore_company_rss(ticker):
    """
    Toggle ignore RSS flag for a company.

    Args:
        ticker: Company ticker

    Returns:
        JSON: New ignore_company_rss state
    """
    new_state = service.toggle_ignore_rss(ticker)

    if new_state is None:
        return jsonify({
            'success': False,
            'error': f'Company not found: {ticker}'
        }), 404

    return jsonify({
        'success': True,
        'ignore_company_rss': new_state
    })


@companies_bp.route('/api/company/<ticker>/toggle-active', methods=['POST'])
def toggle_active(ticker):
    """
    Toggle active status for a company.

    Args:
        ticker: Company ticker symbol

    Returns:
        JSON: New active state
    """
    new_state = service.toggle_active(ticker)

    if new_state is None:
        return jsonify({
            'success': False,
            'error': f'Company not found: {ticker}'
        }), 404

    return jsonify({
        'success': True,
        'active': new_state,
        'ticker': ticker
    })
