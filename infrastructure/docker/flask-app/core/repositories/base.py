"""
Abstract Base Classes for Repositories

Defines the interface that all repository implementations must follow.
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from datetime import datetime


class CompanyRepository(ABC):
    """Abstract base class for company data access"""

    @abstractmethod
    def get_all(self, limit: int = 500) -> List['CompanyDTO']:
        """Get all companies"""
        pass

    @abstractmethod
    def get_all_active(self, limit: int = 500) -> List['CompanyDTO']:
        """Get all active companies"""
        pass

    @abstractmethod
    def get_by_ticker(self, ticker: str) -> Optional['CompanyDTO']:
        """Get company by ticker"""
        pass

    @abstractmethod
    def get_by_id(self, company_id: int) -> Optional['CompanyDTO']:
        """Get company by ID (for SQLite compatibility)"""
        pass

    @abstractmethod
    def search(self, query: str, limit: int = 100) -> List['CompanyDTO']:
        """Search companies by ticker or name"""
        pass

    @abstractmethod
    def update(self, ticker: str, data: Dict[str, Any]) -> bool:
        """Update company data"""
        pass

    @abstractmethod
    def create(self, data: Dict[str, Any]) -> 'CompanyDTO':
        """Create new company"""
        pass

    @abstractmethod
    def get_with_release_stats(self) -> List[Dict[str, Any]]:
        """Get companies with latest release date and count"""
        pass


class PressReleaseRepository(ABC):
    """Abstract base class for press release data access"""

    @abstractmethod
    def get_by_id(self, release_id: int) -> Optional['PressReleaseDTO']:
        """Get press release by ID"""
        pass

    @abstractmethod
    def get_by_url(self, url: str) -> Optional['PressReleaseDTO']:
        """Get press release by URL"""
        pass

    @abstractmethod
    def get_by_unique_id(self, unique_id: str) -> Optional['PressReleaseDTO']:
        """Get press release by unique_id"""
        pass

    @abstractmethod
    def get_recent(
        self,
        limit: int = 50,
        days: Optional[int] = None,
        category: Optional[str] = None,
        tickers: Optional[List[str]] = None,
        include_deleted: bool = False
    ) -> List['PressReleaseDTO']:
        """Get recent press releases with filtering"""
        pass

    @abstractmethod
    def get_archived(self, limit: int = 100) -> List['PressReleaseDTO']:
        """Get archived (soft-deleted) press releases"""
        pass

    @abstractmethod
    def get_by_company(
        self,
        ticker: str,
        limit: int = 50,
        include_deleted: bool = False
    ) -> List['PressReleaseDTO']:
        """Get press releases for a company"""
        pass

    @abstractmethod
    def get_uncategorized_count(self) -> int:
        """Get count of uncategorized press releases"""
        pass

    @abstractmethod
    def get_total_count(self, include_deleted: bool = False) -> int:
        """Get total press release count"""
        pass

    @abstractmethod
    def update(self, url: str, data: Dict[str, Any]) -> bool:
        """Update press release data"""
        pass

    @abstractmethod
    def create(self, data: Dict[str, Any]) -> 'PressReleaseDTO':
        """Create new press release"""
        pass

    @abstractmethod
    def soft_delete(self, url: str) -> bool:
        """Soft delete (archive) a press release"""
        pass

    @abstractmethod
    def restore(self, url: str) -> bool:
        """Restore a soft-deleted press release"""
        pass

    @abstractmethod
    def hard_delete(self, url: str) -> bool:
        """Permanently delete a press release"""
        pass

    @abstractmethod
    def get_for_review(
        self,
        relevance_filter: str = 'all',
        company_filter: Optional[List[str]] = None,
        sort_by: str = 'date',
        sort_order: str = 'desc',
        offset: int = 0,
        limit: int = 50
    ) -> tuple:
        """Get press releases for review page with counts"""
        pass

    @abstractmethod
    def get_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        limit: int = 200,
        include_deleted: bool = False
    ) -> List['PressReleaseDTO']:
        """Get press releases within a date range"""
        pass


class NewsletterRepository(ABC):
    """Abstract base class for newsletter data access"""

    @abstractmethod
    def get_by_id(self, newsletter_id: int) -> Optional['NewsletterDTO']:
        """Get newsletter by ID"""
        pass

    @abstractmethod
    def get_recent(self, limit: int = 50) -> List['NewsletterDTO']:
        """Get recent newsletters"""
        pass

    @abstractmethod
    def update(self, newsletter_id: int, data: Dict[str, Any]) -> bool:
        """Update newsletter data"""
        pass

    @abstractmethod
    def create(self, data: Dict[str, Any]) -> 'NewsletterDTO':
        """Create new newsletter"""
        pass


class ReviewEmailRepository(ABC):
    """Abstract base class for review email data access"""

    @abstractmethod
    def get_by_id(self, review_id: int) -> Optional['ReviewEmailDTO']:
        """Get review email by ID"""
        pass

    @abstractmethod
    def get_by_gmail_id(self, gmail_message_id: str) -> Optional['ReviewEmailDTO']:
        """Get review email by Gmail message ID"""
        pass

    @abstractmethod
    def get_pending(self) -> List['ReviewEmailDTO']:
        """Get all pending review emails"""
        pass

    @abstractmethod
    def update_status(self, review_id: int, status: str, **kwargs) -> bool:
        """Update review email status"""
        pass

    @abstractmethod
    def create(self, data: Dict[str, Any]) -> 'ReviewEmailDTO':
        """Create new review email"""
        pass


class RelevanceRepository(ABC):
    """Abstract base class for relevance decision data access"""

    @abstractmethod
    def create(self, data: Dict[str, Any]) -> 'RelevanceDecisionDTO':
        """Create new relevance decision"""
        pass

    @abstractmethod
    def get_by_press_release(self, press_release_id: int) -> List['RelevanceDecisionDTO']:
        """Get relevance decisions for a press release"""
        pass


class DisclosureRepository(ABC):
    """Abstract base class for 8-K disclosure data access (simplified)"""

    @abstractmethod
    def get_by_filing_url(self, filing_url: str) -> Optional['DisclosureDTO']:
        """Get disclosure by filing URL (primary key)"""
        pass

    @abstractmethod
    def get_recent(self, days: int = 7, limit: int = 500) -> List['DisclosureDTO']:
        """Get recent disclosures sorted by date"""
        pass

    @abstractmethod
    def update_title(self, filing_url: str, title: str) -> bool:
        """Update the AI summary title for a disclosure"""
        pass

    @abstractmethod
    def get_by_date_range(
        self,
        start_dt: 'datetime',
        end_dt: 'datetime',
        limit: int = 500
    ) -> List['DisclosureDTO']:
        """
        Get disclosures within a datetime range.

        Args:
            start_dt: Start datetime (timezone-aware)
            end_dt: End datetime (timezone-aware)
            limit: Maximum items to return

        Returns:
            List of disclosures sorted by first_seen_at descending
        """
        pass

    @abstractmethod
    def update(self, filing_url: str, updates: Dict[str, Any]) -> bool:
        """
        Update disclosure fields.

        Args:
            filing_url: Primary key
            updates: Dict of field names to values

        Returns:
            True if successful
        """
        pass
