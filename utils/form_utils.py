"""
Form validation and sanitization utilities.
Centralizes form processing logic (Single Responsibility).
"""
from config.newsletter_config import (
    PRESS_RELEASE_TITLE_MAX_LENGTH,
    PRESS_RELEASE_MAX_WORDS
)


# ------------------------------------------------------------------
# FORM VALIDATION - Single Responsibility
# ------------------------------------------------------------------

def validate_press_release_form(form_data, required_fields=None):
    """
    Validate press release form data.

    Args:
        form_data: Form data dictionary (Flask request.form)
        required_fields: List of required field names (default: standard fields)

    Returns:
        tuple: (is_valid, error_message)
               is_valid: bool
               error_message: str or None
    """
    if required_fields is None:
        required_fields = ['company_id', 'title', 'url', 'date', 'time', 'full_text']

    for field in required_fields:
        value = form_data.get(field)

        # Check if value exists and is not empty (handle both strings and other types)
        if isinstance(value, str):
            if not value.strip():
                return False, f'Field "{field}" is required'
        elif not value:
            return False, f'Field "{field}" is required'

    return True, None


# ------------------------------------------------------------------
# DATA SANITIZATION - Single Responsibility
# ------------------------------------------------------------------

def sanitize_press_release_data(title, full_text):
    """
    Sanitize press release data (truncate title and text to limits).

    Args:
        title: Press release title
        full_text: Press release full text

    Returns:
        tuple: (sanitized_title, sanitized_text)
    """
    # Truncate title if too long
    if len(title) > PRESS_RELEASE_TITLE_MAX_LENGTH:
        title = title[:PRESS_RELEASE_TITLE_MAX_LENGTH - 3] + '...'

    # Limit to first N words
    words = full_text.split()
    if len(words) > PRESS_RELEASE_MAX_WORDS:
        full_text = ' '.join(words[:PRESS_RELEASE_MAX_WORDS]) + '...'

    return title, full_text


def sanitize_text(text, max_length):
    """
    Sanitize text to maximum length with ellipsis.

    Args:
        text: Text to sanitize
        max_length: Maximum length (including ellipsis)

    Returns:
        str: Sanitized text
    """
    if not text:
        return text

    if len(text) > max_length:
        return text[:max_length - 3] + '...'

    return text


def sanitize_text_words(text, max_words):
    """
    Sanitize text to maximum word count with ellipsis.

    Args:
        text: Text to sanitize
        max_words: Maximum number of words

    Returns:
        str: Sanitized text
    """
    if not text:
        return text

    words = text.split()
    if len(words) > max_words:
        return ' '.join(words[:max_words]) + '...'

    return text
