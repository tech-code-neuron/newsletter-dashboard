"""
Disclosure Service - Business Logic for 8-K SEC Filing Display

Simplified read-only service:
- List disclosures with pagination
- Detail view with related press release

No editing, no duplication filtering.
"""
import logging
from typing import List, Optional, Tuple

from core.repositories import get_disclosure_repo, get_press_release_repo
from core.dto import DisclosureDTO, PressReleaseDTO

logger = logging.getLogger(__name__)


class DisclosureService:
    """
    Service layer for 8-K disclosure operations.

    Simplified to read-only display with related PR linking.
    """

    def __init__(self):
        """Initialize service with repository references."""
        self.disclosure_repo = get_disclosure_repo()
        self.pr_repo = get_press_release_repo()

    def get_disclosures_for_list(
        self,
        days: int = 7,
        page: int = 1,
        per_page: int = 50
    ) -> Tuple[List[DisclosureDTO], int]:
        """
        Get disclosures for list view with pagination.

        Args:
            days: Number of days to look back
            page: Page number (1-indexed)
            per_page: Items per page

        Returns:
            Tuple of (disclosures, total_count)
        """
        disclosures = self.disclosure_repo.get_recent(days=days, limit=500)

        # Deduplicate: FWP takes precedence over 424B5 for same priced deal
        disclosures = self._deduplicate_fwp_424b5(disclosures)

        # Paginate
        total = len(disclosures)
        start = (page - 1) * per_page
        end = start + per_page
        paginated = disclosures[start:end]

        return paginated, total

    def _deduplicate_fwp_424b5(self, disclosures: list) -> list:
        """
        Remove 424B5 filings that duplicate an FWP for the same priced deal.

        FWP (Free Writing Prospectus) is more timely than 424B5, so when both
        exist for the same deal, we show only the FWP.

        Match criteria:
        - Same ticker
        - Both are 'priced' offering_type
        - Same security_type
        - Principal amount within 5%
        - Filed within 14 days
        """
        from datetime import datetime, timedelta

        # Index FWPs by ticker
        fwps = {}
        for d in disclosures:
            if d.form_type == 'FWP' and d.offering_type == 'priced':
                key = d.ticker
                if key not in fwps:
                    fwps[key] = []
                fwps[key].append(d)

        def is_superseded(disclosure) -> bool:
            """Check if this 424B5 is superseded by an FWP."""
            if disclosure.form_type not in ('424B5', '424B2'):
                return False
            if disclosure.offering_type != 'priced':
                return False

            ticker_fwps = fwps.get(disclosure.ticker, [])
            if not ticker_fwps:
                return False

            for fwp in ticker_fwps:
                # Check security type match
                if fwp.security_type != disclosure.security_type:
                    continue

                # Check principal amount match (within 5%)
                if fwp.principal_amount and disclosure.principal_amount:
                    try:
                        ratio = float(disclosure.principal_amount) / float(fwp.principal_amount)
                        if not (0.95 <= ratio <= 1.05):
                            continue
                    except:
                        continue

                # Check date proximity (within 14 days)
                try:
                    fwp_date = datetime.strptime(fwp.filing_date, '%Y-%m-%d')
                    disc_date = datetime.strptime(disclosure.filing_date, '%Y-%m-%d')
                    if abs((disc_date - fwp_date).days) <= 14:
                        return True
                except:
                    continue

            return False

        return [d for d in disclosures if not is_superseded(d)]

    def get_disclosure_detail(
        self,
        filing_url: str
    ) -> Tuple[Optional[DisclosureDTO], Optional[PressReleaseDTO]]:
        """
        Get disclosure detail with matched press release.

        Args:
            filing_url: URL-encoded filing URL (primary key)

        Returns:
            Tuple of (disclosure, matched_press_release or None)
        """
        from urllib.parse import unquote

        # Decode URL
        decoded_url = unquote(filing_url)

        disclosure = self.disclosure_repo.get_by_filing_url(decoded_url)
        if not disclosure:
            return None, None

        # Get matched press release if linked (only for 8-K disclosures, not prospectuses)
        matched_pr = None
        related_url = getattr(disclosure, 'related_pr_url', None)
        if related_url:
            matched_pr = self.pr_repo.get_by_url(related_url)

        return disclosure, matched_pr

    def update_disclosure_title(
        self,
        filing_url: str,
        title: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Update the display title for a disclosure.

        Args:
            filing_url: URL-encoded filing URL (primary key)
            title: New title (empty string to clear)

        Returns:
            Tuple of (success, error_message)
        """
        from urllib.parse import unquote

        decoded_url = unquote(filing_url)

        # Verify disclosure exists
        disclosure = self.disclosure_repo.get_by_filing_url(decoded_url)
        if not disclosure:
            return False, 'Disclosure not found'

        # Update title
        success = self.disclosure_repo.update_title(decoded_url, title)
        if success:
            logger.info(f"Updated title for {disclosure.ticker}: {title[:50]}...")
            return True, None

        return False, 'Failed to update title'
