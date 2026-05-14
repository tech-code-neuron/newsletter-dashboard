"""
Q4 PDF platform scraper.
Company: HIW (Highwoods Properties)
"""
from datetime import datetime, timedelta
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import pypdf
import io
import logging

from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class Q4PdfScraper(BaseScraper):
    """Scraper for Q4 sites that link directly to PDFs"""

    def scrape(self, company, lookback_days=14):
        """
        Scrape press releases from Q4 sites that link to PDFs instead of HTML pages.

        These sites have a press releases listing page with direct links to PDFs
        (typically hosted on Q4 CDN). We scrape the HTML listing page, download
        each PDF within the lookback window, and extract text using pypdf.

        Args:
            company: Company model instance
            lookback_days: Only return releases from the last N days

        Returns:
            int: Number of new press releases saved to database
        """
        press_url = company.press_release_url or company.ir_url
        if not press_url:
            logger.warning(f"[{company.ticker}] No press release URL - skipping q4_pdf scrape")
            return 0

        logger.info(f"[{company.ticker}] Q4 PDF scrape: {press_url}")

        try:
            response = self.session.get(press_url, timeout=30)
            if response.status_code != 200:
                logger.warning(f"[{company.ticker}] HTTP {response.status_code} from {press_url}")
                return 0
        except Exception as e:
            logger.error(f"[{company.ticker}] Request failed: {e}")
            return 0

        soup = BeautifulSoup(response.content, 'html.parser')

        # Find all PDF links using config
        release_links = soup.select(self.config['link_selector'])

        if not release_links:
            logger.info(f"[{company.ticker}] No PressRelease links found on page")
            return 0

        logger.info(f"[{company.ticker}] Found {len(release_links)} PDF links")

        cutoff_date = datetime.now() - timedelta(days=lookback_days)
        releases = []

        for link in release_links:
            try:
                # Extract metadata from HTML structure using config
                date_elem = link.select_one(self.config['date_selector'])
                title_elem = link.find('h2', class_='h20')
                pdf_url = link.get('href')

                if not date_elem or not title_elem or not pdf_url:
                    continue

                # Parse date using config format
                date_str = date_elem.get_text(strip=True)
                try:
                    # Parse date and set time to 1pm UTC (9am ET)
                    pub_date = datetime.strptime(date_str, self.config['date_format']).replace(hour=13, minute=0, second=0)
                except ValueError:
                    logger.debug(f"[{company.ticker}] Could not parse date: {date_str}")
                    continue

                # Check lookback window
                if (datetime.now() - pub_date).days > lookback_days:
                    continue

                title = title_elem.get_text(strip=True)

                # Make URL absolute if needed
                if not pdf_url.startswith('http'):
                    pdf_url = urljoin(press_url, pdf_url)

                releases.append({
                    'title': title,
                    'url': pdf_url,
                    'date': pub_date
                })

            except Exception as e:
                logger.debug(f"[{company.ticker}] Error parsing PDF link: {e}")
                continue

        logger.info(f"[{company.ticker}] {len(releases)} releases within lookback window")

        # Download PDFs and extract text
        new_count = 0
        for release_data in releases:
            # Check for duplicates
            if self.db_session.query(self.db_session.query.__self__.__class__).filter_by(url=release_data['url']).first():
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

                    # Extract text from first 5 pages
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

            # Save using base class (with full_text)
            content = full_text or f"PDF link: {release_data['url']}"
            if self.save_release(company, release_data, content=content):
                new_count += 1

        return new_count
