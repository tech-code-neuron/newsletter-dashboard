"""
SQS Message Schemas - Single Source of Truth
=============================================
This file is the ONLY place message formats are defined.
Pre-commit Check 25 validates all queue operations use these schemas.

Usage:
    from shared.sqs_schemas import (
        validate_message,
        create_enricher_message,
        create_playwright_message,
        create_scraper_message,
    )

    # Validate incoming message
    is_valid, missing = validate_message('PARSER_TO_ENRICHER', message)

    # Create outgoing message (with validation)
    message = create_enricher_message(ticker='EPRT', ...)
"""

from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime, timezone

# ============================================================================
# Schema Definitions
# ============================================================================

# Parser → Enricher (via ENRICH_QUEUE)
PARSER_TO_ENRICHER_SCHEMA = {
    'required': ['ticker', 'idempotency_key', 'email_date', 'email_subject'],
    'optional': ['urls', 'email_received_at', 'press_release_date', 'press_release_title', 'queued_at'],
}

# Parser → Playwright (via PLAYWRIGHT_QUEUE)
# Enricher → Playwright (fallback routing)
# NOTE: email_date is critical for preserving timestamp (converts to email_received_at in Playwright)
PARSER_TO_PLAYWRIGHT_SCHEMA = {
    'required': ['ticker', 'idempotency_key', 'email_date', 'email_subject'],
    'optional': ['press_release_url', 'press_release_date', 'press_release_title', 'email_received_at', 'queued_at', 'company_name'],
}

# Parser → Scraper (via SCRAPE_QUEUE) - for newswire URLs
# Enricher → Scraper (for newswire URLs)
PARSER_TO_SCRAPER_SCHEMA = {
    'required': ['ticker', 'idempotency_key', 'url'],
    'optional': ['email_subject', 'company_name', 'queued_at'],
}

# Enricher → DLQ (landing page or failed match)
ENRICHER_TO_DLQ_SCHEMA = {
    'required': ['idempotency_key', 'classification'],
    'optional': ['ticker', 'email_subject', 'email_date', 'url', 'reason', 'metadata', 'queued_at'],
}

# Schema registry for lookup
SCHEMAS = {
    'PARSER_TO_ENRICHER': PARSER_TO_ENRICHER_SCHEMA,
    'PARSER_TO_PLAYWRIGHT': PARSER_TO_PLAYWRIGHT_SCHEMA,
    'PARSER_TO_SCRAPER': PARSER_TO_SCRAPER_SCHEMA,
    'ENRICHER_TO_DLQ': ENRICHER_TO_DLQ_SCHEMA,
}

# ============================================================================
# Validation Functions
# ============================================================================


def validate_message(schema_name: str, message: dict) -> tuple[bool, list]:
    """
    Validate message against schema.

    Args:
        schema_name: One of 'PARSER_TO_ENRICHER', 'PARSER_TO_PLAYWRIGHT', etc.
        message: Message dict to validate

    Returns:
        tuple: (is_valid, missing_fields)
    """
    schema = SCHEMAS.get(schema_name)
    if not schema:
        return False, [f"Unknown schema: {schema_name}. Valid: {', '.join(SCHEMAS.keys())}"]

    missing = [f for f in schema['required'] if f not in message]
    return len(missing) == 0, missing


def get_all_fields(schema_name: str) -> tuple[list, list]:
    """
    Get required and optional fields for a schema.

    Args:
        schema_name: Schema name

    Returns:
        tuple: (required_fields, optional_fields)
    """
    schema = SCHEMAS.get(schema_name)
    if not schema:
        return [], []
    return schema['required'], schema.get('optional', [])


# ============================================================================
# Message Builders (with validation)
# ============================================================================


