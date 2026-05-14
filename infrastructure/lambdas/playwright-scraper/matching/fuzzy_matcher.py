"""
Fuzzy Matcher - Title Similarity Matching
===========================================
Extracted from handler.py (lines 359-418)

SOLID: Single Responsibility - Only handles fuzzy title matching

Last Created: 2026-03-13
"""

import logging
from difflib import SequenceMatcher

logger = logging.getLogger()

# ============================================================================
# Constants
# ============================================================================

MIN_MATCH_SCORE = 0.6  # 60% similarity required for fuzzy match


# ============================================================================
# Fuzzy Matching Logic
# ============================================================================

def calculate_similarity(str1, str2):
    """
    Calculate similarity between two strings using SequenceMatcher

    Args:
        str1: First string
        str2: Second string

    Returns:
        float: Similarity score (0.0 to 1.0)
    """
    return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()


def find_matching_press_release(press_releases, email_subject, title_cleanup_fn=None):
    """
    Match email subject to scraped press release using fuzzy matching

    SOLID: Single Responsibility - Only handles matching logic

    Args:
        press_releases: List of scraped press releases [{title, url}, ...]
        email_subject: Email subject line to match
        title_cleanup_fn: Optional function name for title cleanup

    Returns:
        dict or None: Best matching press release {title, url, score} or None
    """
    logger.info(f"🔍 Matching: {email_subject[:60]}...")

    # Apply title cleanup if specified
    if title_cleanup_fn:
        logger.info(f"🧹 Applying title cleanup: {title_cleanup_fn}")
        # For now, just log - can implement cleanup functions as needed
        # This could call title_cleanup functions from a registry

    best_match = None
    best_score = 0

    for pr in press_releases:
        title = pr['title']
        score = calculate_similarity(email_subject, title)

        logger.debug(f"  {score:.2f}: {title[:60]}...")

        if score > best_score:
            best_score = score
            best_match = {
                'title': title,
                'url': pr['url'],
                'score': score
            }

    if best_match and best_score >= MIN_MATCH_SCORE:
        logger.info(f"✅ Match found (score: {best_score:.2f})")
        logger.info(f"   Title: {best_match['title'][:60]}...")
        logger.info(f"   URL: {best_match['url']}")
        return best_match
    else:
        logger.warning(f"⚠️  No good match (best score: {best_score:.2f} < {MIN_MATCH_SCORE})")
        return None
