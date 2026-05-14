"""
HTML Sanitization Utility

SOLID: Single Responsibility - HTML sanitization only
Extracted from app.py to promote reusability and testability

SECURITY: Uses bleach library (robust HTML parser) instead of regex
- Regex can miss edge cases (nested tags, HTML entities, null bytes, CSS-based XSS)
- Bleach uses proper HTML parsing for comprehensive protection
"""
import bleach
import re


# Allowed HTML tags for email display (safe subset)
ALLOWED_TAGS = [
    'p', 'br', 'strong', 'em', 'u', 'b', 'i', 'ul', 'ol', 'li',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'code', 'pre',
    'div', 'span', 'table', 'thead', 'tbody', 'tr', 'th', 'td'
]

# Allowed HTML attributes (very restricted for security)
ALLOWED_ATTRS = {
    '*': ['class'],  # Allow class for styling only
    # Note: href deliberately excluded to prevent navigation/tracking
}


def sanitize_email_html(html_content):
    """
    Sanitize HTML content from emails to prevent XSS and tracking.

    Uses bleach library for robust HTML parsing (not regex).

    Removes:
    - Script tags and content
    - Event handlers (onclick, onload, etc.)
    - javascript: protocol
    - data: URLs (can contain base64 encoded scripts)
    - href attributes (prevents navigation/tracking)
    - All images (prevents tracking pixels)
    - All tags/attributes not explicitly allowed

    Args:
        html_content: Raw HTML string

    Returns:
        str: Sanitized HTML safe for display in iframe
    """
    if not html_content:
        return html_content

    # Step 1: Use bleach to strip all non-allowed tags and attributes
    # This handles nested tags, HTML entities, null bytes, CSS-based XSS, etc.
    html_content = bleach.clean(
        html_content,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        strip=True  # Strip disallowed tags instead of escaping them
    )

    # Step 2: Remove ALL images to prevent tracking pixels
    # (bleach doesn't allow img tags, but this is belt-and-suspenders)
    html_content = re.sub(
        r'<img[^>]*>',
        '[Image Removed]',
        html_content,
        flags=re.IGNORECASE
    )

    # Step 3: Remove background images in CSS
    html_content = re.sub(
        r'background(-image)?\s*:\s*url\([^)]+\)',
        'background: none',
        html_content,
        flags=re.IGNORECASE
    )

    return html_content