@dataclass
class EnricherMessage:
    """Parser → Enricher message format."""
    ticker: str
    idempotency_key: str
    email_date: str
    email_subject: str
    urls: list = field(default_factory=list)
    email_received_at: Optional[str] = None
    press_release_date: Optional[str] = None
    press_release_title: Optional[str] = None
    queued_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        """Convert to dict, excluding None values."""
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class PlaywrightMessage:
    """Parser/Enricher → Playwright message format."""
    ticker: str
    idempotency_key: str
    email_date: str
    email_subject: str
    press_release_url: Optional[str] = None
    press_release_date: Optional[str] = None
    press_release_title: Optional[str] = None
    email_received_at: Optional[str] = None
    company_name: Optional[str] = None
    queued_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        """Convert to dict, excluding None values."""
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class ScraperMessage:
    """Parser/Enricher → Scraper message format."""
    ticker: str
    idempotency_key: str
    url: str
    email_subject: Optional[str] = None
    company_name: Optional[str] = None
    queued_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        """Convert to dict, excluding None values."""
        return {k: v for k, v in asdict(self).items() if v is not None}


# ============================================================================
# Factory Functions
# ============================================================================


def create_enricher_message(
    ticker: str,
    idempotency_key: str,
    email_date: str,
    email_subject: str,
    urls: list = None,
    press_release_date: str = None,
    press_release_title: str = None,
) -> dict:
    """Create validated enricher message."""
    msg = EnricherMessage(
        ticker=ticker,
        idempotency_key=idempotency_key,
        email_date=email_date,
        email_subject=email_subject,
        urls=urls or [],
        press_release_date=press_release_date,
        press_release_title=press_release_title,
    )
    return msg.to_dict()


def create_playwright_message(
    ticker: str,
    idempotency_key: str,
    email_date: str,
    email_subject: str,
    press_release_title: str = None,
    press_release_date: str = None,
) -> dict:
    """Create validated playwright message."""
    msg = PlaywrightMessage(
        ticker=ticker,
        idempotency_key=idempotency_key,
        email_date=email_date,
        email_subject=email_subject,
        press_release_title=press_release_title,
        press_release_date=press_release_date,
    )
    return msg.to_dict()


def create_scraper_message(
    ticker: str,
    idempotency_key: str,
    url: str,
    email_subject: str = None,
) -> dict:
    """Create validated scraper message."""
    msg = ScraperMessage(
        ticker=ticker,
        idempotency_key=idempotency_key,
        url=url,
        email_subject=email_subject,
    )
    return msg.to_dict()


# ============================================================================
# Example Generator (for test scripts)
# ============================================================================


def generate_example(schema_name: str) -> dict:
    """
    Generate example message for testing.

    Args:
        schema_name: Schema name

    Returns:
        dict: Example message with all required fields filled
    """
    examples = {
        'PARSER_TO_ENRICHER': {
            'ticker': 'EPRT',
            'idempotency_key': 'test-key-12345',
            'email_date': '2026-03-16',
            'email_subject': 'Essential Properties Reports Q4 Results',
            'urls': ['https://investors.essentialproperties.com/news/...'],
            'queued_at': datetime.now(timezone.utc).isoformat(),
        },
        'PARSER_TO_PLAYWRIGHT': {
            'ticker': 'O',
            'idempotency_key': 'test-key-67890',
            'email_date': '2026-03-16',
            'email_subject': 'Realty Income Announces Monthly Dividend',
            'press_release_title': 'Realty Income Announces 109th Consecutive Quarterly Dividend',
            'queued_at': datetime.now(timezone.utc).isoformat(),
        },
        'PARSER_TO_SCRAPER': {
            'ticker': 'VNO',
            'idempotency_key': 'test-key-11111',
            'url': 'https://www.globenewswire.com/news-release/...',
            'email_subject': 'Vornado Realty Trust Announces...',
            'queued_at': datetime.now(timezone.utc).isoformat(),
        },
        'ENRICHER_TO_DLQ': {
            'idempotency_key': 'test-key-22222',
            'classification': 'landing_page',
            'ticker': 'PK',
            'email_subject': 'Park Hotels Press Release',
            'url': 'https://ir.parkhotels.com/press-releases/2026',
            'reason': 'Year-based path detected: /press-releases/2026',
            'queued_at': datetime.now(timezone.utc).isoformat(),
        },
    }
    return examples.get(schema_name, {})
