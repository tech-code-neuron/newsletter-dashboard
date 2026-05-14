"""
Metadata Builder for Enricher Lambda
=====================================
Explicit service-specific metadata construction.

WHY THIS EXISTS:
Different downstream services expect different field names and features:
- Playwright/SQS: Uses 'email_subject' key (for message reconstruction)
- DynamoDB: Uses 'subject' key (legacy field name) + title cleanup
- Scraper Queue: Uses 'subject' key but NO title cleanup (scraper adds its own)

This makes the intentional differences EXPLICIT rather than scattered across 9 locations.

SOLID: Single Responsibility - only builds metadata dicts
"""

from typing import Optional
from title_cleanup import add_display_title_to_metadata


class MetadataBuilder:
    """
    Builds metadata dicts for different downstream services.

    Each method is explicit about what it produces:
    - for_playwright(): Returns dict with 'email_subject' key
    - for_dynamodb(): Returns dict with 'subject' key + title cleanup
    - for_scraper(): Returns dict with 'subject' key, NO title cleanup
    """

    def __init__(
        self,
        ticker: str,
        email_subject: str,
        email_date: str,
        idempotency_key: str,
        company_name: Optional[str] = None,
        press_release_date: Optional[str] = None,
        press_release_title: Optional[str] = None,
        construction_method: Optional[str] = None
    ):
        """
        Initialize with all possible metadata fields.

        Args:
            ticker: Company stock ticker (required)
            email_subject: Original email subject line (required)
            email_date: Email received date (required)
            idempotency_key: Unique key for deduplication (required)
            company_name: Company name for error messages (Playwright only)
            press_release_date: Extracted press release date (optional)
            press_release_title: Extracted press release title (optional)
            construction_method: How URL was constructed (DynamoDB only)
        """
        self.ticker = ticker
        self.email_subject = email_subject
        self.email_date = email_date
        self.idempotency_key = idempotency_key
        self.company_name = company_name
        self.press_release_date = press_release_date
        self.press_release_title = press_release_title
        self.construction_method = construction_method

    def for_playwright(self) -> dict:
        """
        Build metadata for Playwright queue (SQS message).

        Key differences from DynamoDB:
        - Uses 'email_subject' (not 'subject') - Playwright reconstructs from this
        - Includes 'company_name' for better error messages
        - NO title cleanup (Playwright will extract title from page)
        - Optional: press_release_title if available (for fuzzy matching)

        Returns:
            dict: Metadata for Playwright queue message
        """
        metadata = {
            'ticker': self.ticker,
            'company_name': self.company_name or f'Unknown ({self.ticker})',
            'email_subject': self.email_subject,  # NOTE: 'email_subject' not 'subject'
            'email_date': self.email_date,
            'idempotency_key': self.idempotency_key
        }

        # Optional fields
        if self.press_release_date:
            metadata['press_release_date'] = self.press_release_date
        if self.press_release_title:
            metadata['press_release_title'] = self.press_release_title

        return metadata

    def for_dynamodb(self) -> dict:
        """
        Build metadata for DynamoDB save (final storage).

        Key differences from Playwright:
        - Uses 'subject' (not 'email_subject') - legacy field name
        - NO 'company_name' (already in ticker lookup)
        - Includes title cleanup (display_title field)
        - Optional: construction_method for tracking

        Returns:
            dict: Metadata for DynamoDB item
        """
        metadata = {
            'ticker': self.ticker,
            'subject': self.email_subject,  # NOTE: 'subject' not 'email_subject'
            'email_date': self.email_date,
            'idempotency_key': self.idempotency_key
        }

        # Optional fields
        if self.press_release_date:
            metadata['press_release_date'] = self.press_release_date
        if self.construction_method:
            metadata['construction_method'] = self.construction_method

        # Title cleanup (DynamoDB only - Playwright extracts from page)
        add_display_title_to_metadata(metadata, self.ticker)

        return metadata

    def for_scraper(self) -> dict:
        """
        Build metadata for Scraper queue (newswire URLs).

        Key differences:
        - Uses 'subject' (like DynamoDB)
        - NO title cleanup (scraper extracts title from page)
        - NO construction_method (scraper adds its own)

        Returns:
            dict: Metadata for Scraper queue message
        """
        metadata = {
            'ticker': self.ticker,
            'subject': self.email_subject,  # NOTE: 'subject' not 'email_subject'
            'email_date': self.email_date,
            'idempotency_key': self.idempotency_key
        }

        # Optional fields
        if self.press_release_date:
            metadata['press_release_date'] = self.press_release_date

        # NO title cleanup - scraper will extract from page

        return metadata

    def with_construction_method(self, method: str) -> 'MetadataBuilder':
        """
        Return new builder with construction_method set.

        Useful for timeout recovery: method + '_timeout_recovered'

        Args:
            method: Construction method used (e.g., 'gcs_standard')

        Returns:
            MetadataBuilder: New instance with method set
        """
        return MetadataBuilder(
            ticker=self.ticker,
            email_subject=self.email_subject,
            email_date=self.email_date,
            idempotency_key=self.idempotency_key,
            company_name=self.company_name,
            press_release_date=self.press_release_date,
            press_release_title=self.press_release_title,
            construction_method=method
        )
