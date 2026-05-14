"""
URL Scorer - Multi-Signal Scoring System
=========================================
Single Responsibility: Score URLs by specificity + content matching
"""

import logging
from url_selection.extractor import extract_significant_words
from url_selection.detector import is_landing_page, is_utility_page, get_path_depth
from config.constants import (
    SCORE_SUBJECT_MATCH,
    SCORE_PATH_DEPTH,
    PENALTY_LANDING_PAGE,
    PENALTY_DB_MATCH,
    PENALTY_UTILITY_PAGE
)

logger = logging.getLogger()


def score_url_by_subject(url, subject_line):
    """
    Score URL by how many subject words appear in the URL path

    Args:
        url: Full URL string
        subject_line: Email subject line

    Returns:
        int: Number of subject words found in URL
    """
    significant_words = extract_significant_words(subject_line)

    # Get the URL path (lowercase for matching)
    url_path = url.rstrip('/').lower()

    # Count matches
    matches = sum(1 for word in significant_words if word in url_path)

    return matches


def score_url(url, subject_line, press_release_url=''):
    """
    Score URL by specificity + subject match

    Scoring system:
    - Subject line matching: +100 per word (primary signal)
    - Path depth: +10 per segment (tiebreaker)
    - Landing page: -500 (heavy penalty)
    - Exact match to DB press_release_url: -800 (VERY heavy penalty)
    - Utility page: -1000 (exclusion)

    Args:
        url: Full URL string
        subject_line: Email subject line
        press_release_url: Database press_release_url field (to detect landing pages)

    Returns:
        int: URL score (higher = better match)
    """
    score = 0

    # 1. Subject line matching (primary signal)
    subject_matches = score_url_by_subject(url, subject_line)
    score += subject_matches * SCORE_SUBJECT_MATCH

    # 2. Path depth (tiebreaker - deeper = more specific)
    depth = get_path_depth(url)
    score += depth * SCORE_PATH_DEPTH

    # 3. Landing page penalty
    if is_landing_page(url):
        score += PENALTY_LANDING_PAGE

    # 4. HEAVY penalty if URL exactly matches database press_release_url
    if press_release_url and url.rstrip('/') == press_release_url.rstrip('/'):
        score += PENALTY_DB_MATCH
        logger.debug(f"URL matches database press_release_url exactly (landing page): {PENALTY_DB_MATCH} penalty")

    # 5. Utility page penalty
    if is_utility_page(url):
        score += PENALTY_UTILITY_PAGE

    return score
