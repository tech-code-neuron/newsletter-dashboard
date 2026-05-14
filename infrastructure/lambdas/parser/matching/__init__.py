"""
Parser Company Matching - Modular Package
==========================================
Refactored from 627-line monolithic file to focused modules

SOLID Principles:
- Single Responsibility: Each module does ONE thing
- Facade Pattern: company_matching.py re-exports for backward compatibility
- O(1) Lookups: Domain/name matching via indices or DynamoDB GSI

Modules:
- name_normalization.py: Normalize company names for fuzzy matching
- domain_extraction.py: Extract domains from company records
- index_builder.py: Build in-memory indices for O(1) lookup
- memory_matcher.py: In-memory company matching (legacy)
- gsi_matcher.py: GSI-based company matching (new, O(1) DynamoDB queries)
- hybrid_matcher.py: Selects between in-memory vs GSI matching

Last Created: 2026-03-11
"""

__version__ = "2.0.0"
__author__ = "Press Release Pipeline"
