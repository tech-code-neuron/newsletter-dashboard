"""
Query builder utilities for complex database queries.
Separates query logic from route handlers (Single Responsibility).
"""
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from core.models import PressRelease, Company


# ------------------------------------------------------------------
# CONSTANTS - Query Configuration
# ------------------------------------------------------------------

DEFAULT_REVIEW_PAGE_SIZE = 50
DEFAULT_RELEVANCE_FILTER = 'uncategorized'
DEFAULT_SORT_BY = 'published_date'
DEFAULT_SORT_ORDER = 'desc'

# Sort configuration (Open/Closed: add new sort options here)
SORT_CONFIGURATION = {
    'title': {
        'column': lambda: PressRelease.title,
        'requires_join': False
    },
    'published_date': {
        'column': lambda: PressRelease.published_date,
        'requires_join': False
    },
    'relevance': {
        'column': lambda: PressRelease.relevance,
        'requires_join': False
    },
    'ticker': {
        'column': lambda: Company.ticker,
        'requires_join': True
    }
}


# ------------------------------------------------------------------
# QUERY BUILDERS - Single Responsibility Pattern
# ------------------------------------------------------------------

def build_review_query(db, relevance_filter=None, company_filter=None, sort_by=None, sort_order=None):
    """
    Build review page query with filters and sorting.

    Args:
        db: Database session
        relevance_filter: 'all', 'uncategorized', 'relevant', 'not_relevant'
        company_filter: List of ticker symbols to filter by
        sort_by: 'ticker', 'title', 'published_date', 'relevance'
        sort_order: 'asc' or 'desc'

    Returns:
        SQLAlchemy query object (not executed)
    """
    # Base query - exclude deleted, eagerly load company
    query = db.query(PressRelease).options(
        joinedload(PressRelease.company)
    ).filter(PressRelease.deleted_at.is_(None))

    # Apply relevance filter
    query = _apply_relevance_filter(query, relevance_filter)

    # Apply company filter
    if company_filter:
        query = query.join(Company).filter(Company.ticker.in_(company_filter))

    # Apply sorting
    query = _apply_review_sorting(query, sort_by, sort_order, company_filter)

    return query


def get_review_counts(db):
    """
    Get press release counts for review page filter tabs.

    Args:
        db: Database session

    Returns:
        dict: {
            'all': total count,
            'uncategorized': uncategorized count,
            'relevant': relevant count,
            'not_relevant': not_relevant count
        }
    """
    base_filter = PressRelease.deleted_at.is_(None)

    return {
        'all': db.query(PressRelease).filter(base_filter).count(),
        'uncategorized': db.query(PressRelease).filter(
            base_filter,
            PressRelease.relevance.is_(None)
        ).count(),
        'relevant': db.query(PressRelease).filter(
            base_filter,
            PressRelease.relevance == 'relevant'
        ).count(),
        'not_relevant': db.query(PressRelease).filter(
            base_filter,
            PressRelease.relevance == 'not_relevant'
        ).count()
    }


def build_pagination_info(page, per_page, total_count, items):
    """
    Build pagination metadata object.

    Args:
        page: Current page number (1-indexed)
        per_page: Items per page
        total_count: Total number of items
        items: List of items for current page

    Returns:
        dict: Pagination metadata compatible with template
    """
    total_pages = (total_count + per_page - 1) // per_page
    has_prev = page > 1
    has_next = page < total_pages

    return {
        'page': page,
        'per_page': per_page,
        'total': total_count,
        'pages': total_pages,
        'has_prev': has_prev,
        'has_next': has_next,
        'prev_num': page - 1 if has_prev else None,
        'next_num': page + 1 if has_next else None,
        'items': items
    }


# ------------------------------------------------------------------
# PRIVATE HELPERS - Implementation Details
# ------------------------------------------------------------------

def _apply_relevance_filter(query, relevance_filter):
    """Apply relevance filter to query."""
    if not relevance_filter or relevance_filter == 'all':
        return query

    filter_map = {
        'uncategorized': PressRelease.relevance.is_(None),
        'relevant': PressRelease.relevance == 'relevant',
        'not_relevant': PressRelease.relevance == 'not_relevant'
    }

    filter_condition = filter_map.get(relevance_filter)
    if filter_condition is not None:
        query = query.filter(filter_condition)

    return query


def _apply_review_sorting(query, sort_by, sort_order, company_filter):
    """
    Apply sorting to review query.
    Fully data-driven sort configuration (Open/Closed principle).

    To add new sort option:
    1. Add entry to SORT_CONFIGURATION dict
    2. No code changes needed here
    """
    # Get sort configuration (default to published_date)
    sort_config = SORT_CONFIGURATION.get(sort_by, SORT_CONFIGURATION['published_date'])

    # Join Company table if needed and not already joined
    if sort_config['requires_join'] and not company_filter:
        query = query.join(Company)

    # Get sort column and apply direction
    sort_column = sort_config['column']()
    is_desc = sort_order == 'desc'

    return query.order_by(
        sort_column.desc() if is_desc else sort_column.asc()
    )
