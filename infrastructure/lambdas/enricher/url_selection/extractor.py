"""
Subject Word Extractor
======================
Single Responsibility: Extract significant words from email subjects
"""

import re
from config.constants import SUBJECT_NOISE_WORDS


def extract_significant_words(subject_line):
    """
    Extract meaningful words from subject line for URL matching

    Filters out:
    - Common noise words ('the', 'of', 'and', etc.)
    - Generic PR words ('announces', 'reports', 'releases')
    - Short words (<3 chars, except numbers)

    Args:
        subject_line: Email subject line

    Returns:
        list: Significant words (lowercase)
    """
    if not subject_line:
        return []

    # Extract words (lowercase, keep alphanumeric including numbers)
    words = re.findall(r'\b[a-z0-9]+\b', subject_line.lower())

    # Filter noise + keep words >= 3 chars (or numbers)
    significant = [
        w for w in words
        if (w not in SUBJECT_NOISE_WORDS and len(w) >= 3) or w.isdigit()
    ]

    return significant
