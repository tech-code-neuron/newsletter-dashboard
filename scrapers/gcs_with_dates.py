"""
GCS with dates platform scraper.
For GCS sites that use /news-release-details/ pattern with date extraction.
Companies: SLG, SUI
"""
from datetime import datetime, timedelta
from urllib.parse import urljoin
from dateutil import parser as dateutil_parser
from bs4 import BeautifulSoup
import re
import logging

from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class GcsWithDatesScraper(BaseScraper):
    """Scraper for GCS sites with date extraction"""

    def scrape(self, company, lookback_days=14):
        """
        Scrape press releases from GCS sites that use /news-release-details/ pattern.

        Unlike standard GCS which uses /static-files/ links without dates,
        this variant visits each page to extract the publication date.

        Args:
            company: Company model instance
            lookback_days: Only return releases from the last N days

        Returns:
            int: Number of new press releases saved to database
        """
        press_url = company.press_release_url or company.ir_url
        if not press_url:
            logger.warning(f"[{company.ticker}] No URL for GCS scrape")
            return 0

        logger.info(f"[{company.ticker}] GCS (with dates) scrape: {press_url}")

        try:
            page = self.browser.new_page()

            try:
                page.goto(press_url, wait_until='domcontentloaded', timeout=60000)

                # Accept cookies
                try:
                    cookie_btn = page.query_selector(self.config['cookie_button'])
                    if cookie_btn and cookie_btn.is_visible():
                        cookie_btn.click()
                        page.wait_for_timeout(2000)
                except Exception:
                    pass

                # Scroll and wait
                page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(3000)
                page.evaluate("() => window.scrollTo(0, 0)")
                page.wait_for_timeout(2000)

                # Extract links using config
                links = page.query_selector_all(self.config['link_selector'])
                raw_releases = []

                url_pattern = self.config['link_url_pattern']
                for link in links:
                    href = link.get_attribute('href') or ''
                    text = (link.text_content() or '').strip()
                    if len(text) > 20 and url_pattern in href:
                        full_url = urljoin(press_url, href)
                        # Deduplicate
                        if not any(r['url'] == full_url for r in raw_releases):
                            raw_releases.append({'title': text, 'url': full_url})

                logger.info(f"[{company.ticker}] Found {len(raw_releases)} GCS press release links")

            finally:
                page.close()

        except Exception as e:
            logger.error(f"[{company.ticker}] GCS scrape failed: {e}")
            return 0

        # Visit each page to get dates and content
        cutoff_date = datetime.now() - timedelta(days=lookback_days)
        new_count = 0

        for release_data in raw_releases:
            try:
                # Check for duplicates first
                from models import PressRelease
                if self.db_session.query(PressRelease).filter_by(url=release_data['url']).first():
                    logger.debug(f"[{company.ticker}] Already have: {release_data['title'][:50]}")
                    continue

                # Fetch the page
                page = self.browser.new_page()
                try:
                    page.goto(release_data['url'], wait_until='domcontentloaded', timeout=30000)
                    page.wait_for_timeout(2000)
                    html_content = page.content()
                    soup = BeautifulSoup(html_content, 'html.parser')
                finally:
                    page.close()

                # Extract date from page
                pub_date = self._extract_date(soup)

                if not pub_date:
                    pub_date = datetime.now()

                # Check if within lookback
                if pub_date < cutoff_date:
                    continue

                # Extract content from the already-loaded page (more reliable than fetch_content)
                content = self._extract_content(soup)

                # Save with extracted date and content
                release_data['date'] = pub_date
                if self.save_release(company, release_data, content=content):
                    new_count += 1

            except Exception as e:
                logger.warning(f"[{company.ticker}] Error processing {release_data['url']}: {e}")
                continue

        return new_count

    def _extract_content(self, soup):
        """Extract text content from press release page"""
        from scrapers.base_scraper import MAX_CONTENT_LENGTH

        # Try to find the main content container (GCS-specific)
        content_div = soup.find('div', class_='amt-news-story')

        # Fallback to other common content containers
        if not content_div:
            content_div = soup.find('div', class_='node__content')
        if not content_div:
            content_div = soup.find('article')
        if not content_div:
            # Last resort: use entire body
            content_div = soup

        # Remove script and style elements
        for script in content_div(['script', 'style']):
            script.decompose()

        # Get text
        text = content_div.get_text()

        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)

        return text[:MAX_CONTENT_LENGTH]

    def _extract_date(self, soup):
        """Extract publication date from GCS page"""
        # Look for date patterns in <p> tags
        for p_tag in soup.find_all('p', limit=20):
            text = p_tag.get_text(strip=True)

            # Pattern like "Jan 28, 2026 at 4:05 PM EST"
            if ' at ' in text and ('AM' in text or 'PM' in text):
                try:
                    pub_date = dateutil_parser.parse(text)
                    return pub_date.replace(tzinfo=None) if pub_date.tzinfo else pub_date
                except Exception:
                    pass

            # Pattern like "BOSTON--(BUSINESS WIRE)--Feb. 24, 2026--"
            if 'BUSINESS WIRE' in text:
                try:
                    match = re.search(r'--([A-Z][a-z]{2,9}\.?\s+\d{1,2},\s+\d{4})--', text)
                    if match:
                        pub_date = dateutil_parser.parse(match.group(1))
                        return pub_date.replace(tzinfo=None) if pub_date.tzinfo else pub_date
                except Exception:
                    pass

            # Pattern like "NEW YORK, Jan. 28, 2026 (GLOBE NEWSWIRE)"
            if 'GLOBE NEWSWIRE' in text or 'PR NEWSWIRE' in text:
                try:
                    match = re.search(r'([A-Z][a-z]{2,9}\.?\s+\d{1,2},\s+\d{4})', text)
                    if match:
                        pub_date = dateutil_parser.parse(match.group(1))
                        return pub_date.replace(tzinfo=None) if pub_date.tzinfo else pub_date
                except Exception:
                    pass

        return None
