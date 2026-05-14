"""
HTML Sanitization Utility

SOLID: Single Responsibility - HTML sanitization only
Extracted from app.py to promote reusability and testability
"""
import re


def sanitize_email_html(html_content):
    """
    Sanitize HTML content from emails to prevent XSS and tracking.

    Removes:
    - Script tags and content
    - Event handlers (onclick, onload, etc.)
    - javascript: protocol
    - data: URLs (can contain base64 encoded scripts)
    - href attributes (prevents navigation)
    - All images (prevents tracking pixels)
    - Background images in CSS

    Args:
        html_content: Raw HTML string

    Returns:
        str: Sanitized HTML safe for display in iframe
    """
    if not html_content:
        return html_content

    # Remove script tags and their content
    html_content = re.sub(
        r'<script[^>]*>.*?</script>',
        '',
        html_content,
        flags=re.DOTALL | re.IGNORECASE
    )

    # Remove event handlers (onclick, onload, etc.)
    html_content = re.sub(
        r'\s*on\w+\s*=\s*["\'][^"\']*["\']',
        '',
        html_content,
        flags=re.IGNORECASE
    )
    html_content = re.sub(
        r'\s*on\w+\s*=\s*[^\s>]+',
        '',
        html_content,
        flags=re.IGNORECASE
    )

    # Remove javascript: protocol
    html_content = re.sub(
        r'javascript:',
        '',
        html_content,
        flags=re.IGNORECASE
    )

    # Remove data: URLs (can contain base64 encoded scripts)
    html_content = re.sub(
        r'data:[^"\'>\s]+',
        '',
        html_content,
        flags=re.IGNORECASE
    )

    # Disable all links by removing href attributes (prevents navigation)
    html_content = re.sub(
        r'<a\s+([^>]*\s+)?href\s*=\s*["\'][^"\']*["\']',
        '<a \\1',
        html_content,
        flags=re.IGNORECASE
    )
    html_content = re.sub(
        r'<a\s+([^>]*\s+)?href\s*=\s*[^\s>]+',
        '<a \\1',
        html_content,
        flags=re.IGNORECASE
    )

    # SECURITY: Remove ALL images to prevent tracking pixels
    html_content = re.sub(
        r'<img[^>]*>',
        '[Image Removed]',
        html_content,
        flags=re.IGNORECASE
    )

    # Remove background images in CSS
    html_content = re.sub(
        r'background(-image)?\s*:\s*url\([^)]+\)',
        'background: none',
        html_content,
        flags=re.IGNORECASE
    )

    return html_content
