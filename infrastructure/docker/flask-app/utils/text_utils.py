"""
Text Utilities - Unicode normalization for search matching

Provides accent/diacritic-insensitive text matching.
Example: "Ivanhoe" matches "Ivanhoé Cambridge"
"""

import re
import unicodedata


def normalize_text(text: str) -> str:
    """
    Normalize text for accent-insensitive search matching.

    Uses NFKD decomposition to split characters like 'é' into 'e' + combining accent,
    then removes the combining diacritical marks (U+0300 to U+036F).

    Args:
        text: Text to normalize

    Returns:
        Lowercase text with diacritics removed

    Examples:
        >>> normalize_text("Ivanhoé Cambridge")
        'ivanhoe cambridge'
        >>> normalize_text("café")
        'cafe'
        >>> normalize_text("naïve résumé")
        'naive resume'
    """
    if not text:
        return ''
    # NFKD decomposition splits accented characters
    nfkd = unicodedata.normalize('NFKD', str(text))
    # Remove combining diacritical marks
    return re.sub(r'[\u0300-\u036f]', '', nfkd).lower()
