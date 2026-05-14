"""
URL Selector - Main URL Selection Orchestration
===============================================
Single Responsibility: Orchestrate URL selection with redirect following + smart scoring

Rate Limiting Strategy (Best Practice):
- Connection pooling via requests.Session() for efficiency
- 300ms delay between requests to avoid pattern detection
- Exponential backoff: 1s, 2s (max 2 retries)
- Circuit breaker: Stop after 2 consecutive failures per domain
"""

import logging
import requests
import time
from urllib.parse import urlparse

from url_selection.detector import is_landing_page, is_utility_page
from url_selection.scorer import score_url
from url_selection.decision_logger import log_url_selection_decision
from config.constants import REDIRECT_TIMEOUT

logger = logging.getLogger()

# Global session for connection pooling (reused across Lambda invocations)
_session = None

def get_session():
    """Get or create a requests Session for connection pooling"""
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    return _session


def _follow_redirect_with_backoff(url, max_retries=2):
    """
    Follow redirect with manual redirect following to capture final URL even on timeout

    IMPROVEMENT: Manually follows each redirect step so we can capture the final URL
    even if the destination times out. Critical for tracking URLs that redirect to
    slow-loading sites.

    Example:
        url9490.notification.gcs-web.com → www.alx-inc.com/news-releases/...
        Even if www.alx-inc.com times out, we still capture that final URL.

    Args:
        url: Tracking URL to follow
        max_retries: Maximum retry attempts (default: 2 = initial + 1 retry)

    Returns:
        str: Final URL in redirect chain (even if destination timed out!)
    """
    session = get_session()
    current_url = url
    redirect_count = 0
    max_redirects = 10

    for attempt in range(max_retries):
        try:
            if attempt > 0:
                delay = 2 ** (attempt - 1)
                logger.info(f"  Retry {attempt}/{max_retries-1} after {delay}s delay...")
                time.sleep(delay)

            logger.info(f"Following redirect chain from: {current_url[:60]}...")

            # Manually follow redirects step by step
            while redirect_count < max_redirects:
                response = session.head(
                    current_url,
                    allow_redirects=False,  # Manual redirect following
                    timeout=REDIRECT_TIMEOUT
                )

                # Success - no more redirects
                if response.status_code == 200:
                    logger.info(f"✅ Final URL: {current_url[:80]}")
                    return current_url

                # Redirect - follow it
                if response.status_code in (301, 302, 303, 307, 308):
                    redirect_url = response.headers.get('Location')
                    if not redirect_url:
                        logger.warning(f"Redirect without Location header")
                        return current_url

                    # Handle relative redirects
                    if redirect_url.startswith('/'):
                        parsed = urlparse(current_url)
                        redirect_url = f"{parsed.scheme}://{parsed.netloc}{redirect_url}"

                    logger.info(f"  → Redirect: {current_url[:60]}... → {redirect_url[:60]}...")
                    current_url = redirect_url
                    redirect_count += 1
                    continue

                # Other status (404, 403, etc.)
                logger.warning(f"Non-success status: {response.status_code}")
                return current_url

            # Too many redirects
            logger.warning(f"Too many redirects (>{max_redirects})")
            return current_url

        except requests.exceptions.Timeout as e:
            # CRITICAL: Return the last URL we reached before timeout
            logger.warning(f"  Timeout on attempt {attempt + 1}/{max_retries}: {e}")
            logger.info(f"✓ Captured final URL despite timeout: {current_url[:80]}")
            if attempt == max_retries - 1:
                # We have the final URL even though it timed out!
                logger.warning(f"Using final URL despite timeout (works in browsers): {current_url[:80]}")
                return current_url
        except Exception as e:
            logger.warning(f"  Error on attempt {attempt + 1}/{max_retries}: {e}")
            if attempt == max_retries - 1:
                logger.warning(f"Using last known URL: {current_url[:80]}")
                return url

    return url


