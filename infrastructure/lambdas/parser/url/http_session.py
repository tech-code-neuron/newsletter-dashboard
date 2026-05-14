"""
Parser - HTTP Session Management
=================================
HTTP session with connection pooling

SOLID Principles:
- Single Responsibility: Only manages HTTP sessions
- Module-level caching: Persists across Lambda warm starts

Last Created: 2026-03-11
"""

import logging
import requests
from requests.adapters import HTTPAdapter

logger = logging.getLogger()

# ============================================================================
# Module-Level HTTP Session (Persists Across Lambda Invocations)
# ============================================================================

HTTP_SESSION = None


def get_http_session():
    """
    Get or create HTTP session with connection pooling

    Single Responsibility: Only manages HTTP session

    Connection pool settings:
    - Pool size: 10 connections
    - Max retries: 0 (we handle retries ourselves)
    - Timeout: Configurable per request

    Persists across Lambda warm starts for connection reuse

    Returns:
        requests.Session: Configured session with connection pooling
    """
    global HTTP_SESSION

    if HTTP_SESSION is None:
        HTTP_SESSION = requests.Session()

        # Configure connection pooling
        adapter = HTTPAdapter(
            pool_connections=10,
            pool_maxsize=10,
            max_retries=0  # We handle retries ourselves
        )

        HTTP_SESSION.mount('http://', adapter)
        HTTP_SESSION.mount('https://', adapter)

        logger.info("Created HTTP session with connection pooling")

    return HTTP_SESSION


def close_http_session():
    """
    Close HTTP session and clear connection pool

    Single Responsibility: Only closes session

    Useful for:
    - Testing
    - Memory cleanup
    - Forcing fresh sessions
    """
    global HTTP_SESSION

    if HTTP_SESSION is not None:
        HTTP_SESSION.close()
        HTTP_SESSION = None
        logger.info("HTTP session closed")
