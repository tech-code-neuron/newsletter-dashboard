"""
Date-slug platform scraper.
For sites with dates embedded in URLs (/YYYY-MM-DD-Title-Slug pattern).
Companies: WY (Weyerhaeuser), ACR (ACRES Commercial Realty)
"""
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin
import re
import logging

from scrapers.base_scraper import BaseScraper
from models import PressRelease

logger = logging.getLogger(__name__)


class DateSlugScraper(BaseScraper):
    """Scraper for sites with date-in-URL pattern"""

    def scrape(self, company, lookback_days=14):
        """
        Scrape press releases from sites with /YYYY-MM-DD-Title-Slug URL pattern.

        These sites embed the date in the URL path. Used for sites like WY and ACR.

        Tested against: WY (Weyerhaeuser), ACR (ACRES Commercial Realty)

        Args:
            company: Company model instance
            lookback_days: Only return releases from the last N days

        Returns:
            int: Number of new press releases saved to database
        """
        press_url = company.press_release_url or company.ir_url
        if not press_url:
            logger.warning(f"[{company.ticker}] No URL for date-slug scrape")
            return 0

        logger.info(f"[{company.ticker}] Date-slug scrape: {press_url}")

        try:
            page = self.browser.new_page()

            try:
                page.goto(press_url, wait_until='domcontentloaded', timeout=30000)

                # Accept cookies
                try:
                    cookie_btn = page.query_selector('button:has-text("Accept")')
                    if cookie_btn and cookie_btn.is_visible():
                        cookie_btn.click()
                        page.wait_for_timeout(2000)
                except Exception:
                    pass

                # Scroll to load all content
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(3000)

                # Find all links using config
                all_links = page.query_selector_all(self.config['link_selector'])
                logger.info(f"[{company.ticker}] Checking {len(all_links)} links for date-slug pattern")

                raw_releases = []
                cutoff_date = datetime.now(timezone.utc) - timedelta(days=lookback_days)
                min_length = self.config['min_title_length']

                for link in all_links:
                    href = link.get_attribute('href') or ''

                    # Match date pattern in URL using config regex
                    date_match = re.search(r'/(\d{4})-(\d{2})-(\d{2})-', href)
                    if date_match:
                        year = int(date_match.group(1))
                        month = int(date_match.group(2))
                        day = int(date_match.group(3))

                        try:
                            # Set time to 9am ET (1pm UTC) as default
                            pub_date = datetime(year, month, day, 13, 0, 0, tzinfo=timezone.utc)

                            if pub_date < cutoff_date:
                                continue

                            # Extract title from link text or URL
                            title = link.text_content().strip()
                            if not title or len(title) < min_length:
                                # Extract from URL slug
                                slug = href.split(f'{year}-{month:02d}-{day:02d}-', 1)[1] if f'{year}-{month:02d}-{day:02d}-' in href else ''
                                title = slug.replace('-', ' ').strip()

                            if not title or len(title) < min_length:
                                continue

                            # Make URL absolute
                            full_url = urljoin(press_url, href)

                            raw_releases.append({
                                'title': title[:200],
                                'url': full_url,
                                'date': pub_date
                            })

                        except ValueError as e:
                            logger.debug(f"[{company.ticker}] Invalid date in URL {href}: {e}")
                            continue

                logger.info(f"[{company.ticker}] Found {len(raw_releases)} releases within {lookback_days} days")

            finally:
                page.close()

        except Exception as e:
            logger.error(f"[{company.ticker}] Date-slug scrape failed: {e}")
            return 0

        # Save to database
        new_count = 0
        for release_data in raw_releases:
            # Skip if already exists
            if self.db_session.query(PressRelease).filter_by(url=release_data['url']).first():
                continue

            # Fetch content
            content = self.fetch_content(release_data['url'])

            press_release = PressRelease(
                company_id=company.id,
                title=release_data['title'],
                url=release_data['url'],
                published_date=release_data['date'],
                content=content,
                category=None,
                included_in_newsletter=True
            )

            self.db_session.add(press_release)
            new_count += 1

            date_str = release_data['date'].strftime('%Y-%m-%d')
            logger.info(f"  ✓ [{company.ticker}] ({date_str}) {release_data['title'][:60]}")

        if new_count > 0:
            self.db_session.commit()

        return new_count
