"""
Parser - URL Extraction with Context
=====================================
Extract URLs from emails with priority scoring

SOLID Principles:
- Single Responsibility: Only extracts URLs
- Priority scoring: Identifies most likely press release link

Last Created: 2026-03-11
"""

import re
import logging
from typing import List, Tuple
from constants import PRESS_RELEASE_LINK_KEYWORDS, PRESS_RELEASE_PATTERNS

logger = logging.getLogger()

# URL extraction regex
URL_PATTERN = re.compile(r'https?://[^\s<>"]+')


def extract_urls_with_context(html_body: str, plain_body: str = None) -> List[Tuple[str, str, int]]:
    """
    Extract URLs with link text context for prioritization

    Single Responsibility: Extracts URLs with context from HTML/plain text

    This fixes the "missed PR links" issue by:
    1. Extracting link text from HTML <a> tags
    2. Scoring URLs by likelihood of being the PR link
    3. Prioritizing "View Press Release", "Read More", etc.

    Priority scoring:
    - 100: Link text contains "press release", "full article", "read more", etc.
    - 50: URL domain matches company IR domain (checked later)
    - 10: URL contains /news/ or /press/ or /release/ or /detail/
    - 1: Any other URL

    Args:
        html_body: HTML email body
        plain_body: Plain text email body (fallback)

    Returns:
        list: Tuples of (url, link_text, priority_score) sorted by priority (highest first)
    """
    urls_with_context = []

    # Parse HTML to extract <a> tags with link text
    if html_body:
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html_body, 'html.parser')

            for link in soup.find_all('a', href=True):
                url = link['href']
                link_text = link.get_text(strip=True).lower()

                # Calculate priority score
                score = 1

                # High priority: Link text contains PR keywords
                if any(kw in link_text for kw in PRESS_RELEASE_LINK_KEYWORDS):
                    score = 100
                    logger.info(f"High-priority PR link found (text: '{link_text[:40]}'): {url[:60]}...")

                # Medium priority: URL contains PR path patterns
                elif any(p in url.lower() for p in ['/news/', '/press/', '/release/', '/detail/', '/newsroom/']):
                    score = 10

                urls_with_context.append((url, link_text, score))

        except ImportError:
            logger.warning("BeautifulSoup not available - falling back to plain text extraction")
        except Exception as e:
            logger.warning(f"Error parsing HTML for URL context: {e}")

    # Fallback: Extract URLs from plain text (no context, score=1)
    if plain_body and not urls_with_context:
        plain_urls = URL_PATTERN.findall(plain_body)
        urls_with_context = [(url.rstrip('.,;:)]}'), '', 1) for url in plain_urls]

    # Sort by priority score (highest first)
    urls_with_context.sort(key=lambda x: x[2], reverse=True)

    return urls_with_context


def extract_urls_from_email(msg) -> List[str]:
    """
    Extract URLs from email message with priority scoring

    Single Responsibility: Orchestrates email parsing + URL extraction

    Returns URLs sorted by priority (most likely PR link first)

    Args:
        msg: Email message object

    Returns:
        list: URLs sorted by priority (highest first)
    """
    html_body = None
    plain_body = None

    # Extract HTML and plain text bodies
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            try:
                if content_type == 'text/html':
                    html_body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                elif content_type == 'text/plain':
                    plain_body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
            except Exception as e:
                logger.warning(f"Error decoding email part ({content_type}): {e}")
    else:
        try:
            plain_body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
        except Exception as e:
            logger.warning(f"Error decoding email payload: {e}")

    # Extract URLs with context and priority
    urls_with_context = extract_urls_with_context(html_body, plain_body)

    # Return URLs only (already sorted by priority)
    return [url for url, _, _ in urls_with_context]


def extract_urls_from_text(text: str) -> List[str]:
    """
    Extract all URLs from text using regex

    Single Responsibility: Only extracts URLs

    DEPRECATED: Use extract_urls_from_email() for priority-based extraction

    Args:
        text: Plain text content

    Returns:
        list: URLs found in text
    """
    if not text:
        return []

    urls = URL_PATTERN.findall(text)
    # Clean up URLs (remove trailing punctuation)
    return [url.rstrip('.,;:)]}') for url in urls]
