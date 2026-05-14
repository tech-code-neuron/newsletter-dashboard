"""
Title Extractors for Special Email Formats
==========================================

Extracts press release titles from email HTML body when the email subject
is generic (e.g., "Company Name Alerting Service").

SOLID: Single Responsibility - Each extractor handles one email format.
DRY: Consolidates title extraction logic in one place.

Author: Claude Code
Date: 2026-04-08
"""

import re
import logging
from typing import Optional

logger = logging.getLogger()


class RealtyIncomeTitleExtractor:
    """
    Extract press release title from Realty Income email HTML.

    SOLID: Single Responsibility - Only handles Realty Income title extraction.

    Pattern: Text between date (MMM DD, YYYY) and tracking URL
    Example: "134TH COMMON STOCK MONTHLY DIVIDEND INCREASE DECLARED BY REALTY INCOME"
    """

    DATE_PATTERN = re.compile(
        r'<p[^>]*>\s*([A-Z][a-z]{2,8})\s+(\d{1,2}),\s+(\d{4})\s*</p>',
        re.IGNORECASE
    )
    TITLE_PATTERN = re.compile(
        r'<p[^>]*>\s*([A-Z0-9][^<]{20,200})\s*</p>',
        re.IGNORECASE
    )

    @classmethod
    def extract(cls, html_body: str) -> Optional[str]:
        """
        Extract title from Realty Income email HTML.

        Args:
            html_body: Email HTML body

        Returns:
            str: Extracted title or None
        """
        if not html_body:
            return None

        try:
            date_match = cls.DATE_PATTERN.search(html_body)
            if not date_match:
                logger.debug("Realty Income: Date pattern not found")
                return None

            remaining_html = html_body[date_match.end():]
            title_match = cls.TITLE_PATTERN.search(remaining_html)

            if title_match:
                title = title_match.group(1).strip()
                logger.info(f"Realty Income: Extracted title: {title[:60]}...")
                return title

            logger.debug("Realty Income: Title pattern not found after date")
            return None

        except Exception as e:
            logger.warning(f"Error extracting Realty Income title: {e}")
            return None

    @classmethod
    def extract_if_realty_income(cls, ticker: str, html_body: str) -> Optional[str]:
        """
        Extract title only if company is Realty Income (O ticker).

        SOLID: Encapsulates the ticker check + extraction in one place.

        Args:
            ticker: Company ticker symbol
            html_body: Email HTML body

        Returns:
            str: Extracted title or None
        """
        if ticker != 'O':  # Realty Income ticker
            return None

        logger.info("Realty Income detected - extracting title from email body")
        title = cls.extract(html_body)

        if title:
            logger.info(f"✓ Extracted title for Realty Income: {title[:80]}...")
        else:
            logger.warning("⚠️  Failed to extract title for Realty Income")

        return title


class AlertingServiceTitleExtractor:
    """
    Extract press release title from alerting service email HTML.

    Detection: Multiple signals (subject/sender contain "alerting",
    sender domain is investis.com). Future-proof for new companies.

    Extraction: Styled <p> tag with large font-size (20-30px).

    SOLID: Single Responsibility - Only handles alerting service title extraction.
    """

    # Match <p> with large font-size in inline style
    TITLE_PATTERN = re.compile(
        r'<p[^>]*style="[^"]*font-size:\s*2[0-9]px[^"]*"[^>]*>\s*([^<]{15,300})\s*</p>',
        re.IGNORECASE | re.DOTALL
    )

    @classmethod
    def _is_alerting_service_email(cls, email_subject: str, sender_name: str = '', sender_domain: str = '') -> bool:
        """Detect alerting service emails using multiple signals."""
        signals = [
            'alerting service' in (email_subject or '').lower(),
            'email alerting' in (email_subject or '').lower(),
            'alerting' in (sender_name or '').lower(),
            (sender_domain or '').lower() == 'investis.com',
        ]
        return any(signals)

    @classmethod
    def extract(cls, html_body: str) -> Optional[str]:
        """Extract title from alerting service email HTML."""
        if not html_body:
            return None
        match = cls.TITLE_PATTERN.search(html_body)
        if match:
            title = re.sub(r'\s+', ' ', match.group(1).strip())
            if 15 <= len(title) <= 300:
                return title
        return None

    @classmethod
    def extract_if_alerting_service(
        cls,
        email_subject: str,
        html_body: str,
        sender_name: str = '',
        sender_domain: str = ''
    ) -> Optional[str]:
        """Extract title if this is an alerting service email."""
        if not cls._is_alerting_service_email(email_subject, sender_name, sender_domain):
            return None

        logger.info("Alerting service email detected - extracting title from HTML body")
        title = cls.extract(html_body)

        if title:
            logger.info(f"✓ Extracted alerting service title: {title[:80]}...")
        else:
            logger.warning("⚠️ Failed to extract title from alerting service email HTML")

        return title
