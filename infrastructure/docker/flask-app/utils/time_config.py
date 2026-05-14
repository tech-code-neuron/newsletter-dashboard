"""
Date extraction strategies and patterns
Centralized date handling for press release scrapers
"""
import re
import logging

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
# DATE PATTERNS FOR Q4 DRUPAL SCRAPER
# ═══════════════════════════════════════════════════════════
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


def find_date_from_context(link_element, date_patterns=None, dateutil_parser=None):
    """
    SOLID: Single Responsibility - Extract date from DOM context

    Walk up from a link element through parents/siblings to find a date string.

    Q4 Drupal layouts vary — sometimes the date is in a <time> tag, sometimes
    in a <span> sibling, sometimes in a parent <div> or <td>. We check:
      1. <time> tag with datetime attr (most reliable)
      2. Parent containers (walk up to 4 levels, checking inline children)
      3. Previous siblings of the link element

    Args:
        link_element: BeautifulSoup element containing a press release link
        date_patterns: List of regex patterns to match date strings (defaults to Q4_DATE_PATTERNS)
        dateutil_parser: dateutil.parser module for parsing date strings

    Returns:
        datetime or None: Parsed date if found, None otherwise
    """
    if date_patterns is None:
        date_patterns = Q4_DATE_PATTERNS

    if dateutil_parser is None:
        from dateutil import parser as dateutil_parser

    # Strategy 1: Look for <time> element in link's parent
    parent = link_element.parent
    if parent:
        time_elem = parent.find('time')
        if time_elem and time_elem.get('datetime'):
            try:
                return dateutil_parser.parse(time_elem['datetime'])
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
                return dateutil_parser.parse(time_elem['datetime'])
            except (ValueError, TypeError):
                pass

        # Try regex patterns against collected text
        for pattern in date_patterns:
            match = re.search(pattern, text_to_search, re.I)
            if match:
                try:
                    return dateutil_parser.parse(match.group(1))
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
                            return dateutil_parser.parse(match.group(1))
                        except (ValueError, TypeError):
                            continue

    return None
