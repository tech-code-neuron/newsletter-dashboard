"""
Content Extractor - Extract Clean Text from HTML
=================================================
Extracts press release content from HTML for newsletter summaries

SOLID Principles:
- Single Responsibility: Only extracts content
- No Hardcoded Values: All constants defined
- DRY: Zero duplication

Last Created: 2026-03-11
"""

import logging
import re
from typing import Optional, Tuple

logger = logging.getLogger()

# ============================================================================
# Constants
# ============================================================================

# Maximum words to extract (for newsletter summaries)
MAX_WORDS = 2000

# Content selectors (try in priority order)
CONTENT_SELECTORS = [
    '.xn-content',              # Q4/GCS press releases (e.g., Brixmor)
    '.module_body',             # Q4 outer container
    'article',                  # Semantic HTML
    '[class*="release"]',       # Generic release containers
    '[class*="press"]',         # Generic press containers
    '.news-content',            # Common news class
    '.pr-content',              # PR content
    'main',                     # Semantic main content
]

# ============================================================================
# BeautifulSoup Availability Check
# ============================================================================

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    logger.warning("BeautifulSoup not available")


# ============================================================================
# Content Extraction
# ============================================================================

def extract_text_content(html: str) -> Tuple[Optional[str], int]:
    """
    Extract clean text from press release HTML

    Single Responsibility: Only extracts text content

    Strategy:
    1. Parse HTML with BeautifulSoup
    2. Try common press release content selectors (priority order)
    3. Fallback to body if no specific selector found
    4. Extract text and clean whitespace
    5. Limit to first 2000 words for newsletter summaries
    6. Return (text_preview, word_count)

    This extracts only what's needed for newsletter summaries,
    NOT full content (drives traffic to IR sites by linking back)

    Args:
        html: HTML string

    Returns:
        tuple: (text_preview, word_count) or (None, 0) if failed
    """
    if not BS4_AVAILABLE or not html:
        logger.warning("BeautifulSoup not available or no HTML")
        return None, 0

    try:
        # Step 1: Parse HTML
        soup = BeautifulSoup(html, 'html.parser')

        # Step 2: Try common press release content selectors
        content_div = None
        for selector in CONTENT_SELECTORS:
            content_div = soup.select_one(selector)
            if content_div:
                logger.info(f"Found content using selector: {selector}")
                break

        # Step 3: Fallback to body
        if not content_div:
            content_div = soup.find('body')
            logger.warning("No specific content selector found, using body")

        if not content_div:
            logger.error("No content found in HTML")
            return None, 0

        # Step 4: Extract text and clean whitespace
        text = content_div.get_text(separator=' ', strip=True)
        text = re.sub(r'\s+', ' ', text)

        # Step 5: Count words
        words = text.split()
        word_count = len(words)

        # Step 6: Extract first 2000 words
        if word_count > MAX_WORDS:
            preview = ' '.join(words[:MAX_WORDS])
            logger.info(f"Extracted {MAX_WORDS} words from {word_count} total")
        else:
            preview = text
            logger.info(f"Extracted all {word_count} words")

        return preview, word_count

    except Exception as e:
        logger.error(f"Error extracting content: {e}")
        return None, 0


def extract_company_domain(url: str) -> Optional[str]:
    """
    Extract company domain from URL

    Single Responsibility: Only extracts domain

    Example:
        "https://investors.terreno.com/press/123" → "investors.terreno.com"

    Args:
        url: URL string

    Returns:
        str: Domain (netloc) or None
    """
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
        return parsed.netloc
    except Exception as e:
        logger.error(f"Error extracting domain: {e}")
        return None


# ============================================================================
# Content Validation
# ============================================================================

def validate_extracted_content(text_preview: str, word_count: int, min_words: int = 50) -> bool:
    """
    Validate extracted content is substantial

    Single Responsibility: Only validates content

    Args:
        text_preview: Extracted text
        word_count: Word count
        min_words: Minimum words required (default: 50)

    Returns:
        bool: True if content is substantial
    """
    if not text_preview or word_count < min_words:
        logger.warning(f"Insufficient content: {word_count} words (min: {min_words})")
        return False

    return True