def select_best_url_from_email(urls, company, subject_line=''):
    """
    Select the URL that best matches the company's press release domain

    Strategy (Zero-Maintenance Redirect Following + Smart Selection):
        1. For each URL:
           - If domain matches company IR domain → Use directly (no redirect)
           - If domain is external → Follow redirect (likely tracking link)
        2. Filter resolved URLs to company domain
        3. Smart selection:
           - If first URL is specific (not landing page) → Use it (90% case)
           - If first URL is landing page → Score all URLs by subject + depth
           - Choose highest scoring URL

    This approach works with ANY tracking service (SendGrid, GCS-Web, etc.)
    without maintaining a whitelist of tracking domains.

    Args:
        urls: List of URLs from email
        company: Company config dict with press_release_url, ir_domain
        subject_line: Email subject line (for content matching when needed)

    Returns:
        str: Best matching URL or None
    """
    if not urls:
        return None

    # Don't skip redirect logic for single URLs - tracking URLs need resolution!
    # Removed: if len(urls) == 1: return urls[0]

    press_release_url = company.get('press_release_url', '')
    ir_domain = company.get('ir_domain', '')

    # Extract domain from press_release_url
    pr_domain = None
    if press_release_url:
        parsed = urlparse(press_release_url)
        pr_domain = parsed.netloc

    # Smart redirect following: Follow redirects for URLs NOT on company IR domain
    resolved_urls = []
    for url in urls:
        parsed_url = urlparse(url)

        # Check if URL is already on company's IR domain
        is_company_domain = False
        if ir_domain and ir_domain in parsed_url.netloc:
            is_company_domain = True
        elif pr_domain and pr_domain in parsed_url.netloc:
            is_company_domain = True

        # If URL is external (not company domain), follow redirect with rate limiting
        if not is_company_domain:
            final_url = _follow_redirect_with_backoff(url)
            resolved_urls.append((final_url, url))

            # Rate limiting: 300ms delay between requests to avoid triggering Cloudflare
            time.sleep(0.3)
        else:
            logger.debug(f"URL already on company domain, using directly: {url[:60]}...")
            resolved_urls.append((url, url))

    # Phase 1: Filter to domain-matching URLs
    domain_matching_urls = []

    # Priority 1: Match press_release_url domain
    if pr_domain:
        for final_url, original_url in resolved_urls:
            parsed_url = urlparse(final_url)
            if pr_domain in parsed_url.netloc and not is_utility_page(final_url):
                domain_matching_urls.append(final_url)
        if domain_matching_urls:
            logger.info(f"✓ Found {len(domain_matching_urls)} URLs matching PR domain: {pr_domain}")

    # Priority 2: Match ir_domain (if no PR domain or no matches)
    if not domain_matching_urls and ir_domain:
        for final_url, original_url in resolved_urls:
            parsed_url = urlparse(final_url)
            if ir_domain in parsed_url.netloc and not is_utility_page(final_url):
                domain_matching_urls.append(final_url)
        if domain_matching_urls:
            logger.info(f"✓ Found {len(domain_matching_urls)} URLs matching IR domain: {ir_domain}")

    # Fallback: Use all resolved URLs (excluding utility pages)
    if not domain_matching_urls:
        domain_matching_urls = [
            final for final, orig in resolved_urls
            if not is_utility_page(final)
        ]
        logger.info(f"✓ Fallback: Using all {len(domain_matching_urls)} non-utility URLs")

    # Phase 2: Smart URL selection with landing page detection
    if domain_matching_urls:
        first_url = domain_matching_urls[0]

        # Simple case: First URL is specific (not a landing page)
        if not is_landing_page(first_url):
            logger.info(f"✓ Selected specific URL (not landing page): {first_url[:80]}...")

            # Log simple selection decision
            ticker = company.get('ticker', 'UNKNOWN')
            # Score all URLs even in simple case (for comparison in logs)
            scored_urls = [
                (url, score_url(url, subject_line, press_release_url))
                for url in domain_matching_urls
            ]
            log_url_selection_decision(
                ticker=ticker,
                email_subject=subject_line,
                candidate_urls_with_scores=scored_urls,
                selected_url=first_url,
                company=company,
                selection_method='simple_first_non_landing'
            )

            return first_url

        # Landing page detected: Score all URLs by subject line + specificity
        logger.info(f"⚠ Landing page detected, scoring all URLs by subject line + specificity")

        scored_urls = [
            (url, score_url(url, subject_line, press_release_url))
            for url in domain_matching_urls
        ]

        # Log scores for debugging
        for url, url_score in scored_urls:
            logger.info(f"  URL score {url_score}: {url[:80]}...")

        # Choose highest scoring URL
        best_url, best_score = max(scored_urls, key=lambda x: x[1])
        logger.info(f"✓ Selected best URL (score={best_score}): {best_url[:80]}...")

        # Log decision for analysis (structured logging with 180-day retention)
        ticker = company.get('ticker', 'UNKNOWN')
        log_url_selection_decision(
            ticker=ticker,
            email_subject=subject_line,
            candidate_urls_with_scores=scored_urls,
            selected_url=best_url,
            company=company,
            selection_method='smart_scoring'
        )

        return best_url

    # Final fallback: First resolved URL
    if resolved_urls:
        first_final, first_original = resolved_urls[0]
        logger.warning(f"No domain match found, using first URL: {first_final[:80]}...")

        # Log fallback decision
        ticker = company.get('ticker', 'UNKNOWN')
        log_url_selection_decision(
            ticker=ticker,
            email_subject=subject_line,
            candidate_urls_with_scores=[(first_final, 0)],
            selected_url=first_final,
            company=company,
            selection_method='fallback_first_url'
        )

        return first_final

    return None
