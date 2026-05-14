"""
Welltower platform scraper.
Company: WELL (Welltower)
"""
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin
from dateutil import parser as date_parser
import re
import logging

from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class WelltowerScraper(BaseScraper):
    """Scraper for Welltower press releases"""

    def scrape(self, company, lookback_days=14):
        """
        Scrape press releases from Welltower (WELL).

        Welltower uses /investors/press-release-details?id=XXX URL pattern.
        Dates are extracted from the listing page.

        Args:
            company: Company model instance
            lookback_days: Only return releases from the last N days

        Returns:
            int: Number of new press releases saved to database
        """
        press_url = company.press_release_url or company.ir_url
        if not press_url:
            logger.warning(f"[{company.ticker}] No URL for Welltower scrape")
            return 0

        # Ensure URL points to press releases
        if '/investors-press-releases' not in press_url:
            if press_url.endswith('/'):
                press_url = press_url + 'investors/investors-press-releases/'
            else:
                press_url = press_url + '/investors/investors-press-releases/'

        logger.info(f"[{company.ticker}] Welltower scrape: {press_url}")

        try:
            page = self.browser.new_page()

            try:
                page.goto(press_url, wait_until='domcontentloaded', timeout=30000)

                # Accept cookies
                try:
                    cookie_btn = page.query_selector(self.config['cookie_button'])
                    if cookie_btn and cookie_btn.is_visible():
                        cookie_btn.click()
                        page.wait_for_timeout(2000)
                except Exception:
                    pass

                # Scroll to load content
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(3000)

                # Find press release links using config
                links = page.query_selector_all(self.config['link_selector'])
                logger.info(f"[{company.ticker}] Found {len(links)} press release links")

                raw_releases = []
                cutoff_date = datetime.now(timezone.utc) - timedelta(days=lookback_days)

                for link in links:
                    href = link.get_attribute('href') or ''

                    # Try to find the container with both date and title
                    try:
                        container = link.evaluate_handle('''(el) => {
                            let current = el.parentElement;
                            for (let i = 0; i < 5; i++) {
                                if (!current) break;
                                // Look for container that has both the link and date text
                                let text = current.textContent || '';
                                if (text.includes('/202')) {  // Has date pattern
                                    return current;
                                }
                                current = current.parentElement;
                            }
                            return el.parentElement;
                        }''')

                        if container:
                            # Get full text of container
                            full_text = container.as_element().text_content() or ''

                            # Extract date (format: MM/DD/YYYY at start)
                            date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', full_text)
                            if date_match:
                                date_str = date_match.group(1)
                                try:
                                    pub_date = date_parser.parse(date_str)
                                    if pub_date.tzinfo is None:
                                        pub_date = pub_date.replace(tzinfo=timezone.utc)

                                    if pub_date < cutoff_date:
                                        continue

                                    # Extract title (text after the date)
                                    title = full_text.replace(date_str, '').strip()
                                    title = re.sub(r'\s+', ' ', title)  # Normalize whitespace

                                    if len(title) < 10:
                                        continue

                                    # Make URL absolute
                                    full_url = urljoin(press_url, href)

                                    raw_releases.append({
                                        'title': title[:200],  # Limit title length
                                        'url': full_url,
                                        'date': pub_date
                                    })
                                except Exception as e:
                                    logger.debug(f"[{company.ticker}] Date parse error: {e}")
                                    continue

                    except Exception as e:
                        logger.debug(f"[{company.ticker}] Error processing link: {e}")
                        continue

                logger.info(f"[{company.ticker}] Found {len(raw_releases)} releases within {lookback_days} days")

            finally:
                page.close()

        except Exception as e:
            logger.error(f"[{company.ticker}] Welltower scrape failed: {e}")
            return 0

        # Save to database using base class method
        new_count = 0
        for release_data in raw_releases:
            if self.save_release(company, release_data):
                new_count += 1

        return new_count
