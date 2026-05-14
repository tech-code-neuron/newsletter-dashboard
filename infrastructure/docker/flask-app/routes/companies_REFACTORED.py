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
from forms.company_forms import AddCompanyForm, EditCompanyForm
from utils.form_validator import process_company_form_data

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

    if form.validate_on_submit():
        form_data = process_company_form_data(form.data)

        success = service.update_company(
            ticker=ticker,
            name=form_data['name'],
            sector=form_data.get('sector'),
            rss_feed_url=form_data.get('rss_feed_url'),
            emails_activated=form_data.get('emails_activated', False)
        )

        if success:
            flash('Company updated successfully!', 'success')
            return redirect(url_for('companies.company_detail', ticker=ticker))
        else:
            flash('Error updating company', 'error')

    return render_template('edit_company.html', company=company, form=form)


# =============================================================================
# ADD NEW COMPANY
# =============================================================================

@companies_bp.route('/company/add', methods=['GET', 'POST'])
def add_company():
    """
    Add a new company.
    """
    form = AddCompanyForm()

    if form.validate_on_submit():
        form_data = process_company_form_data(form.data)

        success = service.add_company(
            ticker=form_data['ticker'],
            name=form_data['name'],
            sector=form_data.get('sector'),
            rss_feed_url=form_data.get('rss_feed_url'),
            emails_activated=form_data.get('emails_activated', False)
        )

        if success:
            flash('Company added successfully!', 'success')
            return redirect(url_for('companies.company_detail', ticker=form_data['ticker'].upper()))
        else:
            flash('Error adding company (may already exist)', 'error')

    return render_template('add_company.html', form=form)


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
        'ticker': c.ticker,
        'name': c.name,
        'sector': c.sector
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
