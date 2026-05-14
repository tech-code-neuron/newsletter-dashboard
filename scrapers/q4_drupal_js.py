"""
Q4 Drupal JavaScript platform scraper.
For Q4 Drupal sites that load content dynamically via JavaScript/AJAX.
Companies: ADC, ARE, PSA, VTR, KIM, and 70 others (75 total)

Handles 5 different Q4 variants:
- Evergreen: a.evergreen-news-link
- NIR Widget: article.node--type-nir-news
- IRW: a.irwGaLabel
- Module: a.module_headline-link
- Wrapper: a.wrapper-link
"""
from datetime import datetime, timedelta
from urllib.parse import urljoin
from dateutil import parser as dateutil_parser
import re
import logging

from scrapers.base_scraper import BaseScraper
from models import PressRelease

logger = logging.getLogger(__name__)


class Q4DrupalJsScraper(BaseScraper):
    """Scraper for Q4 Drupal JavaScript-rendered IR pages"""

    def scrape(self, company, lookback_days=14):
        """
        Scrape press releases from Q4 Drupal JavaScript-rendered pages.

        These pages load an initial "Loading..." placeholder and then populate
        press release links via AJAX after page load. We use Playwright to wait
        for the dynamic content to render before extracting links.

        Tested against: ADC, ARE, PSA, VTR, KIM, and 70 others.

        Args:
            company: Company model instance
            lookback_days: Only return releases from the last N days

        Returns:
            int: Number of new press releases saved to database
        """
        press_url = company.press_release_url or company.ir_url
        if not press_url:
            logger.warning(f"[{company.ticker}] No press release URL — skipping q4_js scrape")
            return 0

        logger.info(f"[{company.ticker}] Q4 JavaScript scrape: {press_url}")

        try:
            # Create isolated browser context
            context = self.browser.new_context(
                permissions=[],  # Block all permissions
                geolocation=None,
                ignore_https_errors=True
            )
            page = context.new_page()

            try:
                # Navigate and wait for content
                page.goto(press_url, wait_until='domcontentloaded', timeout=30000)

                # Handle cookies and popups
                self._handle_cookies_and_popups(page, company)

                # Scroll to trigger lazy loading
                self._scroll_page(page)

                # Detect which Q4 variant this site uses
                selector_used = self._detect_variant(page, company)

                if not selector_used:
                    logger.warning(f"[{company.ticker}] Timeout waiting for Q4 news elements")
                    return 0

                # Wait for AJAX to complete
                page.wait_for_timeout(3000)

                # Extract links based on variant
                raw_links = self._extract_links_by_variant(page, selector_used)

            finally:
                page.close()
                context.close()

        except Exception as e:
            logger.error(f"[{company.ticker}] Q4 JS scrape failed: {e}")
            return 0

        if not raw_links:
            logger.info(f"[{company.ticker}] No release-details links found on page")
            return 0

        logger.info(f"[{company.ticker}] Found {len(raw_links)} candidate links")

        # Parse and filter releases
        releases = self._parse_and_filter_releases(raw_links, press_url, lookback_days, company)

        logger.info(f"[{company.ticker}] {len(releases)} releases after filtering (lookback={lookback_days}d)")

        # Save to database
        return self._save_releases(releases, company)

    def _handle_cookies_and_popups(self, page, company):
        """Handle cookie consent banners and disclaimer popups"""
        # Cookie consent banners
        cookie_selectors = self.config['cookie_selectors']
        for selector in cookie_selectors:
            try:
                cookie_btn = page.query_selector(selector)
                if cookie_btn and cookie_btn.is_visible():
                    cookie_btn.click()
                    logger.debug(f"[{company.ticker}] Clicked cookie accept button")
                    page.wait_for_timeout(1000)
                    break
            except Exception:
                continue

        # JavaScript-based cookie banner dismissal
        page.wait_for_timeout(2000)
        try:
            page.evaluate("""() => {
                if (window.CookieBanner && window.CookieBanner.hideCookieBanner) {
                    window.CookieBanner.hideCookieBanner();
                }
                const banners = document.querySelectorAll('#msCookieBanner, .msCookieBanner, [id*="cookie"]');
                banners.forEach(b => b.style.display = 'none');
            }""")
            logger.debug(f"[{company.ticker}] Executed JavaScript cookie banner dismissal")
            page.wait_for_timeout(1000)
        except Exception:
            pass

        # Disclaimer/popup close buttons
        close_selectors = self.config['close_selectors']
        for selector in close_selectors:
            try:
                close_btn = page.query_selector(selector)
                if close_btn and close_btn.is_visible():
                    close_btn.click()
                    logger.debug(f"[{company.ticker}] Closed disclaimer/popup")
                    page.wait_for_timeout(1000)
                    break
            except Exception:
                continue

    def _scroll_page(self, page):
        """Scroll to trigger lazy loading"""
        page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(2000)
        page.evaluate("() => window.scrollTo(0, 0)")
        page.wait_for_timeout(1000)

    def _detect_variant(self, page, company):
        """Detect which Q4 variant this site uses"""
        variants = self.config['variants']

        # Build selector map
        selector_map = {
            name: variant['selector']
            for name, variant in variants.items()
        }

        # FAST PATH: Use cached variant if available
        if company.scraper_variant and company.scraper_variant in selector_map:
            try:
                page.wait_for_selector(selector_map[company.scraper_variant], timeout=8000)
                logger.debug(f"[{company.ticker}] Direct route: {company.scraper_variant}")
                return company.scraper_variant
            except Exception:
                logger.warning(f"[{company.ticker}] Cached variant '{company.scraper_variant}' failed, trying cascade")

        # SLOW PATH: Try all variants
        for variant_name, selector in selector_map.items():
            try:
                page.wait_for_selector(selector, timeout=8000)
                # Update cache
                if variant_name != company.scraper_variant:
                    company.scraper_variant = variant_name
                    self.db_session.commit()
                    logger.info(f"[{company.ticker}] Updated scraper_variant cache to: {variant_name}")
                return variant_name
            except Exception:
                continue

        return None

    def _extract_links_by_variant(self, page, variant):
        """Extract links based on Q4 variant"""
        if variant == 'evergreen':
            return self._extract_evergreen_links(page)
        elif variant == 'nir-widget':
            return self._extract_nir_widget_links(page)
        elif variant == 'irw':
            return self._extract_irw_links(page)
        elif variant == 'module':
            return self._extract_module_links(page)
        elif variant == 'wrapper':
            return self._extract_wrapper_links(page)
        return []

    def _extract_evergreen_links(self, page):
        """Extract links from Evergreen variant"""
        raw_links = []
        link_elements = page.query_selector_all('a.evergreen-news-link')
        for elem in link_elements:
            href = elem.get_attribute('href') or ''
            text = (elem.text_content() or '').strip()

            if ('-details/' in href.lower() or 'detail.aspx' in href.lower()) and len(text) > 20:
                aria_label = elem.get_attribute('aria-label') or ''
                raw_links.append({'href': href, 'text': text, 'aria_label': aria_label, 'type': 'evergreen'})
        return raw_links

    def _extract_nir_widget_links(self, page):
        """Extract links from NIR Widget variant"""
        raw_links = []
        articles = page.query_selector_all('article.node--type-nir-news')
        for article in articles:
            headline_elem = article.query_selector('.nir-widget--news--headline a')
            if not headline_elem:
                continue

            href = headline_elem.get_attribute('href') or ''
            text = (headline_elem.text_content() or '').strip()

            date_elem = article.query_selector('.nir-widget--news--date-time')
            date_text = (date_elem.text_content() or '').strip() if date_elem else ''

            if href and len(text) > 10:
                raw_links.append({'href': href, 'text': text, 'date_text': date_text, 'type': 'nir-widget'})
        return raw_links

    def _extract_irw_links(self, page):
        """Extract links from IRW variant"""
        raw_links = []
        link_elements = page.query_selector_all('a.irwGaLabel[href]')
        for elem in link_elements:
            href = elem.get_attribute('href') or ''
            text = (elem.text_content() or '').strip()

            if ('/20' in href and
                any(pattern in href.lower() for pattern in ['press-release', 'news-details', 'news/20']) and
                len(text) > 20):
                raw_links.append({'href': href, 'text': text, 'type': 'irw'})
        return raw_links

    def _extract_module_links(self, page):
        """Extract links from Module variant"""
        raw_links = []
        link_elements = page.query_selector_all('a.module_headline-link[href]')
        for elem in link_elements:
            href = elem.get_attribute('href') or ''
            text = (elem.text_content() or '').strip()

            if '/news-details/20' in href and len(text) > 20:
                raw_links.append({'href': href, 'text': text, 'type': 'module'})
        return raw_links

    def _extract_wrapper_links(self, page):
        """Extract links from Wrapper variant"""
        raw_links = []
        link_elements = page.query_selector_all('a.wrapper-link[href*="/news/detail"]')
        for elem in link_elements:
            href = elem.get_attribute('href') or ''
            text = (elem.text_content() or '').strip()

            if '/news/detail/' in href and len(text) > 20:
                raw_links.append({'href': href, 'text': text, 'type': 'wrapper'})
        return raw_links

    def _parse_and_filter_releases(self, raw_links, press_url, lookback_days, company):
        """Parse dates and filter releases by lookback period"""
        cutoff_date = datetime.now() - timedelta(days=lookback_days)
        seen_urls = set()
        releases = []

        for link_data in raw_links:
            title = link_data['text']
            href = link_data['href']

            # Skip short text
            if len(title) < 10:
                continue

            full_url = urljoin(press_url, href)

            # Deduplicate
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            # Extract date based on variant
            pub_date = self._extract_date_by_type(link_data, company)

            # Apply lookback filter
            if pub_date and pub_date < cutoff_date:
                continue

            releases.append({
                'title': title,
                'url': full_url,
                'date': pub_date,
            })

        return releases

    def _extract_date_by_type(self, link_data, company):
        """Extract publication date based on link type"""
        link_type = link_data.get('type', 'unknown')

        if link_type == 'evergreen':
            # Extract from aria-label (format: "Title, Month DD, YYYY")
            aria_label = link_data.get('aria_label', '')
            if aria_label:
                date_match = re.search(r',\s*([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})\s*$', aria_label)
                if date_match:
                    try:
                        return dateutil_parser.parse(date_match.group(1))
                    except Exception:
                        pass

        elif link_type == 'nir-widget':
            # Extract from date_text field
            date_text = link_data.get('date_text', '')
            if date_text:
                try:
                    pub_date = dateutil_parser.parse(date_text)
                    logger.debug(f"[{company.ticker}] Extracted date: {pub_date.strftime('%Y-%m-%d')}")
                    return pub_date
                except Exception as e:
                    logger.debug(f"[{company.ticker}] Date parse failed: {e}")

        elif link_type in ['irw', 'module']:
            # Extract year from URL path
            href = link_data['href']
            year_match = re.search(r'/(\d{4})/', href)
            if year_match:
                year = int(year_match.group(1))
                current_year = datetime.now().year
                if year == current_year:
                    return datetime.now()
                else:
                    return datetime(year, 1, 1)

        elif link_type == 'wrapper':
            # No year in URL, use current date
            return datetime.now()

        return None

    def _save_releases(self, releases, company):
        """Save releases to database"""
        new_count = 0

        for release_data in releases:
            existing = self.db_session.query(PressRelease).filter_by(
                url=release_data['url']
            ).first()

            if existing:
                logger.debug(f"[{company.ticker}] Already have: {release_data['title'][:50]}")
                continue

            content = self.fetch_content(release_data['url'])

            press_release = PressRelease(
                company_id=company.id,
                title=release_data['title'],
                url=release_data['url'],
                published_date=release_data.get('date') or datetime.now(),
                content=content,
                category=None,
                included_in_newsletter=True
            )

            self.db_session.add(press_release)
            self.db_session.commit()
            new_count += 1

            logger.info(f"  ✓ [{company.ticker}] {release_data['title'][:60]}")

        return new_count
