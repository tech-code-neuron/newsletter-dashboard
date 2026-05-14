"""
Parser URL Utilities - Modular Package
=======================================
Refactored from 671-line monolithic file to focused modules

SOLID Principles:
- Single Responsibility: Each module does ONE thing
- Facade Pattern: url_utils.py re-exports for backward compatibility

Modules:
- http_session.py: HTTP session with connection pooling
- url_extraction.py: Extract URLs from emails with priority scoring
- url_filtering.py: Filter press release URLs
- url_classification.py: Classify URLs as newswire/redirect/direct
- domain_utils.py: Extract domain from URLs
- url_validation.py: Validate URL accessibility
- redirect_following.py: Follow redirects with HEAD/GET fallback

Last Created: 2026-03-11
"""

__version__ = "2.0.0"
__author__ = "Press Release Pipeline"
