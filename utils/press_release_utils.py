"""
Press release utility functions.
Centralizes duplicate detection and validation logic (Single Responsibility).
"""
from difflib import SequenceMatcher
from core.models import PressRelease
from config.query_limits import MANUAL_ENTRY_RECENT_LIMIT
from utils.url_utils import normalize_url


# ------------------------------------------------------------------
# CONSTANTS - Duplicate Detection Configuration
# ------------------------------------------------------------------

# Similarity thresholds for duplicate detection
TITLE_SIMILARITY_THRESHOLD = 0.90
CONTENT_SIMILARITY_THRESHOLD = 0.90

# Content comparison settings
CONTENT_COMPARISON_MAX_WORDS = 1000  # Compare first N words to avoid long comparisons


# ------------------------------------------------------------------
# DUPLICATE DETECTION - Single Responsibility Pattern
# ------------------------------------------------------------------

def check_url_duplicate(db, company_id, url):
    """
    Check for duplicate press release by exact URL match.

    Args:
        db: Database session
        company_id: Company ID to search within
        url: URL to check (will be normalized)

    Returns:
        tuple: (is_duplicate, duplicate_release, similarity_score, match_type)
               Returns (True, release, 1.0, 'exact_url') if duplicate found
               Returns (False, None, 0.0, None) if no duplicate
    """
    normalized_url = normalize_url(url)

    # Get recent releases for this company
    recent_releases = db.query(PressRelease).filter(
        PressRelease.company_id == company_id,
        PressRelease.deleted_at.is_(None)
    ).order_by(PressRelease.published_date.desc()).limit(MANUAL_ENTRY_RECENT_LIMIT).all()

    # Check for exact URL match
    for existing in recent_releases:
        if normalize_url(existing.url) == normalized_url:
            return True, existing, 1.0, 'exact_url'

    return False, None, 0.0, None


def check_title_duplicate(db, company_id, title, similarity_threshold=None):
    """
    Check for duplicate press release by fuzzy title matching.

    Args:
        db: Database session
        company_id: Company ID to search within
        title: Title to check
        similarity_threshold: Similarity threshold (default: TITLE_SIMILARITY_THRESHOLD)

    Returns:
        tuple: (is_duplicate, duplicate_release, similarity_score, match_type)
               Returns (True, release, score, 'title') if duplicate found
               Returns (False, None, 0.0, None) if no duplicate
    """
    threshold = similarity_threshold or TITLE_SIMILARITY_THRESHOLD

    # Get recent releases for this company
    recent_releases = db.query(PressRelease).filter(
        PressRelease.company_id == company_id,
        PressRelease.deleted_at.is_(None)
    ).order_by(PressRelease.published_date.desc()).limit(MANUAL_ENTRY_RECENT_LIMIT).all()

    # Check for fuzzy title match
    for existing in recent_releases:
        if existing.title:
            title_similarity = calculate_text_similarity(title, existing.title)
            if title_similarity > threshold:
                return True, existing, title_similarity, 'title'

    return False, None, 0.0, None


def check_content_duplicate(db, company_id, full_text, similarity_threshold=None):
    """
    Check for duplicate press release by fuzzy content matching.

    Args:
        db: Database session
        company_id: Company ID to search within
        full_text: Full text content to check
        similarity_threshold: Similarity threshold (default: CONTENT_SIMILARITY_THRESHOLD)

    Returns:
        tuple: (is_duplicate, duplicate_release, similarity_score, match_type)
               Returns (True, release, score, 'content') if duplicate found
               Returns (False, None, 0.0, None) if no duplicate
    """
    if not full_text:
        return False, None, 0.0, None

    threshold = similarity_threshold or CONTENT_SIMILARITY_THRESHOLD

    # Get recent releases for this company
    recent_releases = db.query(PressRelease).filter(
        PressRelease.company_id == company_id,
        PressRelease.deleted_at.is_(None)
    ).order_by(PressRelease.published_date.desc()).limit(MANUAL_ENTRY_RECENT_LIMIT).all()

    # Check for fuzzy content match
    for existing in recent_releases:
        if existing.full_text:
            # Compare first N words to avoid very long comparisons
            content_similarity = calculate_content_similarity(
                full_text,
                existing.full_text,
                max_words=CONTENT_COMPARISON_MAX_WORDS
            )
            if content_similarity > threshold:
                return True, existing, content_similarity, 'content'

    return False, None, 0.0, None


def check_duplicate_release(db, company_id, title, url, full_text):
    """
    Check for duplicate press releases using multiple strategies.

    Orchestrator function that checks:
    1. Exact URL match (after normalization)
    2. Fuzzy title matching (>90% similar)
    3. Fuzzy content matching (>90% similar)

    Args:
        db: Database session
        company_id: Company ID to search within
        title: Press release title
        url: Press release URL
        full_text: Press release content

    Returns:
        tuple: (is_duplicate, duplicate_release, similarity_score, match_type)
               - is_duplicate: bool
               - duplicate_release: PressRelease object or None
               - similarity_score: float (0.0-1.0)
               - match_type: 'exact_url', 'title', 'content', or None
    """
    # Strategy 1: Exact URL match (fastest, most reliable)
    is_dup, dup, score, match_type = check_url_duplicate(db, company_id, url)
    if is_dup:
        return is_dup, dup, score, match_type

    # Strategy 2: Fuzzy title match
    is_dup, dup, score, match_type = check_title_duplicate(db, company_id, title)
    if is_dup:
        return is_dup, dup, score, match_type

    # Strategy 3: Fuzzy content match (slowest, most thorough)
    is_dup, dup, score, match_type = check_content_duplicate(db, company_id, full_text)
    if is_dup:
        return is_dup, dup, score, match_type

    # No duplicates found
    return False, None, 0.0, None


# ------------------------------------------------------------------
# SIMILARITY CALCULATION - Helper Functions
# ------------------------------------------------------------------

def calculate_text_similarity(text1, text2, case_sensitive=False):
    """
    Calculate similarity ratio between two text strings.

    Args:
        text1: First text
        text2: Second text
        case_sensitive: Whether to consider case (default: False)

    Returns:
        float: Similarity ratio (0.0-1.0)
    """
    if not text1 or not text2:
        return 0.0

    if not case_sensitive:
        text1 = text1.lower()
        text2 = text2.lower()

    return SequenceMatcher(None, text1, text2).ratio()


def calculate_content_similarity(text1, text2, max_words=None):
    """
    Calculate similarity ratio between two content strings.
    Optionally limit comparison to first N words for performance.

    Args:
        text1: First text
        text2: Second text
        max_words: Limit comparison to first N words (default: None = unlimited)

    Returns:
        float: Similarity ratio (0.0-1.0)
    """
    if not text1 or not text2:
        return 0.0

    # Limit to first N words if specified
    if max_words:
        text1_words = ' '.join(text1.split()[:max_words])
        text2_words = ' '.join(text2.split()[:max_words])
    else:
        text1_words = text1
        text2_words = text2

    return calculate_text_similarity(text1_words, text2_words)
