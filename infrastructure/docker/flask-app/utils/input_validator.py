"""Security utilities for input validation and sanitization."""
import re
import uuid
from html import escape
from urllib.parse import urlparse

# Character restrictions for email (beyond standard email format)
EMAIL_DANGEROUS_CHARS = '<>"\'();\\`\n\r\x00'

# Allowed URL schemes for redirects
SAFE_URL_SCHEMES = {'http', 'https'}


def validate_email_strict(email: str) -> tuple[bool, str]:
    """
    Strict email validation with security checks.

    Returns:
        (is_valid, error_message or sanitized_email)
    """
    if not email or len(email) > 254:
        return False, 'Please enter a valid email address.'

    email = email.lower().strip()

    # Check for dangerous characters
    if any(char in email for char in EMAIL_DANGEROUS_CHARS):
        return False, 'Please enter a valid email address.'

    # Must have exactly one @ with content on both sides
    if email.count('@') != 1:
        return False, 'Please enter a valid email address.'

    local, domain = email.rsplit('@', 1)
    if not local or not domain or '.' not in domain:
        return False, 'Please enter a valid email address.'

    # Regex for allowed characters only (a-z, 0-9, . _ % + - @)
    if not re.match(r'^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$', email):
        return False, 'Please enter a valid email address.'

    return True, email


def validate_uuid_token(token: str) -> bool:
    """Validate token is a valid UUID4 format."""
    if not token or len(token) != 36:
        return False
    try:
        uuid.UUID(token, version=4)
        return True
    except (ValueError, AttributeError):
        return False


def validate_hex_string(value: str, length: int) -> bool:
    """Validate string is hex characters of exact length."""
    if not value or len(value) != length:
        return False
    return bool(re.match(r'^[0-9a-f]+$', value.lower()))


def sanitize_redirect_url(url: str, allowed_domains: set = None) -> str | None:
    """
    Sanitize URL for safe redirect.
    Returns None if URL is unsafe.
    """
    if not url:
        return None

    try:
        parsed = urlparse(url)
    except Exception:
        return None

    # Must have safe scheme
    if parsed.scheme.lower() not in SAFE_URL_SCHEMES:
        return None

    # Must have a host
    if not parsed.netloc:
        return None

    # Optional: domain whitelist
    if allowed_domains and parsed.netloc.lower() not in allowed_domains:
        return None

    return url


def sanitize_text_input(text: str, max_length: int = 500) -> str:
    """Sanitize text input - escape HTML and remove dangerous chars."""
    if not text:
        return ''

    # Remove null bytes and control characters (except newline/tab)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

    # Truncate
    text = text[:max_length]

    # HTML escape
    return escape(text)
