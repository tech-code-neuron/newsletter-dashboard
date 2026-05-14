"""
Press Release Date Extraction

Extracts publication dates from press release pages using multiple strategies:
1. Schema.org structured data (datePublished, dateModified)
2. Open Graph meta tags (article:published_time)
3. Common meta tag patterns (published_date, date, etc.)
4. Article/time HTML elements with datetime attributes
5. URL patterns (e.g., /2026/03/12/ or /news/2026-03-12-)
"""

import re
from datetime import datetime
from typing import Optional
from bs4 import BeautifulSoup

def extract_date_from_html(html: str, url: str) -> Optional[str]:
    """
    Extract press release date from HTML content.

    Returns ISO 8601 formatted date string (YYYY-MM-DD) or None if not found.
    """

    if not html:
        return None

    try:
        soup = BeautifulSoup(html, 'html.parser')

        # Strategy 1: Schema.org structured data
        date = extract_from_schema_org(soup)
        if date:
            return date

        # Strategy 2: Open Graph meta tags
        date = extract_from_open_graph(soup)
        if date:
            return date

        # Strategy 3: Common meta tags
        date = extract_from_meta_tags(soup)
        if date:
            return date

        # Strategy 4: HTML5 time elements
        date = extract_from_time_elements(soup)
        if date:
            return date

        # Strategy 5: URL patterns
        date = extract_from_url(url)
        if date:
            return date

    except Exception as e:
        print(f"Error extracting date: {e}")

    return None

def extract_from_schema_org(soup: BeautifulSoup) -> Optional[str]:
    """Extract date from Schema.org structured data (JSON-LD)."""

    scripts = soup.find_all('script', type='application/ld+json')

    for script in scripts:
        try:
            import json
            data = json.loads(script.string)

            # Handle single object or array
            items = data if isinstance(data, list) else [data]

            for item in items:
                # Look for datePublished or dateModified
                for key in ['datePublished', 'dateModified', 'dateCreated']:
                    if key in item:
                        return parse_date_string(item[key])
        except:
            continue

    return None

def extract_from_open_graph(soup: BeautifulSoup) -> Optional[str]:
    """Extract date from Open Graph meta tags."""

    # article:published_time is the standard OG tag for article dates
    og_date = soup.find('meta', property='article:published_time')
    if og_date and og_date.get('content'):
        return parse_date_string(og_date['content'])

    # Also check for modified time
    og_modified = soup.find('meta', property='article:modified_time')
    if og_modified and og_modified.get('content'):
        return parse_date_string(og_modified['content'])

    return None

def extract_from_meta_tags(soup: BeautifulSoup) -> Optional[str]:
    """Extract date from common meta tag patterns."""

    # Common meta tag names for publication dates
    meta_names = [
        'date',
        'publishdate',
        'publish_date',
        'published',
        'pubdate',
        'publication_date',
        'sailthru.date',
        'article.published',
        'article:published_time',
        'DC.date.issued',
        'dcterms.created',
    ]

    for name in meta_names:
        # Try as name attribute
        meta = soup.find('meta', attrs={'name': name})
        if meta and meta.get('content'):
            date = parse_date_string(meta['content'])
            if date:
                return date

        # Try as property attribute
        meta = soup.find('meta', attrs={'property': name})
        if meta and meta.get('content'):
            date = parse_date_string(meta['content'])
            if date:
                return date

    return None

def extract_from_time_elements(soup: BeautifulSoup) -> Optional[str]:
    """Extract date from HTML5 <time> elements."""

    # Look for time elements with datetime attribute
    time_elements = soup.find_all('time', datetime=True)

    for time_elem in time_elements:
        datetime_attr = time_elem.get('datetime')
        if datetime_attr:
            date = parse_date_string(datetime_attr)
            if date:
                return date

    # Also check for class names that might indicate date
    date_classes = ['date', 'published', 'entry-date', 'post-date', 'article-date']
    for class_name in date_classes:
        time_elem = soup.find('time', class_=re.compile(class_name, re.I))
        if time_elem and time_elem.get('datetime'):
            date = parse_date_string(time_elem['datetime'])
            if date:
                return date

    return None

def extract_from_url(url: str) -> Optional[str]:
    """Extract date from URL patterns."""

    # Pattern 1: /YYYY/MM/DD/ (e.g., /2026/03/12/)
    match = re.search(r'/(\d{4})/(\d{2})/(\d{2})/', url)
    if match:
        year, month, day = match.groups()
        return f"{year}-{month}-{day}"

    # Pattern 2: /YYYY-MM-DD/ or /YYYY-MM-DD- (e.g., /2026-03-12/ or /news/2026-03-12-)
    match = re.search(r'/(\d{4})-(\d{2})-(\d{2})', url)
    if match:
        year, month, day = match.groups()
        return f"{year}-{month}-{day}"

    # Pattern 3: /YYYYMMDD/ (e.g., /20260312/)
    match = re.search(r'/(\d{4})(\d{2})(\d{2})', url)
    if match:
        year, month, day = match.groups()
        return f"{year}-{month}-{day}"

    return None

def parse_date_string(date_str: str) -> Optional[str]:
    """
    Parse various date string formats to ISO 8601 (YYYY-MM-DD).

    Handles:
    - ISO 8601: 2026-03-12T10:30:00Z
    - RFC 2822: Mon, 12 Mar 2026 10:30:00 GMT
    - Common formats: March 12, 2026 / 03/12/2026 / etc.
    """

    if not date_str:
        return None

    # Clean up the string
    date_str = date_str.strip()

    # List of date format patterns to try
    formats = [
        '%Y-%m-%dT%H:%M:%S%z',      # 2026-03-12T10:30:00+00:00
        '%Y-%m-%dT%H:%M:%SZ',        # 2026-03-12T10:30:00Z
        '%Y-%m-%d %H:%M:%S',         # 2026-03-12 10:30:00
        '%Y-%m-%d',                  # 2026-03-12
        '%Y/%m/%d',                  # 2026/03/12
        '%m/%d/%Y',                  # 03/12/2026
        '%m-%d-%Y',                  # 03-12-2026
        '%B %d, %Y',                 # March 12, 2026
        '%b %d, %Y',                 # Mar 12, 2026
        '%d %B %Y',                  # 12 March 2026
        '%d %b %Y',                  # 12 Mar 2026
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime('%Y-%m-%d')
        except ValueError:
            continue

    # Try parsing with dateutil as fallback (if available)
    try:
        from dateutil import parser
        dt = parser.parse(date_str)
        return dt.strftime('%Y-%m-%d')
    except:
        pass

    return None
