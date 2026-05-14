"""
Investis platform scraper.
For Investis-hosted IR sites with /investors/press-releases/ pattern.
Companies: O (Realty Income), PK (Park Hotels)
"""
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin
from dateutil import parser as date_parser
import logging

from scrapers.base_scraper import BaseScraper
from models import PressRelease

logger = logging.getLogger(__name__)


class InvestisScraper(BaseScraper):
    """Scraper for Investis platform sites"""

    def scrape(self, company, lookback_days=14):
        """
        Scrape press releases from Investis platform sites.

        Investis sites have press releases at /investors/press-releases/title-slug pattern.
        Each release has a date element that we extract.

        Tested against: O (Realty Income), PK (Park Hotels)

        Args:
            company: Company model instance
            lookback_days: Only return releases from the last N days

        Returns:
            int: Number of new press releases saved to database
        """
        press_url = company.press_release_url or company.ir_url
        if not press_url:
            logger.warning(f"[{company.ticker}] No URL for Investis scrape")
            return 0

        # Ensure URL points to press releases
        if '/press-releases' not in press_url:
            if press_url.endswith('/'):
                press_url = press_url + 'investors/press-releases'
            else:
                press_url = press_url + '/investors/press-releases'

        logger.info(f"[{company.ticker}] Investis scrape: {press_url}")

        try:
            page = self.browser.new_page()

            try:
                page.goto(press_url, wait_until='domcontentloaded', timeout=30000)

                # Accept cookies
                try:
                    for selector in self.config['cookie_buttons']:
                        cookie_btn = page.query_selector(selector)
                        if cookie_btn and cookie_btn.is_visible():
                            cookie_btn.click()
                            page.wait_for_timeout(2000)
                            break
                except Exception:
                    pass

                # Scroll to load content
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(3000)

                # Find press release links using config
                links = page.query_selector_all(self.config['link_selector'])
                logger.info(f"[{company.ticker}] Found {len(links)} links with {self.config['link_url_pattern']}")

                raw_releases = []
                cutoff_date = datetime.now(timezone.utc) - timedelta(days=lookback_days)

                min_length = self.config['min_title_length']
                time_sel = self.config['time_selector']
                date_sel = self.config['date_selector']

                for link in links:
                    href = link.get_attribute('href') or ''
                    title = link.text_content().strip()

                    # Skip navigation links (just /press-releases with nothing after)
                    if not href or not title or len(title) < min_length:
                        continue
                    if href.endswith('/press-releases') or href.endswith('/press-releases/'):
                        continue

                    # Try to find date in the parent container
                    try:
                        # Walk up to find container with date
                        container = link.evaluate_handle(f'''(el) => {{
                            let current = el;
                            for (let i = 0; i < 5; i++) {{
                                if (current.querySelector && (current.querySelector('{time_sel}') || current.querySelector('{date_sel}'))) {{
                                    return current;
                                }}
                                current = current.parentElement;
                                if (!current) break;
                            }}
                            return null;
                        }}''')

                        pub_date = None
                        if container:
                            # Try time element first
                            time_elem = container.as_element().query_selector(time_sel)
                            if time_elem:
                                datetime_str = time_elem.get_attribute('datetime')
                                if datetime_str:
                                    pub_date = date_parser.parse(datetime_str)

                            # Try date span/div
                            if not pub_date:
                                date_elem = container.as_element().query_selector(date_sel)
                                if date_elem:
                                    date_text = date_elem.text_content().strip()
                                    if date_text:
                                        try:
                                            pub_date = date_parser.parse(date_text)
                                        except:
                                            pass

                        if not pub_date:
                            # Default to current date if we can't extract
                            pub_date = datetime.now(timezone.utc)

                        # Convert to UTC
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
            logger.error(f"[{company.ticker}] Investis scrape failed: {e}")
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
