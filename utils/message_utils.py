"""
Message formatting utilities for flash messages and notifications.
Centralizes message creation logic (Single Responsibility).
"""
from flask import url_for
from markupsafe import Markup
from config.newsletter_config import DUPLICATE_WARNING_TEMPLATE


# ------------------------------------------------------------------
# DUPLICATE WARNING MESSAGES
# ------------------------------------------------------------------

def create_duplicate_warning_message(duplicate, match_type, similarity):
    """
    Create formatted duplicate warning message for flash display.

    Args:
        duplicate: Duplicate PressRelease object
        match_type: 'exact_url', 'title', or 'content'
        similarity: Float similarity score (0.0-1.0)

    Returns:
        Markup: Safe HTML markup for flash message
    """
    # Data-driven match type descriptions (Open/Closed)
    match_type_descriptions = {
        'exact_url': 'Exact URL match',
        'title': f'Similar title ({similarity:.0%})',
        'content': f'Similar content ({similarity:.0%})'
    }

    match_type_text = match_type_descriptions.get(
        match_type,
        f'Match detected ({similarity:.0%})'  # Fallback
    )

    edit_url = url_for('edit_press_release', release_id=duplicate.id)

    return Markup(
        DUPLICATE_WARNING_TEMPLATE.format(
            match_type=match_type_text,
            edit_url=edit_url
        )
    )
