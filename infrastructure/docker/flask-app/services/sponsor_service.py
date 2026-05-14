"""
Sponsor Service - Business Logic Layer

Handles sponsor-related operations including:
- Listing sponsors with usage statistics
- Finding non-canonical sponsors in database
- Previewing migration changes

SOLID Principles:
- Single Responsibility: Only sponsor-related business logic
- Dependency Inversion: Depends on repository abstractions
"""
import logging
from typing import List, Dict, Optional
from collections import defaultdict

from config.sponsors import (
    SPONSORS,
    SPONSOR_ALIASES,
    SPECIAL_SPONSORS,
    get_canonical_sponsor,
    is_canonical_sponsor
)
from core.repositories import get_press_release_repo

logger = logging.getLogger(__name__)


class SponsorService:
    """
    Service layer for sponsor operations.

    Handles:
    - Sponsor listing with company counts
    - Non-canonical sponsor detection
    - Migration preview
    """

    def __init__(self):
        """Initialize service with repository reference."""
        from core.repositories import get_company_repo
        self.company_repo = get_company_repo()

    # =========================================================================
    # List Operations
    # =========================================================================

    def get_all_canonical_sponsors(self) -> List[str]:
        """
        Get all canonical sponsors.

        Returns:
            Sorted list of canonical sponsor names
        """
        return sorted(SPONSORS)

    def get_all_sponsors_for_autocomplete(self) -> List[str]:
        """
        Get all sponsors for form autocomplete (canonical + DB-discovered).

        Returns:
            Sorted list of all sponsor names (config + unique DB values)
        """
        # Start with canonical sponsors
        all_sponsors = set(SPONSORS)

        # Add DB-discovered sponsors
        non_canonical = self.find_non_canonical_sponsors()
        for item in non_canonical:
            if item['current_value'] == item['suggested_canonical']:
                # Truly new sponsor (not a typo)
                all_sponsors.add(item['current_value'])

        return sorted(all_sponsors)

    def get_sponsor_usage(self) -> Dict[str, List[str]]:
        """
        Get sponsor usage statistics.

        Returns:
            Dict mapping canonical sponsor name to list of company tickers
        """
        companies = self.company_repo.get_all()
        usage = defaultdict(list)

        for company in companies:
            for field in ['lead_sponsor', 'second_sponsor']:
                sponsor = getattr(company, field, None)
                if sponsor:
                    canonical = get_canonical_sponsor(sponsor)
                    if company.ticker not in usage[canonical]:
                        usage[canonical].append(company.ticker)

        return dict(usage)

    def get_sponsors_for_display(self) -> Dict:
        """
        Get sponsor data formatted for admin display.

        Returns:
            Dict with sponsors, usage counts, non-canonical list
        """
        usage = self.get_sponsor_usage()
        non_canonical = self.find_non_canonical_sponsors()

        # Build display list from canonical sponsors
        sponsor_list = []
        for sponsor in sorted(SPONSORS):
            tickers = usage.get(sponsor, [])
            sponsor_list.append({
                'name': sponsor,
                'count': len(tickers),
                'companies': sorted(tickers),
                'is_special': sponsor in SPECIAL_SPONSORS,
                'is_db_sourced': False
            })

        # Add DB-discovered sponsors (new sponsors not in config)
        for item in non_canonical:
            if item['current_value'] == item['suggested_canonical']:
                # This is a truly new sponsor (not a typo/alias)
                sponsor_list.append({
                    'name': item['current_value'],
                    'count': len(item['tickers']),
                    'companies': sorted(item['tickers']),
                    'is_special': False,
                    'is_db_sourced': True
                })

        # Sort by count descending, then name
        sponsor_list.sort(key=lambda x: (-x['count'], x['name']))

        # Filter non_canonical to only show typos/variations (not new sponsors)
        typos_only = [n for n in non_canonical if n['current_value'] != n['suggested_canonical']]

        return {
            'sponsors': sponsor_list,
            'total_sponsors': len(SPONSORS),
            'used_sponsors': len([s for s in sponsor_list if s['count'] > 0]),
            'non_canonical': typos_only,
            'non_canonical_count': len(typos_only)
        }

    # =========================================================================
    # Non-Canonical Detection
    # =========================================================================

    def find_non_canonical_sponsors(self) -> List[Dict]:
        """
        Find sponsors in database that aren't canonical.

        Returns:
            List of dicts with current_value, suggested_canonical, tickers
        """
        companies = self.company_repo.get_all()
        non_canonical = {}

        for company in companies:
            for field in ['lead_sponsor', 'second_sponsor']:
                sponsor = getattr(company, field, None)
                if sponsor and not is_canonical_sponsor(sponsor):
                    canonical = get_canonical_sponsor(sponsor)
                    key = sponsor

                    if key not in non_canonical:
                        non_canonical[key] = {
                            'current_value': sponsor,
                            'suggested_canonical': canonical,
                            'tickers': []
                        }
                    if company.ticker not in non_canonical[key]['tickers']:
                        non_canonical[key]['tickers'].append(company.ticker)

        # Convert to sorted list
        result = list(non_canonical.values())
        result.sort(key=lambda x: x['current_value'])
        return result

    # =========================================================================
    # Migration Preview
    # =========================================================================

    def preview_migration(self) -> List[Dict]:
        """
        Preview what the migration would change.

        Returns:
            List of dicts with ticker, field, old_value, new_value
        """
        companies = self.company_repo.get_all()
        changes = []

        for company in companies:
            for field in ['lead_sponsor', 'second_sponsor']:
                old_value = getattr(company, field, None)
                if old_value:
                    new_value = get_canonical_sponsor(old_value)
                    if new_value != old_value:
                        changes.append({
                            'ticker': company.ticker,
                            'company_name': company.name,
                            'field': 'Lead Sponsor' if field == 'lead_sponsor' else 'Second Sponsor',
                            'old_value': old_value,
                            'new_value': new_value
                        })

        # Sort by ticker
        changes.sort(key=lambda x: x['ticker'])
        return changes

    # =========================================================================
    # Autocomplete Support
    # =========================================================================

    def search_sponsors(self, query: str, limit: int = 10) -> List[str]:
        """
        Search sponsors by prefix for autocomplete.

        Args:
            query: Search prefix
            limit: Maximum results to return

        Returns:
            List of matching canonical sponsor names
        """
        if not query:
            return []

        query_lower = query.lower()
        matches = []

        for sponsor in SPONSORS:
            if sponsor.lower().startswith(query_lower):
                matches.append(sponsor)
            elif query_lower in sponsor.lower():
                matches.append(sponsor)

        return sorted(set(matches))[:limit]

    def rename_sponsor(self, old_name: str, new_name: str) -> Dict:
        """
        Rename a sponsor across all companies.

        Args:
            old_name: Current sponsor name
            new_name: New sponsor name

        Returns:
            Dict with old_name, new_name, and list of updated tickers
        """
        companies = self.company_repo.get_all()
        updated = []

        for company in companies:
            changed = False
            updates = {}

            if getattr(company, 'lead_sponsor', None) == old_name:
                updates['lead_sponsor'] = new_name
                changed = True
            if getattr(company, 'second_sponsor', None) == old_name:
                updates['second_sponsor'] = new_name
                changed = True

            if changed:
                self.company_repo.update(company.ticker, updates)
                updated.append(company.ticker)

        # Invalidate company cache for all updated tickers
        if updated:
            pr_repo = get_press_release_repo()
            for ticker in updated:
                pr_repo.clear_company_cache(ticker)

        logger.info(f"Renamed sponsor '{old_name}' to '{new_name}', updated {len(updated)} companies")
        return {'old_name': old_name, 'new_name': new_name, 'updated_tickers': updated}


# =============================================================================
# Service Factory (Singleton Pattern)
# =============================================================================

_service_instance = None


def get_sponsor_service() -> SponsorService:
    """
    Get or create sponsor service instance (singleton).

    Returns:
        SponsorService: Service instance
    """
    global _service_instance
    if _service_instance is None:
        _service_instance = SponsorService()
    return _service_instance
