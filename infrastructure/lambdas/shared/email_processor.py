"""
Email Processor Orchestrator
============================
SOLID: Single Responsibility + Orchestration Pattern

Replaces massive lambda_handler with focused orchestrator class.
Each method has a single responsibility:
- process_message(): Main orchestration
- match_company(): Company identification
- construct_url(): URL construction with strategies
- handle_fallbacks(): Fallback logic when construction fails
- route_urls(): Send to appropriate destination

Benefits:
1. Testable: Each method can be unit tested
2. Maintainable: Clear separation of concerns
3. Extensible: Easy to add new features
4. SOLID: Open/Closed - extend without modifying existing code
"""

import json
import logging
from datetime import datetime
from urllib.parse import urlparse

from .constants import JAVASCRIPT_RENDERED_COMPANIES
from .url_strategies import get_url_strategy

logger = logging.getLogger(__name__)


class EmailProcessor:
    """
    Orchestrates email processing workflow
    SOLID: Orchestration Pattern - Coordinates multiple services
    """

    def __init__(self,
                 s3_client,
                 companies_loader,
                 url_validator,
                 company_matcher,
                 url_classifier,
                 url_router,
                 idempotency_checker):
        """
        Initialize email processor with dependencies

        Args:
            s3_client: S3 client for email downloads
            companies_loader: Function to load all companies
            url_validator: Function to validate constructed URLs
            company_matcher: Object with match_by_domain() and match_by_name()
            url_classifier: Function to classify URLs (direct vs newswire)
            url_router: Object with route_direct() and route_scrape()
            idempotency_checker: Object with check() and mark_processed()
        """
        self.s3 = s3_client
        self.load_companies = companies_loader
        self.validate_url = url_validator
        self.company_matcher = company_matcher
        self.classify_url = url_classifier
        self.url_router = url_router
        self.idempotency = idempotency_checker

    def process_message(self, message_body, email_metadata_extractor,
                       confirmation_detector=None,
                       javascript_handler=None,
                       eprt_scraper=None,
                       redirect_follower=None,
                       construction_method_updater=None):
        """
        Process single SQS message

        Args:
            message_body: Parsed SQS message body
            email_metadata_extractor: Function to extract metadata from email
            confirmation_detector: Function to detect confirmation emails (optional)
            javascript_handler: Function to handle JS-rendered companies (optional)
            eprt_scraper: Function to scrape EPRT press release list (optional)
            redirect_follower: Function to follow redirect URLs (optional)
            construction_method_updater: Function to update construction method (optional)

        Returns:
            Dict with processing results
        """
        bucket = message_body['bucket']
        key = message_body['key']
        idempotency_key = message_body['idempotency_key']

        logger.info(f"Processing: {bucket}/{key}")

        # Check idempotency
        if self.idempotency.check(idempotency_key):
            logger.info(f"Already processed: {idempotency_key}")
            return {'status': 'skipped', 'reason': 'already_processed'}

        # Load companies (cached)
        companies = self.load_companies()

        # Download email from S3
        response = self.s3.get_object(Bucket=bucket, Key=key)
        email_content = response['Body'].read()

        # Extract metadata
        email_meta = email_metadata_extractor(email_content)
        logger.info(f"From: {email_meta['from_field'][:80]}")
        logger.info(f"Subject: {email_meta['subject'][:80]}")
        logger.info(f"Found {len(email_meta['urls'])} URLs")

        # Skip confirmation emails
        if confirmation_detector and confirmation_detector(email_meta['subject'], email_meta.get('body_text', '')):
            logger.info(f"✓ Skipped confirmation email: {idempotency_key}")
            self.idempotency.mark_processed(idempotency_key, {
                'email_key': key,
                'skipped_reason': 'confirmation_email',
                'subject': email_meta['subject'][:100]
            })
            return {'status': 'skipped', 'reason': 'confirmation_email'}

        # Match company
        matched_company = self._match_company(email_meta)

        if not matched_company:
            logger.info("No company match found")
            # Continue with URL-based matching fallback
            matched_urls = self._fallback_url_matching(email_meta)
        else:
            # Handle JavaScript-rendered companies
            if matched_company['ticker'] in JAVASCRIPT_RENDERED_COMPANIES:
                if javascript_handler:
                    return javascript_handler(
                        matched_company,
                        email_meta,
                        key,
                        idempotency_key
                    )

            # Construct URL using strategy
            matched_urls = self._construct_and_validate_urls(
                matched_company,
                email_meta,
                eprt_scraper=eprt_scraper,
                redirect_follower=redirect_follower
            )

            # Smart fallback if construction failed
            if not matched_urls:
                matched_urls = self._handle_fallback(
                    matched_company,
                    email_meta,
                    redirect_follower=redirect_follower,
                    construction_method_updater=construction_method_updater
                )

        # Final fallback: URL-based matching
        if not matched_urls:
            matched_urls = self._fallback_url_matching(email_meta)

        logger.info(f"Filtered to {len(matched_urls)} company press release URLs")

        # Route URLs
        direct_count, newswire_count = self._route_urls(matched_urls, key)

        # Mark as processed
        self.idempotency.mark_processed(idempotency_key, {
            'email_key': key,
            'from_field': email_meta['from_field'],
            'subject': email_meta['subject'],
            'urls_found': len(email_meta['urls']),
            'urls_matched': len(matched_urls),
            'direct_links': direct_count,
            'newswire_links': newswire_count
        })

        logger.info(f"Completed: {direct_count} direct, {newswire_count} newswire")

        return {
            'status': 'processed',
            'direct_count': direct_count,
            'newswire_count': newswire_count
        }

    def _match_company(self, email_meta):
        """
        Match company from email metadata
        Priority: Domain first (source of truth), then name

        Args:
            email_meta: Email metadata dict

        Returns:
            Matched company dict or None
        """
        # Priority 1: Domain-based matching
        matched_company, matched_url = self.company_matcher.match_by_domain(email_meta['urls'])
        if matched_company:
            logger.info(f"✓ Company matched by domain: {matched_company['ticker']} ({matched_company['name']})")
            return matched_company

        # Priority 2: Name-based matching
        matched_company = self.company_matcher.match_by_name(email_meta['from_field'])
        if matched_company:
            logger.info(f"Company matched from From field: {matched_company['ticker']} ({matched_company['name']})")
            return matched_company

        return None

    def _construct_and_validate_urls(self, company, email_meta, eprt_scraper=None, redirect_follower=None):
        """
        Construct and validate URLs using strategy pattern

        Args:
            company: Matched company dict
            email_meta: Email metadata
            eprt_scraper: EPRT scraping function (optional)
            redirect_follower: Redirect following function (optional)

        Returns:
            List of (url, company) tuples
        """
        construction_method = company.get('url_construction_method', 'direct_url')
        logger.info(f"Using construction method: {construction_method}")

        matched_urls = []

        # Get strategy
        strategy = get_url_strategy(construction_method)
        if not strategy:
            logger.warning(f"Unknown construction method: {construction_method}")
            return []

        # Handle special cases (EPRT, redirect_follow, direct_url)
        if construction_method == 'eprt_scrape_list' and eprt_scraper:
            # EPRT-specific scraping
            matched_urls = self._handle_eprt_scraping(company, email_meta, eprt_scraper)
        elif construction_method == 'redirect_follow' and redirect_follower:
            # Redirect following
            matched_urls = self._handle_redirect_following(company, email_meta, redirect_follower)
        elif construction_method == 'direct_url':
            # Direct URL extraction from email
            matched_urls = self._handle_direct_url_extraction(company, email_meta)
        else:
            # Standard URL construction
            crafted_url = strategy.construct(
                email_meta['subject'],
                company['ir_domain'],
                email_meta.get('date')
            )

            if crafted_url:
                # Validate constructed URL
                exists, status = self.validate_url(crafted_url)
                if exists:
                    matched_urls.append((crafted_url, company))
                    logger.info(f"✓ Crafted URL validated ({construction_method}): {company['ticker']} - {crafted_url}")
                else:
                    logger.warning(f"✗ Crafted URL failed validation (status {status}): {crafted_url}")

        return matched_urls

    def _handle_eprt_scraping(self, company, email_meta, eprt_scraper):
        """Handle EPRT-specific press release list scraping"""
        matched_urls = []

        # Verify this is a press release email
        subject_lower = email_meta['subject'].lower()
        is_press_release = any(keyword in subject_lower for keyword in [
            'announces', 'declares', 'reports', 'completes', 'acquires',
            'dividend', 'earnings', 'acquisition'
        ])

        if not is_press_release:
            logger.info(f"EPRT: Skipping non-press-release email: {email_meta['subject'][:60]}")
            return []

        # Extract title
        title = email_meta['subject']
        if ':' in title:
            title = title.split(':', 1)[1].strip()

        # Get press releases list page URL
        press_releases_url = company.get('press_release_url') or \
                            f"https://{company['ir_domain']}/press-releases/"

        # Scrape list page
        pr_url = eprt_scraper(title, press_releases_url)

        if pr_url:
            matched_urls.append((pr_url, company))
            logger.info(f"✓ EPRT scraper found PR: {company['ticker']} - {pr_url}")
        else:
            logger.warning(f"✗ EPRT scraper failed to find matching PR for: {title[:60]}")

        return matched_urls

    def _handle_redirect_following(self, company, email_meta, redirect_follower):
        """Handle redirect following strategy"""
        matched_urls = []

        for url in email_meta['urls']:
            # Only follow notification/tracking redirects
            is_redirect_url = (
                '/ls/click' in url or
                'notification' in url or
                'sendgrid' in url or
                'ir.stockpr.com' in url
            )
            if not is_redirect_url:
                continue

            # Follow redirect
            final_url = redirect_follower(url, timeout=5)
            if final_url and final_url != url:
                # Validate it's a press release
                from .parser_utils import is_press_release_url
                if is_press_release_url(final_url):
                    matched_urls.append((final_url, company))
                    logger.info(f"Redirect followed: {company['ticker']} - {url[:50]}... → {final_url}")

        return matched_urls

    def _handle_direct_url_extraction(self, company, email_meta):
        """Handle direct URL extraction from email body"""
        from .parser_utils import is_press_release_url
        matched_urls = []

        for url in email_meta['urls']:
            if not is_press_release_url(url):
                continue

            # Check if URL belongs to company
            try:
                parsed = urlparse(url)
                url_domain = parsed.netloc.lower()
                url_path = parsed.path.lower()
                company_domain = company.get('ir_domain', '').lower()

                # Domain match
                if company_domain and (company_domain in url_domain or url_domain in company_domain):
                    matched_urls.append((url, company))
                    logger.info(f"URL matched to company: {company['ticker']} - {url}")

            except:
                continue

        return matched_urls

    def _handle_fallback(self, company, email_meta, redirect_follower=None, construction_method_updater=None):
        """
        Handle fallback when URL construction fails

        Args:
            company: Matched company
            email_meta: Email metadata
            redirect_follower: Redirect following function
            construction_method_updater: Function to update construction method

        Returns:
            List of (url, company) tuples
        """
        from .parser_utils import is_press_release_url
        construction_method = company.get('url_construction_method', 'direct_url')

        # Skip fallback for methods that don't construct URLs
        if construction_method in ['direct_url', 'redirect_follow']:
            return []

        logger.warning(f"⚠️  URL construction failed for {company['ticker']}, trying redirect_follow fallback...")

        matched_urls = []

        if not redirect_follower:
            return []

        for url in email_meta['urls']:
            # Only follow notification/tracking redirects
            is_redirect_url = (
                '/ls/click' in url or
                'notification' in url or
                'sendgrid' in url or
                'ir.stockpr.com' in url
            )
            if not is_redirect_url:
                continue

            if not is_press_release_url(url):
                continue

            # Follow redirect
            final_url = redirect_follower(url, timeout=5)
            if final_url and final_url != url:
                if is_press_release_url(final_url):
                    matched_urls.append((final_url, company))
                    logger.info(f"✓ Redirect fallback succeeded: {company['ticker']} - {final_url}")

                    # Auto-correct: Update database to use redirect_follow
                    if construction_method_updater:
                        construction_method_updater(
                            company['ticker'],
                            'redirect_follow',
                            f"Auto-corrected from {construction_method} which returned 404"
                        )
                    break

        return matched_urls

    def _fallback_url_matching(self, email_meta):
        """
        Fallback to URL-based company matching

        Args:
            email_meta: Email metadata

        Returns:
            List of (url, company) tuples
        """
        from .parser_utils import is_press_release_url
        matched_urls = []

        logger.info("Trying URL-based matching...")

        for url in email_meta['urls']:
            if not is_press_release_url(url):
                continue

            company, matched, final_url = self.company_matcher.find_by_url(url)
            if matched:
                url_to_save = final_url if final_url else url
                matched_urls.append((url_to_save, company))
                logger.info(f"URL-based match: {company['ticker']} - {url_to_save}")

        return matched_urls

    def _route_urls(self, matched_urls, email_key):
        """
        Route URLs to appropriate destinations

        Args:
            matched_urls: List of (url, company) tuples
            email_key: S3 email key (for metadata)

        Returns:
            Tuple of (direct_count, newswire_count)
        """
        direct_count = 0
        newswire_count = 0

        for url, company in matched_urls:
            url_type, url = self.classify_url(url)

            metadata = {
                'email_key': email_key,
                'extracted_at': datetime.utcnow().isoformat(),
                'ticker': company['ticker'],
                'company_name': company['name']
            }

            if url_type == 'direct':
                self.url_router.route_direct(url, metadata)
                direct_count += 1
            elif url_type == 'newswire':
                self.url_router.route_scrape(url, metadata)
                newswire_count += 1

        return direct_count, newswire_count
