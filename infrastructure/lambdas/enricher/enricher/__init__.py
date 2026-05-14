"""
Enricher - Modular Package
===========================
Refactored from 777-line monolithic handler to focused modules

SOLID Principles:
- Single Responsibility: Each module does ONE thing
- Strategy Pattern: URL construction methods
- Open/Closed: Add URL methods without modifying existing code

Modules:
- url_construction.py: URL construction strategies (GCS, Brixmor, Terreno)
- url_validation.py: URL validation (HTTP HEAD)
- url_selection.py: Select best URL from email via domain matching
- url_classification.py: Classify URLs as newswire/direct
- database_ops.py: Database operations (save, deduplication)
- queue_ops.py: Queue operations (send to scraper)
- company_lookup.py: Company config retrieval
- enrichment_processor.py: Enrichment workflow orchestration

Last Created: 2026-03-11
"""

__version__ = "2.0.0"
__author__ = "Press Release Pipeline"
