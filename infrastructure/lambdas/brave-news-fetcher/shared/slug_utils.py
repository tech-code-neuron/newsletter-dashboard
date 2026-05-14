"""
Slug Generation Utility
=======================
Generates URL-safe slugs for press release titles.
Used by social media pipeline for your-domain.com permalinks.

Usage:
    from shared.slug_utils import generate_release_slug
    slug = generate_release_slug('Realty Income Announces Q4 Results!')
    # Returns: 'realty-income-announces-q4-results'
"""

import re
from typing import Optional

MAX_SLUG_LENGTH = 60


def generate_release_slug(title: str) -> Optional[str]:
    """
    Generate URL-safe slug from press release title.

    Args:
        title: Press release title (e.g., 'Company XYZ Announces Q4 2026 Results!')

    Returns:
        URL-safe slug (e.g., 'company-xyz-announces-q4-2026-results'), max 60 chars
        Returns None if title is empty/None
    """
    if not title:
        return None

    slug = title.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    slug = slug.strip('-')

    if not slug:
        return None

    if len(slug) > MAX_SLUG_LENGTH:
        slug = slug[:MAX_SLUG_LENGTH].rsplit('-', 1)[0]

    return slug
