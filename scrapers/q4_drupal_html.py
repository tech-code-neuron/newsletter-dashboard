"""
Q4 Drupal HTML platform scraper.
For Q4 Drupal sites that render press releases as standard HTML.
Companies: AAT, CCI, DLR, ABR, BXP, FRT, SPG, VNO, and 16 others (24 total)
"""
from datetime import datetime, timedelta
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from dateutil import parser as dateutil_parser
import re
import logging

from scrapers.base_scraper import BaseScraper
from models import PressRelease

logger = logging.getLogger(__name__)


# Date patterns used by Q4 Drupal HTML scraper
Q4_DATE_PATTERNS = [
    # Month DD, YYYY (with optional comma)
    r'((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})',
    # Abbreviated month: Jan DD, YYYY
    r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4})',
    # MM/DD/YYYY
    r'(\d{1,2}/\d{1,2}/\d{4})',
    # YYYY-MM-DD
    r'(\d{4}-\d{2}-\d{2})',
]


def _find_date_from_context(link_element, date_patterns, parser):
    """
    Walk up from a link element through parents/siblings to find a date string.

    Q4 Drupal layouts vary — sometimes the date is in a <time> tag, sometimes
    in a <span> sibling, sometimes in a parent <div> or <td>. We check:
      1. <time> tag with datetime attr (most reliable)
      2. Parent containers (walk up to 4 levels, checking inline children)
      3. Previous siblings of the link element
    """
    # Strategy 1: Look for <time> element in link's parent
    parent = link_element.parent
    if parent:
        time_elem = parent.find('time')
        if time_elem and time_elem.get('datetime'):
            try:
                return parser.parse(time_elem['datetime'])
            except (ValueError, TypeError):
                pass

    # Strategy 2: Walk up parent elements (up to 4 levels)
    current = link_element.parent
    for _ in range(4):
        if current is None:
            break

        # Collect text from direct children only (not deep nesting)
        # to avoid picking up dates from unrelated releases
        text_to_search = ""

        for child in current.children:
            if isinstance(child, str):
                text_to_search += child
            elif hasattr(child, 'name') and child.name in ('span', 'td', 'time', 'div', 'p', 'small'):
                child_text = child.get_text(strip=True)
                if len(child_text) < 50:  # Date strings are short
                    text_to_search += " " + child_text

        # Check for <time> at this level
        time_elem = current.find('time')
        if time_elem and time_elem.get('datetime'):
            try:
                return parser.parse(time_elem['datetime'])
            except (ValueError, TypeError):
                pass

        # Try regex patterns against collected text
        for pattern in date_patterns:
            match = re.search(pattern, text_to_search, re.I)
            if match:
                try:
                    return parser.parse(match.group(1))
                except (ValueError, TypeError):
                    continue

        current = current.parent

    # Strategy 3: Check previous siblings of the link
    for sibling in link_element.previous_siblings:
        if hasattr(sibling, 'get_text'):
            sib_text = sibling.get_text(strip=True)
            if len(sib_text) < 50:
                for pattern in date_patterns:
                    match = re.search(pattern, sib_text, re.I)
                    if match:
                        try:
                            return parser.parse(match.group(1))
                        except (ValueError, TypeError):
                            continue

    return None


class Q4DrupalHtmlScraper(BaseScraper):
    """Scraper for Q4 Drupal HTML-rendered IR pages"""

    def scrape(self, company, lookback_days=14):
        """
        Scrape press releases from Q4 Drupal-rendered IR pages.

        Q4 Drupal pages render press release links as standard HTML <a> tags
        with 'news-release-details' in the href. Dates are typically in a
        sibling or parent element as 'Month DD, YYYY' or 'MM/DD/YYYY'.

        Tested against: AAT, CCI, DLR, ABR, BXP, FRT, SPG, VNO, and others.

        Args:
            company: Company model instance
            lookback_days: Only return releases from the last N days

        Returns:
            int: Number of new press releases saved to database
        """
        press_url = company.press_release_url or company.ir_url
        if not press_url:
            logger.warning(f"[{company.ticker}] No press release URL — skipping q4_drupal scrape")
            return 0

        logger.info(f"[{company.ticker}] Q4 Drupal HTML scrape: {press_url}")

        try:
            response = self.session.get(press_url, timeout=30)
            if response.status_code != 200:
                logger.warning(f"[{company.ticker}] HTTP {response.status_code} from {press_url}")
                return 0
        except Exception as e:
            logger.error(f"[{company.ticker}] Request failed: {e}")
            return 0

        soup = BeautifulSoup(response.content, 'html.parser')

        # Find all Q4 Drupal press release links using config
        link_pattern = self.config['link_pattern']
        all_links = soup.find_all('a', href=re.compile(link_pattern, re.I))

        if not all_links:
            logger.info(f"[{company.ticker}] No '{link_pattern}' links found on page")
            return 0

        logger.info(f"[{company.ticker}] Found {len(all_links)} candidate links")

        cutoff_date = datetime.now() - timedelta(days=lookback_days)
        seen_urls = set()
        releases = []
        min_length = self.config['min_title_length']

        for link in all_links:
            title = link.get_text(strip=True)
            href = link.get('href', '')

            # Skip short text links using config
            if len(title) < min_length:
                continue

            full_url = urljoin(press_url, href)

            # Deduplicate by URL
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            # Find date by walking up parent elements
            pub_date = _find_date_from_context(link, Q4_DATE_PATTERNS, dateutil_parser)

            # Apply lookback filter
            if pub_date:
                if pub_date < cutoff_date:
                    continue
            else:
                logger.debug(f"[{company.ticker}] No date found for: {title[:60]}")

            releases.append({
                'title': title,
                'url': full_url,
                'date': pub_date,
            })

        logger.info(f"[{company.ticker}] {len(releases)} releases after filtering (lookback={lookback_days}d)")

        # Save new releases to database
        new_count = 0

        for release_data in releases:
            existing = self.db_session.query(PressRelease).filter_by(
                url=release_data['url']
            ).first()

            if existing:
                logger.debug(f"[{company.ticker}] Already have: {release_data['title'][:50]}")
                continue

            content = self.fetch_content(release_data['url'])

            press_release = PressRelease(
                company_id=company.id,
                title=release_data['title'],
                url=release_data['url'],
                published_date=release_data.get('date') or datetime.now(),
                content=content,
                category=None,
                included_in_newsletter=True
            )

            self.db_session.add(press_release)
            self.db_session.commit()
            new_count += 1

            logger.info(f"  ✓ [{company.ticker}] {release_data['title'][:60]}")

        return new_count
