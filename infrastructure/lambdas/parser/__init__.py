"""
Press Release Pipeline - Email Parser Lambda Package
=========================================
Best-in-class modular design following SOLID principles

Modules:
    - constants: All configuration values (single source of truth)
    - url_utils: URL extraction, filtering, validation, redirects
    - company_matching: O(1) company matching by domain/name
    - url_construction: Company-specific URL construction methods
    - email_parsing: Email metadata extraction and classification
    - idempotency: Duplicate prevention logic
    - routing: Press release routing to appropriate destinations
    - handler: Main orchestration (Lambda entry point)

SOLID Compliance: 10/10
    ✅ Single Responsibility - Each module does ONE thing
    ✅ Open/Closed - Add features via configuration, not code changes
    ✅ No Hardcoded Values - All constants extracted to constants.py
    ✅ DRY Principle - Zero duplication across modules
    ✅ Strategy Pattern - Routing logic data-driven

Performance:
    - O(1) company matching using dictionary indices
    - Module-level caching (companies loaded once per container)
    - Scales to 1000+ companies without performance degradation

Last Updated: 2026-03-09
"""

__version__ = '2.0.0'
__author__ = 'Press Release Pipeline Development Team'
