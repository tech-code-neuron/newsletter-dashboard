"""
OLP PDF platform scraper.
For One Liberty Properties' PDF press releases with dates in filenames.
Company: OLP
"""
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin
import pypdf
import io
import re
import logging

from scrapers.base_scraper import BaseScraper
from models import PressRelease

logger = logging.getLogger(__name__)


class OlpPdfScraper(BaseScraper):
    """Scraper for One Liberty Properties PDF press releases"""

    def scrape(self, company, lookback_days=14):
        """
        Scrape press releases from One Liberty Properties (OLP) PDF listing page.

        OLP has PDFs at /filesystem/one-liberty-properties/News/Financial/YYYY/MM-DD-YY_OLP_PR_title.pdf
        Date is extracted from filename in MM-DD-YY format.

        Tested against: OLP (One Liberty Properties)

        Args:
            company: Company model instance
            lookback_days: Only return releases from the last N days

        Returns:
            int: Number of new press releases saved to database
        """
        press_url = company.press_release_url or company.ir_url
        if not press_url:
            logger.warning(f"[{company.ticker}] No URL for OLP PDF scrape")
            return 0

        logger.info(f"[{company.ticker}] OLP PDF scrape: {press_url}")

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

                # Find all PDF links using config
                pdf_links = page.query_selector_all(self.config['pdf_link_selector'])
                logger.info(f"[{company.ticker}] Found {len(pdf_links)} PDF links")

                raw_releases = []
                cutoff_date = datetime.now(timezone.utc) - timedelta(days=lookback_days)
                min_length = self.config['min_title_length']

                for link in pdf_links:
                    href = link.get_attribute('href') or ''
                    title = link.text_content().strip()

                    if not href or not title or len(title) < min_length:
                        continue

                    # Extract date from filename: MM-DD-YY_OLP_PR_title.pdf
                    date_match = re.search(r'/(\d{1,2})-(\d{1,2})-(\d{2})_', href)
                    if date_match:
                        month = int(date_match.group(1))
                        day = int(date_match.group(2))
                        year_short = int(date_match.group(3))
                        # Assume 20XX for the century
                        year = 2000 + year_short

                        try:
                            # Set time to 9am ET (1pm UTC) as default
                            pub_date = datetime(year, month, day, 13, 0, 0, tzinfo=timezone.utc)

                            if pub_date < cutoff_date:
                                continue

                            # Make URL absolute
                            full_url = urljoin(press_url, href)

                            raw_releases.append({
                                'title': title,
                                'url': full_url,
                                'date': pub_date
                            })
                        except ValueError as e:
                            logger.debug(f"[{company.ticker}] Invalid date in filename {href}: {e}")
                            continue

                logger.info(f"[{company.ticker}] Found {len(raw_releases)} releases within {lookback_days} days")

            finally:
                page.close()

        except Exception as e:
            logger.error(f"[{company.ticker}] OLP PDF scrape failed: {e}")
            return 0

        # Save to database
        new_count = 0
        for release_data in raw_releases:
            # Skip if already exists
            if self.db_session.query(PressRelease).filter_by(url=release_data['url']).first():
                continue

            # Download and extract PDF text
            try:
                pdf_response = self.session.get(release_data['url'], timeout=30)
                pdf_file = io.BytesIO(pdf_response.content)
                pdf_reader = pypdf.PdfReader(pdf_file)

                # Extract text from all pages (limit to ~2000 words)
                text_parts = []
                word_count = 0
                for page_obj in pdf_reader.pages:
                    page_text = page_obj.extract_text()
                    words = page_text.split()
                    if word_count + len(words) > 2000:
                        remaining = 2000 - word_count
                        text_parts.append(' '.join(words[:remaining]))
                        break
                    text_parts.append(page_text)
                    word_count += len(words)

                content = '\n\n'.join(text_parts)

            except Exception as e:
                logger.warning(f"[{company.ticker}] Could not extract PDF text from {release_data['url']}: {e}")
                content = f"[PDF content extraction failed: {e}]"

            press_release = PressRelease(
                company_id=company.id,
                title=release_data['title'],
                url=release_data['url'],
                published_date=release_data['date'],
                content=content,
                full_text=content,  # Store PDF text in full_text column
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
