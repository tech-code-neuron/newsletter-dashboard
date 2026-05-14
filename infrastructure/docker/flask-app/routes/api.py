"""
API blueprint - RESTful API endpoints for external integrations
Single Responsibility: JSON API responses only (health checks, status, etc.)

Uses Repository Pattern for database abstraction (DynamoDB in ECS, SQLite local).
"""
from flask import Blueprint, jsonify, session, redirect, request, url_for
from datetime import datetime, timedelta

from core.repositories import get_company_repo, get_press_release_repo

# Blueprint configuration
api_bp = Blueprint('api', __name__, url_prefix='/api')

# Constants
RECENT_RELEASES_DAYS = 7


@api_bp.route('/scraper-health')
def scraper_health():
    """
    Health check endpoint showing scraping status for all companies.
    Returns JSON with statistics and company-level status.
    """
    company_repo = get_company_repo()
    pr_repo = get_press_release_repo()

    # Get all active companies
    companies = company_repo.get_all_active()
    total_companies = len(companies)
    companies_with_rss = sum(1 for c in companies if c.rss_feed_url)
    companies_with_platform = sum(1 for c in companies if c.ir_platform)

    # Get recent scraping activity (last 7 days)
    cutoff = datetime.now() - timedelta(days=RECENT_RELEASES_DAYS)
    recent_releases = pr_repo.get_recent(
        limit=1000,
        days=RECENT_RELEASES_DAYS,
        include_deleted=False
    )

    # Group by company
    releases_by_company = {}
    for pr in recent_releases:
        ticker = pr.company.ticker if pr.company else 'Unknown'
        releases_by_company[ticker] = releases_by_company.get(ticker, 0) + 1

    # Companies with no recent releases
    stale_companies = [c.ticker for c in companies if c.ticker not in releases_by_company]

    # Get companies with release stats
    companies_with_stats = company_repo.get_with_release_stats()
    stats_by_ticker = {item['company'].ticker: item for item in companies_with_stats}

    # Build company status list
    company_status = []
    for company in companies:
        scraper_type = 'RSS' if company.rss_feed_url else company.ir_platform or 'Unknown'

        stats = stats_by_ticker.get(company.ticker, {})
        latest_date = stats.get('latest_date')
        total_releases = stats.get('release_count', 0)

        # Format latest date
        if latest_date:
            if isinstance(latest_date, str):
                try:
                    latest_date = datetime.fromisoformat(latest_date.replace('Z', '+00:00'))
                except ValueError:
                    latest_date = None

        company_status.append({
            'ticker': company.ticker,
            'name': company.name,
            'scraper_type': scraper_type,
            'scraper_variant': company.scraper_variant,
            'last_release_date': latest_date.strftime('%Y-%m-%d') if latest_date else None,
            'releases_last_7d': releases_by_company.get(company.ticker, 0),
            'total_releases': total_releases
        })

    response = {
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'summary': {
            'total_companies': total_companies,
            'companies_with_rss': companies_with_rss,
            'companies_with_platform': companies_with_platform,
            'total_releases_7d': len(recent_releases),
            'companies_with_releases_7d': len(releases_by_company),
            'stale_companies_count': len(stale_companies)
        },
        'stale_companies': stale_companies[:20],  # Limit to 20 for readability
        'companies': company_status
    }

    return jsonify(response)


@api_bp.route('/set-view-mode/<mode>')
def set_view_mode(mode):
    """
    Set user's preferred view mode (desktop, mobile, or auto).

    This allows users on mobile to force desktop view and vice versa.

    Args:
        mode: 'desktop', 'mobile', or 'auto'

    Returns:
        Redirect back to the referring page
    """
    if mode in ['desktop', 'mobile', 'auto']:
        session['view_mode'] = mode

    # Redirect back to the referring page, or home if no referrer
    referrer = request.referrer
    if referrer:
        return redirect(referrer)
    return redirect(url_for('dashboard.dashboard'))


@api_bp.route('/lookup-cik')
def lookup_cik():
    """
    Lookup SEC CIK number by ticker symbol.

    Queries SEC EDGAR's ticker-to-CIK mapping file.

    Query params:
        ticker: Stock ticker symbol (e.g., EPRT)

    Returns:
        JSON with CIK if found, error message otherwise
    """
    import requests

    ticker = request.args.get('ticker', '').strip().upper()

    if not ticker:
        return jsonify({
            'success': False,
            'message': 'Ticker symbol is required'
        }), 400

    try:
        # SEC's official ticker-to-CIK mapping
        SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
        SEC_USER_AGENT = "PressReleasePipeline/1.0 (contact@your-domain.com)"

        headers = {"User-Agent": SEC_USER_AGENT}
        response = requests.get(SEC_TICKERS_URL, headers=headers, timeout=10)
        response.raise_for_status()

        data = response.json()

        # Search for ticker
        for entry in data.values():
            if entry.get("ticker", "").upper() == ticker:
                cik = str(entry.get("cik_str", "")).zfill(10)
                company_name = entry.get("title", "")
                return jsonify({
                    'success': True,
                    'ticker': ticker,
                    'cik': cik,
                    'company_name': company_name
                })

        # Ticker not found
        return jsonify({
            'success': False,
            'message': f'Ticker "{ticker}" not found in SEC database. You can enter CIK manually.'
        })

    except requests.RequestException as e:
        return jsonify({
            'success': False,
            'message': f'SEC lookup failed: {str(e)}'
        }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Unexpected error: {str(e)}'
        }), 500
