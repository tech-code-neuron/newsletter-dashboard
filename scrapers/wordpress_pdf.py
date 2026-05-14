"""
WordPress PDF platform scraper.
For WordPress sites with PDF press releases.
Companies: EPR, GTY, STAG
"""
from datetime import datetime, timedelta
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import pypdf
import io
import logging

from scrapers.base_scraper import BaseScraper
from models import PressRelease

logger = logging.getLogger(__name__)


class WordpressPdfScraper(BaseScraper):
    """Scraper for WordPress sites with PDF links"""

    def scrape(self, company, lookback_days=14):
        """
        Scrape press releases from WordPress sites with PDF links.

        These sites have press releases structured as:
        - <div class="news-list-item"> containers
        - Title in <strong> tag
        - Date in <span class="date"> tag
        - PDF link in <a class="btn btn-default">

        Tested against: STAG (STAG Industrial), EPR, GTY

        Args:
            company: Company model instance
            lookback_days: Only return releases from the last N days

        Returns:
            int: Number of new press releases saved to database
        """
        press_url = company.press_release_url or company.ir_url
        if not press_url:
            logger.warning(f"[{company.ticker}] No press release URL - skipping wordpress_pdf scrape")
            return 0

        logger.info(f"[{company.ticker}] WordPress PDF scrape: {press_url}")

        try:
            response = self.session.get(press_url, timeout=30)
            if response.status_code != 200:
                logger.warning(f"[{company.ticker}] HTTP {response.status_code} from {press_url}")
                return 0
        except Exception as e:
            logger.error(f"[{company.ticker}] Request failed: {e}")
            return 0

        soup = BeautifulSoup(response.content, 'html.parser')

        # Find all news list items using config
        news_items = soup.select(self.config['news_item_selector'])

        if not news_items:
            logger.info(f"[{company.ticker}] No news-list-item divs found on page")
            return 0

        logger.info(f"[{company.ticker}] Found {len(news_items)} news items")

        cutoff_date = datetime.now() - timedelta(days=lookback_days)
        releases = []

        for item in news_items:
            try:
                # Extract title using config
                title_elem = item.select_one(self.config['title_selector'])
                if not title_elem:
                    continue
                title = title_elem.get_text(strip=True)

                # Extract date using config
                date_elem = item.select_one(self.config['date_selector'])
                if not date_elem:
                    continue
                date_str = date_elem.get_text(strip=True)

                # Parse date using config format
                try:
                    pub_date = datetime.strptime(date_str, self.config['date_format'])
                    # Set to 4PM ET (9PM UTC) - typical after-hours release time
                    pub_date = pub_date.replace(hour=21, minute=0, second=0)
                except ValueError:
                    logger.debug(f"[{company.ticker}] Could not parse date: {date_str}")
                    continue

                # Check lookback window
                if (datetime.now() - pub_date).days > lookback_days:
                    continue

                # Extract PDF URL using config
                pdf_link = item.select_one(self.config['pdf_link_selector'])
                if not pdf_link:
                    continue
                pdf_url = pdf_link.get('href')

                if not pdf_url or '.pdf' not in pdf_url.lower():
                    continue

                # Make URL absolute if needed
                if not pdf_url.startswith('http'):
                    pdf_url = urljoin(press_url, pdf_url)

                releases.append({
                    'title': title,
                    'url': pdf_url,
                    'date': pub_date
                })

            except Exception as e:
                logger.debug(f"[{company.ticker}] Error parsing news item: {e}")
                continue

        logger.info(f"[{company.ticker}] {len(releases)} releases within lookback window")

        # Download PDFs and extract text
        new_count = 0
        for release_data in releases:
            # Check for duplicates
            existing = self.db_session.query(PressRelease).filter_by(url=release_data['url']).first()
            if existing:
                logger.debug(f"[{company.ticker}] Already have: {release_data['title'][:50]}")
                continue

            # Download and extract PDF text
            full_text = None
            try:
                logger.debug(f"[{company.ticker}] Downloading PDF: {release_data['url']}")
                pdf_response = self.session.get(release_data['url'], timeout=20)

                if pdf_response.status_code == 200:
                    pdf_file = io.BytesIO(pdf_response.content)
                    pdf_reader = pypdf.PdfReader(pdf_file)

                    # Extract text from first 5 pages (plenty for ~2000 words)
                    extracted_text = ""
                    num_pages = min(5, len(pdf_reader.pages))
                    for i in range(num_pages):
                        extracted_text += pdf_reader.pages[i].extract_text() + "\n"

                    # Truncate to ~2000 words
                    words = extracted_text.split()[:2000]
                    full_text = ' '.join(words)

                    logger.debug(f"[{company.ticker}] Extracted {len(words)} words from PDF")
                else:
                    logger.warning(f"[{company.ticker}] PDF download failed: HTTP {pdf_response.status_code}")

            except Exception as e:
                logger.warning(f"[{company.ticker}] PDF extraction failed for {release_data['url']}: {e}")
                # Continue saving even if PDF extraction fails - we have the metadata

            # Save to database
            press_release = PressRelease(
                company_id=company.id,
                title=release_data['title'],
                url=release_data['url'],
                published_date=release_data['date'],
                content=full_text or f"PDF link: {release_data['url']}",
                full_text=full_text,
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
