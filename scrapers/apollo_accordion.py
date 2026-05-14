"""
Apollo accordion platform scraper.
Company: ARI (Apollo Commercial Real Estate Finance)
"""
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin
import re
import logging

from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class ApolloAccordionScraper(BaseScraper):
    """Scraper for Apollo sites with accordion navigation"""

    def scrape(self, company, lookback_days=14):
        """
        Scrape press releases from Apollo sites that use accordion navigation.

        Apollo sites (like ARI) have press releases hidden in an accordion that must
        be clicked to reveal the content. Press releases are at /insights-news/pressreleases/.

        Args:
            company: Company model instance
            lookback_days: Only return releases from the last N days

        Returns:
            int: Number of new press releases saved to database
        """
        ir_url = company.ir_url
        if not ir_url:
            logger.warning(f"[{company.ticker}] No IR URL for Apollo accordion scrape")
            return 0

        logger.info(f"[{company.ticker}] Apollo accordion scrape: {ir_url}")

        try:
            page = self.browser.new_page()

            try:
                page.goto(ir_url, wait_until='domcontentloaded', timeout=30000)

                # Accept cookies
                try:
                    cookie_btn = page.query_selector(self.config['cookie_button'])
                    if cookie_btn and cookie_btn.is_visible():
                        cookie_btn.click()
                        page.wait_for_timeout(2000)
                except Exception:
                    pass

                # Find and click Press Releases accordion button
                pr_button = page.query_selector(self.config['accordion_button'])
                if pr_button:
                    logger.info(f"[{company.ticker}] Clicking Press Releases accordion")
                    pr_button.click()
                    page.wait_for_timeout(3000)

                # Extract press release links using config
                links = page.query_selector_all(self.config['link_selector'])
                logger.info(f"[{company.ticker}] Found {len(links)} press release links")

                raw_releases = []
                cutoff_date = datetime.now(timezone.utc) - timedelta(days=lookback_days)
                min_length = self.config['min_title_length']

                for link in links:
                    href = link.get_attribute('href') or ''
                    title = link.text_content().strip()

                    if not href or not title or len(title) < min_length:
                        continue

                    # Extract date from URL path: /pressreleases/YYYY/MM/
                    date_match = re.search(r'/pressreleases/(\d{4})/(\d{2})/', href)
                    if date_match:
                        year = int(date_match.group(1))
                        month = int(date_match.group(2))
                        # Default to first of the month, 9am ET (1pm UTC)
                        pub_date = datetime(year, month, 1, 13, 0, 0, tzinfo=timezone.utc)

                        if pub_date < cutoff_date:
                            continue

                        # Make URL absolute
                        full_url = urljoin(ir_url, href)

                        raw_releases.append({
                            'title': title,
                            'url': full_url,
                            'date': pub_date
                        })

                logger.info(f"[{company.ticker}] Found {len(raw_releases)} releases within {lookback_days} days")

            finally:
                page.close()

        except Exception as e:
            logger.error(f"[{company.ticker}] Apollo accordion scrape failed: {e}")
            return 0

        # Save to database using base class
        new_count = 0
        for release_data in raw_releases:
            if self.save_release(company, release_data):
                new_count += 1

        return new_count
