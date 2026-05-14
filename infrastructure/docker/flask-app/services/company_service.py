"""
Company Service - Business Logic Layer

SOLID Principles:
- Single Responsibility: Handles company search/filter/sort logic
- Dependency Inversion: Depends on repository abstractions
- Open/Closed: Extendable without modifying routes

Responsibilities:
- Company search and filtering
- Sorting logic
- Staleness calculations
- Release statistics
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any

from core.repositories import get_company_repo, get_press_release_repo
from config.query_limits import MAX_COMPANIES_DISPLAY, COMPANY_DETAIL_RELEASES_LIMIT
from utils.text_utils import normalize_text

logger = logging.getLogger(__name__)

# Constants
HISTORICAL_WINDOW_DAYS = 90


class CompanyService:
    """
    Service layer for company operations.

    Handles:
    - Company search, filtering, and sorting
    - Staleness calculations
    - Release statistics
    """

    def __init__(self):
        """Initialize service with repository references."""
        self.company_repo = get_company_repo()
        self.pr_repo = get_press_release_repo()

    # =========================================================================
    # List & Search Operations
    # =========================================================================

    def get_companies_for_display(
        self,
        search: Optional[str] = None,
        sort_by: str = 'ticker',
        order: str = 'asc'
    ) -> Dict[str, Any]:
        """
        Get companies with search, filter, and sort for display page.

        Args:
            search: Search query
            sort_by: Sort field (ticker, name)
            order: Sort order (asc, desc)

        Returns:
            dict: Active companies, inactive companies, sectors
        """
        # Get companies with release stats
        results = self.company_repo.get_with_release_stats()

        # Filter by search (accent-insensitive: "Ivanhoe" matches "Ivanhoé")
        if search:
            search_normalized = normalize_text(search)
            results = [
                r for r in results
                if search_normalized in normalize_text(r['company'].ticker) or
                   search_normalized in normalize_text(r['company'].name or '')
            ]

        # Sort
        results = self._sort_companies(results, sort_by, order)

        # Limit results
        results = results[:MAX_COMPANIES_DISPLAY]

        # Calculate staleness and separate by active status
        active_companies, inactive_companies = self._calculate_staleness(results)

        # Extract unique sectors
        sectors = self._extract_sectors([r['company'] for r in results])

        return {
            'active_companies': active_companies,
            'inactive_companies': inactive_companies,
            'sectors': sectors,
            'search': search or '',
            'sort_by': sort_by,
            'order': order
        }

    # =========================================================================
    # Company Detail
    # =========================================================================

    def get_company_with_releases(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Get company with recent press releases for detail page.

        Args:
            ticker: Company ticker

        Returns:
            dict: Company and recent releases, or None if not found
        """
        company = self.company_repo.get_by_ticker(ticker)
        if not company:
            return None

        # Get recent releases for this company using GSI (efficient O(1) query)
        # NOTE: get_recent() with tickers filter uses table scan with pre-filter Limit,
        # which misses items when table has >50 entries. get_by_company() uses GSI.
        releases = self.pr_repo.get_by_company(
            ticker=ticker,
            limit=COMPANY_DETAIL_RELEASES_LIMIT,
            include_deleted=False
        )

        return {
            'company': company,
            'releases': releases
        }

    # =========================================================================
    # CRUD Operations
    # =========================================================================

    def update_company(
        self,
        ticker: str,
        data: Dict[str, Any],
        new_ticker: Optional[str] = None
    ) -> bool:
        """
        Update company information.

        Args:
            ticker: Current company ticker
            data: Dictionary of company fields to update
            new_ticker: New ticker if being renamed

        Returns:
            bool: Success status
        """
        try:
            company = self.company_repo.get_by_ticker(ticker)
            if not company:
                logger.error(f"Company not found: {ticker}")
                return False

            # Map 'name' to 'company_name' for DynamoDB (form uses 'name')
            if 'name' in data:
                data['company_name'] = data.pop('name')

            # Handle ticker change (requires delete + create since ticker is PK)
            if new_ticker and new_ticker.upper() != ticker.upper():
                # Check if new ticker already exists
                existing = self.company_repo.get_by_ticker(new_ticker)
                if existing:
                    logger.error(f"Cannot rename: ticker {new_ticker} already exists")
                    return False

                # Create new record with new ticker (preserve all existing fields)
                new_data = {**data, 'ticker': new_ticker.upper(), 'active': company.active}
                self.company_repo.create(new_data)

                # Delete old record
                self.company_repo.delete(ticker)

                # Invalidate company cache for both old and new tickers
                pr_repo = get_press_release_repo()
                pr_repo.clear_company_cache(ticker)
                pr_repo.clear_company_cache(new_ticker.upper())

                logger.info(f"Renamed company: {ticker} -> {new_ticker}")
                return True

            # Normal update (no ticker change) - use repository signature
            success = self.company_repo.update(ticker, data)
            if not success:
                logger.error(f"Repository failed to update company: {ticker}")
                return False

            # Invalidate company cache so publisher reflects changes immediately
            pr_repo = get_press_release_repo()
            pr_repo.clear_company_cache(ticker)

            logger.info(f"Updated company: {ticker}")
            return True

        except Exception as e:
            logger.error(f"Error updating company {ticker}: {e}", exc_info=True)
            return False

    def add_company(self, data: Dict[str, Any]) -> bool:
        """
        Add a new company.

        Args:
            data: Dictionary of company fields from form

        Returns:
            bool: Success status
        """
        try:
            ticker = data.get('ticker', '').upper()
            if not ticker:
                logger.error("Cannot add company: missing ticker")
                return False

            # Check for duplicate
            existing = self.company_repo.get_by_ticker(ticker)
            if existing:
                logger.error(f"Company already exists: {ticker}")
                return False

            # Ensure required fields and defaults
            # Map 'name' to 'company_name' for DynamoDB (form uses 'name')
            company_data = {
                **data,
                'ticker': ticker,
                'company_name': data.get('name') or data.get('company_name', ''),
                'active': data.get('active', True),
                'is_public': data.get('is_public', True),
                'url_construction_method': data.get('url_construction_method', 'direct_url')
            }
            # Remove 'name' key if present (DynamoDB uses company_name)
            company_data.pop('name', None)
            self.company_repo.create(company_data)

            # Invalidate company cache in case this ticker was previously used
            pr_repo = get_press_release_repo()
            pr_repo.clear_company_cache(ticker)

            logger.info(f"Added company: {ticker} - {company_data.get('company_name')}")
            return True

        except Exception as e:
            logger.error(f"Error adding company: {e}")
            return False

    def delete_company(self, ticker: str) -> bool:
        """
        Delete a company permanently.

        Args:
            ticker: Company ticker

        Returns:
            bool: Success status
        """
        try:
            company = self.company_repo.get_by_ticker(ticker)
            if not company:
                logger.error(f"Cannot delete: company not found: {ticker}")
                return False

            success = self.company_repo.delete(ticker)
            if success:
                # Invalidate company cache so deleted company doesn't appear
                pr_repo = get_press_release_repo()
                pr_repo.clear_company_cache(ticker)
                logger.info(f"Deleted company: {ticker}")
            return success

        except Exception as e:
            logger.error(f"Error deleting company {ticker}: {e}")
            return False

    def toggle_emails_activated(self, ticker: str) -> Optional[bool]:
        """
        Toggle email notifications for a company.

        Args:
            ticker: Company ticker

        Returns:
            bool: New emails_activated state, or None on error
        """
        try:
            company = self.company_repo.get_by_ticker(ticker)
            if not company:
                return None

            # Toggle
            new_value = not company.emails_activated
            # Use DynamoDB-compatible update signature: (ticker, data_dict)
            self.company_repo.update(ticker, {'emails_activated': new_value})

            # Invalidate company cache
            pr_repo = get_press_release_repo()
            pr_repo.clear_company_cache(ticker)

            logger.info(f"Toggled emails for {ticker}: {company.emails_activated}")
            return company.emails_activated

        except Exception as e:
            logger.error(f"Error toggling emails for {ticker}: {e}")
            return None

    def toggle_ignore_rss(self, ticker: str) -> Optional[bool]:
        """
        Toggle ignore RSS flag for a company.

        Args:
            ticker: Company ticker

        Returns:
            bool: New ignore_company_rss state, or None on error
        """
        try:
            company = self.company_repo.get_by_ticker(ticker)
            if not company:
                return None

            # Toggle
            new_value = not company.ignore_company_rss
            # Use DynamoDB-compatible update signature: (ticker, data_dict)
            self.company_repo.update(ticker, {'ignore_company_rss': new_value})

            # Invalidate company cache
            pr_repo = get_press_release_repo()
            pr_repo.clear_company_cache(ticker)

            logger.info(f"Toggled ignore RSS for {ticker}: {company.ignore_company_rss}")
            return company.ignore_company_rss

        except Exception as e:
            logger.error(f"Error toggling ignore RSS for {ticker}: {e}")
            return None

    def toggle_active(self, ticker: str) -> Optional[bool]:
        """
        Toggle active status for a company.

        Args:
            ticker: Company ticker

        Returns:
            bool: New active state, or None on error
        """
        try:
            company = self.company_repo.get_by_ticker(ticker)
            if not company:
                return None

            new_value = not company.active
            self.company_repo.update(ticker, {'active': new_value})

            # Invalidate company cache
            pr_repo = get_press_release_repo()
            pr_repo.clear_company_cache(ticker)

            logger.info(f"Toggled active for {ticker}: {new_value}")
            return new_value

        except Exception as e:
            logger.error(f"Error toggling active for {ticker}: {e}")
            return None

    # =========================================================================
    # Helper Methods (Private)
    # =========================================================================

    def _sort_companies(self, results: List[Dict], sort_by: str, order: str) -> List[Dict]:
        """
        Sort companies by specified field and order.

        Args:
            results: List of company result dicts
            sort_by: Sort field (ticker, name)
            order: Sort order (asc/desc)

        Returns:
            Sorted results
        """
        def get_sort_key(item):
            company = item['company']
            if sort_by == 'name':
                return company.name or ''
            return company.ticker

        results.sort(key=get_sort_key, reverse=(order == 'desc'))
        return results

    def _calculate_staleness(self, results: List[Dict]) -> tuple:
        """
        Calculate staleness for companies and separate by active status.

        Args:
            results: List of company result dicts

        Returns:
            Tuple of (active_companies, inactive_companies)
        """
        ninety_days_ago = datetime.now() - timedelta(days=HISTORICAL_WINDOW_DAYS)
        active_companies = []
        inactive_companies = []

        for item in results:
            company = item['company']
            latest_date = item['latest_date']
            release_count = item['release_count']

            # Add computed fields
            company.has_releases = release_count > 0 if release_count else False

            # Handle latest_date comparison
            if latest_date:
                if isinstance(latest_date, str):
                    try:
                        latest_date = datetime.fromisoformat(latest_date.replace('Z', '+00:00'))
                    except (ValueError, AttributeError):
                        latest_date = None

            company.is_stale = bool(latest_date and latest_date < ninety_days_ago)
            company.latest_release_date = latest_date
            company.release_count = release_count or 0

            # Separate by active status
            if company.active:
                active_companies.append(company)
            else:
                inactive_companies.append(company)

        return active_companies, inactive_companies

    def _extract_sectors(self, companies: List) -> List[str]:
        """
        Extract unique sectors from company list.

        Args:
            companies: List of company objects

        Returns:
            Sorted list of unique sectors
        """
        sectors = set()
        for c in companies:
            if c.sector:
                sectors.add(c.sector)
        return sorted(list(sectors))


# =============================================================================
# Service Factory (Singleton Pattern)
# =============================================================================

_service_instance = None

def get_company_service() -> CompanyService:
    """
    Get or create company service instance (singleton).

    Returns:
        CompanyService: Service instance
    """
    global _service_instance
    if _service_instance is None:
        _service_instance = CompanyService()
    return _service_instance
