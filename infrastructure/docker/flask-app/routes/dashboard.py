"""
Dashboard blueprint - Main landing page with stats and feed health
Single Responsibility: Dashboard visualization only

Uses Repository Pattern for database abstraction (DynamoDB in ECS, SQLite local).
"""
from flask import Blueprint, render_template
from datetime import datetime, timedelta

from config.aws_config import aws_config
from config.query_limits import (
    DASHBOARD_RECENT_RELEASES_LIMIT,
    DASHBOARD_RECENT_NEWSLETTERS_LIMIT
)
from core.repositories import (
    get_company_repo,
    get_press_release_repo,
    get_newsletter_repo
)
from routes.auth_decorators import login_required

# Blueprint configuration (no URL prefix - serves root '/')
dashboard_bp = Blueprint('dashboard', __name__)

# Constants
STALE_CUTOFF_DAYS = 30


def get_dashboard_data():
    """Get dashboard data using repository pattern (works for both ECS and local)"""
    company_repo = get_company_repo()
    pr_repo = get_press_release_repo()
    newsletter_repo = get_newsletter_repo()

    # Get counts
    companies = company_repo.get_all_active()
    total_companies = len(companies)
    total_releases = pr_repo.get_total_count()
    uncategorized = pr_repo.get_uncategorized_count()

    # Get recent releases
    recent_releases = pr_repo.get_recent(limit=DASHBOARD_RECENT_RELEASES_LIMIT)

    # Get recent newsletters
    recent_newsletters = newsletter_repo.get_recent(limit=DASHBOARD_RECENT_NEWSLETTERS_LIMIT)

    # Feed health - companies with RSS feeds
    rss_companies = [c for c in companies if c.rss_feed_url]
    rss_total = len(rss_companies)

    # Calculate feed exceptions (stale or never scraped)
    stale_cutoff = datetime.now() - timedelta(days=STALE_CUTOFF_DAYS)
    feed_exceptions = []

    # Get companies with release stats for feed health
    companies_with_stats = company_repo.get_with_release_stats()

    for item in companies_with_stats:
        company = item['company']
        latest_date = item['latest_date']

        # Only check companies with RSS feeds
        if not company.rss_feed_url:
            continue

        if not latest_date:
            feed_exceptions.append({
                'ticker': company.ticker,
                'name': company.name,
                'last_scraped': 'Never'
            })
        else:
            # Parse date if string
            if isinstance(latest_date, str):
                try:
                    latest_date = datetime.fromisoformat(latest_date.replace('Z', '+00:00'))
                except ValueError:
                    continue

            latest_date_naive = latest_date.replace(tzinfo=None) if latest_date.tzinfo else latest_date

            if latest_date_naive < stale_cutoff:
                feed_exceptions.append({
                    'ticker': company.ticker,
                    'name': company.name,
                    'last_scraped': latest_date_naive.strftime('%b %d, %Y')
                })

    return {
        'total_companies': total_companies,
        'total_releases': total_releases,
        'uncategorized': uncategorized,
        'recent_releases': recent_releases,
        'recent_newsletters': recent_newsletters,
        'rss_total': rss_total,
        'feed_exceptions': feed_exceptions
    }


@dashboard_bp.route('/dashboard')
@login_required
def index():
    """
    Dashboard with overview stats and feed health monitoring

    Shows:
    - Total counts (companies, press releases, uncategorized)
    - Recent press releases
    - Recent newsletters
    - RSS feed health exceptions (stale or never scraped)
    """
    data = get_dashboard_data()
    return render_template('index.html', **data)
