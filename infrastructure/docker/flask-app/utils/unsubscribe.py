"""
Unsubscribe URL Generation - Shared across services and routes.

Centralizes HMAC-signed unsubscribe link generation to avoid
circular imports between routes and services.

SOLID Principle: Single Responsibility - only unsubscribe URL logic.
"""

import hmac
import hashlib
import os
from urllib.parse import urlencode


def generate_unsubscribe_signature(email: str) -> str:
    """
    Generate HMAC-SHA256 signature for unsubscribe link.

    Args:
        email: Subscriber email (will be lowercased)

    Returns:
        16-character hex signature

    Raises:
        ValueError: If UNSUBSCRIBE_SECRET is not set
    """
    secret = os.environ.get('UNSUBSCRIBE_SECRET')
    if not secret:
        raise ValueError("UNSUBSCRIBE_SECRET environment variable is required")
    return hmac.new(
        secret.encode(),
        email.lower().encode(),
        hashlib.sha256
    ).hexdigest()[:16]


def verify_unsubscribe_signature(email: str, signature: str) -> bool:
    """
    Verify HMAC signature for unsubscribe link (timing-safe).

    Args:
        email: Subscriber email
        signature: 16-character hex signature to verify

    Returns:
        True if signature is valid
    """
    expected = generate_unsubscribe_signature(email)
    return hmac.compare_digest(expected, signature)


def generate_unsubscribe_url(email: str) -> str:
    """
    Generate full unsubscribe URL with HMAC signature.

    Args:
        email: Subscriber email

    Returns:
        Full unsubscribe URL (e.g., https://reitsheet.co/unsubscribe?email=...&sig=...)
    """
    base_url = os.environ.get('PUBLIC_BASE_URL', 'https://reitsheet.co')
    sig = generate_unsubscribe_signature(email)
    params = urlencode({'email': email.lower(), 'sig': sig})
    return f"{base_url}/unsubscribe?{params}"
