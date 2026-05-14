"""
Q4 detail platform scraper.
For Q4 sites using /press-releases/detail/[ID]/ URL pattern.
Companies: AVB, CDP, DX, MFA, NSA, OHI, ONL, PLD, SKT, VRE
"""
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin
from dateutil import parser as date_parser
import logging

from scrapers.base_scraper import BaseScraper
from models import PressRelease

logger = logging.getLogger(__name__)


class Q4DetailScraper(BaseScraper):
    """Scraper for Q4 sites with detail URL pattern"""

    def scrape(self, company, lookback_days=14):
        """
        Scrape press releases from Q4 sites using /press-releases/detail/[ID]/ URL pattern.

        This Q4 variant has a listing page with press releases in a consistent structure:
        - Each release in <div class="media-body">
        - Date in <time datetime="YYYY-MM-DDTHH:MM:SS"> tag
        - Title/link in <a href="/press-releases/detail/[ID]/slug">

        Tested against: OHI, VRE, AVB, PLD, CDP, DX, MFA, NSA, ONL, SKT

        Args:
            company: Company model instance
            lookback_days: Only return releases from the last N days

        Returns:
            int: Number of new press releases saved to database
        """
        press_url = company.press_release_url or company.ir_url
        if not press_url:
            logger.warning(f"[{company.ticker}] No URL for q4_detail scrape")
            return 0

        # Ensure URL points to press releases listing
        if '/press-releases' not in press_url:
            if press_url.endswith('/'):
                press_url = press_url + 'news-events/press-releases'
            else:
                press_url = press_url + '/news-events/press-releases'

        logger.info(f"[{company.ticker}] Q4 detail scrape: {press_url}")

        try:
            page = self.browser.new_page()

            try:
                page.goto(press_url, wait_until='domcontentloaded', timeout=30000)

                # Accept cookies if present
                try:
                    cookie_btn = page.query_selector(self.config['cookie_button'])
                    if cookie_btn and cookie_btn.is_visible():
                        cookie_btn.click()
                        page.wait_for_timeout(2000)
                except Exception:
                    pass

                # Wait for content
                page.wait_for_timeout(3000)

                # Find all press release links using config
                links = page.query_selector_all(self.config['link_selector'])
                logger.info(f"[{company.ticker}] Found {len(links)} links with {self.config['link_url_pattern']}")

                if len(links) == 0:
                    logger.warning(f"[{company.ticker}] No {self.config['link_url_pattern']} links found")
                    return 0

                raw_releases = []
                cutoff_date = datetime.now(timezone.utc) - timedelta(days=lookback_days)
                time_sel = self.config['time_selector']

                for link in links:
                    href = link.get_attribute('href') or ''
                    title = link.text_content().strip()

                    if not href or not title or len(title) < 10:
                        continue

                    # Find the datetime element (should be in parent container)
                    try:
                        # Navigate up to find the media-body container
                        container = link.evaluate_handle(f'''(el) => {{
                            let current = el;
                            for (let i = 0; i < 5; i++) {{
                                if (current.querySelector && current.querySelector('{time_sel}')) {{
                                    return current;
                                }}
                                current = current.parentElement;
                                if (!current) break;
                            }}
                            return null;
                        }}''')

                        if container:
                            time_elem = container.as_element().query_selector(time_sel)
                            if time_elem:
                                datetime_str = time_elem.get_attribute('datetime')
                                if datetime_str:
                                    # Parse the datetime
                                    pub_date = date_parser.parse(datetime_str)

                                    # Convert to UTC if not already
                                    if pub_date.tzinfo is None:
                                        pub_date = pub_date.replace(tzinfo=timezone.utc)
                                    else:
                                        pub_date = pub_date.astimezone(timezone.utc)

                                    # Filter by date
                                    if pub_date < cutoff_date:
                                        continue

                                    # Make URL absolute
                                    full_url = urljoin(press_url, href)

                                    raw_releases.append({
                                        'title': title,
                                        'url': full_url,
                                        'date': pub_date
                                    })
                    except Exception as e:
                        logger.debug(f"[{company.ticker}] Could not extract date for: {title[:50]} - {e}")
                        continue

                logger.info(f"[{company.ticker}] Found {len(raw_releases)} releases within {lookback_days} days")

            finally:
                page.close()

        except Exception as e:
            logger.error(f"[{company.ticker}] Q4 detail scrape failed: {e}")
            return 0

        # Save to database
        new_count = 0
        for release_data in raw_releases:
            # Skip if already exists
            if self.db_session.query(PressRelease).filter_by(url=release_data['url']).first():
                continue

            # Fetch content from the detail page
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
