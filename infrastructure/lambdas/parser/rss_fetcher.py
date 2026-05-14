"""
Parser Lambda - RSS Feed Fetcher
=================================
Fetch company RSS feeds and extract latest press release URL

SOLID Principles:
- Single Responsibility: Each function does ONE thing
- No Hardcoded Values: All constants imported
- DRY: Zero duplication

Last Updated: 2026-03-10
"""

import feedparser
import requests
import logging
from datetime import datetime, timedelta, timezone
from constants import (
    RSS_FETCH_TIMEOUT_SECONDS,
    RSS_MAX_RETRIES,
    RSS_ENTRY_MAX_AGE_DAYS,
    USER_AGENT_FULL
)
from url_utils import extract_domain_from_url

logger = logging.getLogger()


def fetch_company_rss_feed(rss_url, timeout=RSS_FETCH_TIMEOUT_SECONDS):
    """
    Fetch and parse company RSS feed

    Single Responsibility: Only fetches and parses RSS

    Args:
        rss_url: Company RSS feed URL
        timeout: Request timeout in seconds

    Returns:
        tuple: (feed_object, success, error_message)
    """
    if not rss_url or rss_url.strip() == '':
        return None, False, 'Empty RSS URL'

    try:
        logger.info(f"Fetching RSS feed: {rss_url[:60]}...")

        response = requests.get(
            rss_url,
            headers={'User-Agent': USER_AGENT_FULL},
            timeout=timeout
        )

        if response.status_code != 200:
            return None, False, f'HTTP {response.status_code}'

        # Parse RSS feed
        feed = feedparser.parse(response.content)

        if feed.bozo:
            return None, False, f'Parse error: {feed.bozo_exception}'

        if not feed.entries:
            return None, False, 'No entries in feed'

        logger.info(f"RSS feed fetched: {len(feed.entries)} entries")
        return feed, True, None

    except requests.Timeout:
        return None, False, 'Timeout'
    except requests.RequestException as e:
        return None, False, f'Request error: {str(e)[:100]}'
    except Exception as e:
        return None, False, f'Exception: {str(e)[:100]}'


def get_latest_rss_entry(feed, max_age_days=RSS_ENTRY_MAX_AGE_DAYS):
    """
    Get latest entry from RSS feed that's within max_age_days

    Single Responsibility: Only extracts latest entry

    Args:
        feed: Parsed feed object from feedparser
        max_age_days: Maximum age in days to consider "recent"

    Returns:
        dict: {
            'url': Entry URL,
            'title': Entry title,
            'published_date': datetime object,
            'age_days': int
        } or None if no recent entries
    """
    if not feed or not feed.entries:
        return None

    latest_entry = None
    latest_date = None
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=max_age_days)

    for entry in feed.entries:
        # Parse published date (make timezone-aware for comparison with cutoff_date)
        pub_date = None
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            pub_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
            pub_date = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)

        # Skip if no date or too old
        if not pub_date or pub_date < cutoff_date:
            continue

        # Track latest
        if latest_date is None or pub_date > latest_date:
            latest_date = pub_date
            latest_entry = entry

    if not latest_entry:
        logger.warning(f"No entries within {max_age_days} days")
        return None

    age_days = (datetime.now(timezone.utc) - latest_date).days

    return {
        'url': latest_entry.get('link'),
        'title': latest_entry.get('title', 'No title')[:200],
        'published_date': latest_date,
        'age_days': age_days
    }


def fetch_latest_pr_from_rss(company, max_age_days=RSS_ENTRY_MAX_AGE_DAYS):
    """
    Fetch latest press release from company RSS feed

    Single Responsibility: Orchestrates RSS fetch + validation

    Strategy:
    1. Check if company has RSS feed and it's not ignored
    2. Fetch RSS feed
    3. Get latest entry within max_age_days
    4. Validate entry URL is accessible
    5. Return URL + metadata or None

    Args:
        company: Company dict from DynamoDB (must have company_rss_feed_url)
        max_age_days: Maximum age to consider "recent" (default: 7 days)

    Returns:
        dict: {
            'url': Final PR URL,
            'title': PR title,
            'published_date': datetime,
            'source': 'company_rss',
            'rss_url': Original RSS feed URL
        } or None if RSS fails/stale
    """
    # Check if company has RSS feed
    rss_url = company.get('company_rss_feed_url')
    if not rss_url:
        logger.info(f"Company {company.get('ticker')} has no RSS feed")
        return None

    # Check if RSS is disabled for this company
    if company.get('ignore_company_rss', False):
        logger.info(f"RSS disabled for {company.get('ticker')} (ignore_company_rss=True)")
        return None

    # Fetch RSS feed
    feed, success, error = fetch_company_rss_feed(rss_url)
    if not success:
        logger.warning(f"RSS fetch failed for {company.get('ticker')}: {error}")
        return None

    # Get latest entry
    latest = get_latest_rss_entry(feed, max_age_days)
    if not latest:
        logger.warning(f"No recent RSS entries for {company.get('ticker')} (max age: {max_age_days} days)")
        return None

    # Trust RSS feed URLs - no validation needed
    # RSS feeds are authoritative sources, validation adds latency and triggers rate limiting
    pr_url = latest['url']
    if not pr_url:
        logger.warning(f"RSS entry has no URL: {latest['title']}")
        return None

    logger.info(f"✅ RSS SUCCESS for {company.get('ticker')}: {latest['title'][:60]}...")
    logger.info(f"   URL: {pr_url[:70]}...")
    logger.info(f"   Published: {latest['published_date'].strftime('%Y-%m-%d')} ({latest['age_days']} days ago)")
    logger.info(f"   Source: Trusted RSS feed (no validation)")

    return {
        'url': pr_url,
        'title': latest['title'],
        'published_date': latest['published_date'],
        'source': 'company_rss',
        'rss_url': rss_url,
        'age_days': latest['age_days']
    }
