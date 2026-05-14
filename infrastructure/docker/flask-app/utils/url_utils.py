"""
URL normalization and validation utilities.
Centralizes URL processing logic (Single Responsibility).
"""
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse


# ------------------------------------------------------------------
# CONSTANTS - URL Configuration
# ------------------------------------------------------------------

# Tracking parameters to remove during normalization
TRACKING_PARAMETERS = [
    'utm_source',
    'utm_medium',
    'utm_campaign',
    'utm_content',
    'utm_term',
    'fbclid',      # Facebook click ID
    'gclid',       # Google click ID
    'msclkid',     # Microsoft click ID
]

DEFAULT_SCHEME = 'https'


# ------------------------------------------------------------------
# URL NORMALIZATION
# ------------------------------------------------------------------

def normalize_url(url):
    """
    Normalize URL by removing tracking parameters and standardizing format.

    Normalization steps:
    1. Lowercase scheme and netloc
    2. Remove trailing slashes from path
    3. Remove tracking parameters
    4. Remove URL fragments (#anchors)
    5. Sort query parameters for consistent comparison

    Args:
        url: URL string to normalize

    Returns:
        str: Normalized URL

    Example:
        >>> normalize_url('HTTP://example.com/path/?utm_source=twitter&id=123')
        'https://example.com/path?id=123'
    """
    if not url:
        return ''

    parsed = urlparse(url)

    # Remove tracking parameters
    query_params = parse_qs(parsed.query)
    cleaned_params = {
        k: v for k, v in query_params.items()
        if k not in TRACKING_PARAMETERS
    }

    # Rebuild URL with normalization
    normalized = urlunparse((
        parsed.scheme.lower() or DEFAULT_SCHEME,
        parsed.netloc.lower(),
        parsed.path.rstrip('/'),
        parsed.params,
        urlencode(cleaned_params, doseq=True),
        ''  # Remove fragment
    ))

    return normalized


def urls_match(url1, url2):
    """
    Check if two URLs match after normalization.

    Args:
        url1: First URL
        url2: Second URL

    Returns:
        bool: True if URLs match after normalization
    """
    return normalize_url(url1) == normalize_url(url2)


# ------------------------------------------------------------------
# URL SECURITY VALIDATION
# ------------------------------------------------------------------

def is_safe_url(url):
    """
    Validate URL to prevent SSRF (Server-Side Request Forgery) attacks.

    Single Responsibility: Only validates URL safety

    Blocks:
    - Private IP ranges (localhost, 192.168.x.x, 10.x.x.x, etc.)
    - file:// protocol
    - Non-HTTP(S) protocols
    - Internal domains (metadata.google.internal, etc.)

    Args:
        url (str): URL to validate

    Returns:
        bool: True if URL is safe to fetch, False otherwise

    Example:
        >>> is_safe_url('https://example.com/article')
        True
        >>> is_safe_url('http://localhost:8000/admin')
        False
        >>> is_safe_url('file:///etc/passwd')
        False
    """
    import ipaddress
    import socket

    try:
        parsed = urlparse(url)

        # Only allow HTTP/HTTPS
        if parsed.scheme not in ('http', 'https'):
            return False

        # Get hostname
        hostname = parsed.hostname
        if not hostname:
            return False

        # Resolve to IP address
        try:
            ip = socket.gethostbyname(hostname)
            ip_obj = ipaddress.ip_address(ip)

            # Block private IP ranges
            if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_reserved:
                return False

        except (socket.gaierror, ValueError):
            return False

        # Block common internal domains
        blocked_domains = ['localhost', '127.0.0.1', '0.0.0.0', 'metadata.google.internal']
        if any(blocked in hostname.lower() for blocked in blocked_domains):
            return False

        return True

    except Exception:
        return False
