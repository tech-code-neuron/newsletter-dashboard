"""
GCS (GlobeNewswire Corporate Solutions) platform scraper.
Sites on gcs-web.com with /static-files/UUID pattern.
"""
from datetime import datetime
from urllib.parse import urljoin
import logging

from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class GcsScraper(BaseScraper):
    """Scraper for GCS (GlobeNewswire Corporate Solutions) sites"""

    def scrape(self, company, lookback_days=14):
        """
        Scrape press releases from GCS sites.
        Sites on gcs-web.com with /static-files/UUID pattern.

        Args:
            company: Company model instance
            lookback_days: Only return releases from the last N days (used as count limit here)

        Returns:
            int: Number of new press releases saved to database
        """
        press_url = company.press_release_url or company.ir_url
        if not press_url:
            logger.warning(f"[{company.ticker}] No URL for GCS scrape")
            return 0

        logger.info(f"[{company.ticker}] GCS scrape: {press_url}")

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

                # Scroll and wait
                page.evaluate("() => window.scrollTo(0, 1000)")
                page.wait_for_timeout(3000)

                # Extract links using config
                links = page.query_selector_all(self.config['link_selector'])
                raw_releases = []

                url_pattern = self.config['link_url_pattern']
                for link in links:
                    href = link.get_attribute('href') or ''
                    text = (link.text_content() or '').strip()
                    if len(text) > 20 and url_pattern in href:
                        raw_releases.append({
                            'title': text,
                            'url': urljoin(press_url, href),
                            'date': datetime.now()  # GCS doesn't have dates on listing
                        })

                logger.info(f"[{company.ticker}] Found {len(raw_releases)} GCS links")

            finally:
                page.close()

        except Exception as e:
            logger.error(f"[{company.ticker}] GCS scrape failed: {e}")
            return 0

        # Save to database (limit by count since no dates)
        new_count = 0
        for release_data in raw_releases[:lookback_days]:
            if self.save_release(company, release_data):
                new_count += 1

        return new_count
