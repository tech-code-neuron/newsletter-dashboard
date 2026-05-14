"""
Queue Names - Single Source of Truth
=====================================
These constants MUST match infrastructure/terraform/locals.tf and sqs-enrich.tf

Pre-commit Check 27 validates consistency between this file and Terraform.

Usage:
    from shared.queue_names import PLAYWRIGHT_QUEUE, ENRICH_QUEUE, ...

    # In test scripts:
    from shared.queue_names import get_queue_url
    url = get_queue_url('playwright')  # Returns full URL
"""

# ============================================================================
# Project Name (must match Terraform var.project_name)
# ============================================================================

PROJECT_NAME = "reitsheet"

# ============================================================================
# Official Queue Names (must match Terraform definitions)
# ============================================================================

# Parser output queues
PARSE_QUEUE = f"{PROJECT_NAME}-email-parse-queue"
ENRICH_QUEUE = f"{PROJECT_NAME}-enrich-queue"  # From sqs-enrich.tf
SCRAPE_QUEUE = f"{PROJECT_NAME}-scrape-queue"
PLAYWRIGHT_QUEUE = f"{PROJECT_NAME}-playwright-scraper-queue"  # NOT "playwright-queue"
SIMPLE_SCRAPER_QUEUE = f"{PROJECT_NAME}-simple-scraper-queue"

# Dead Letter Queues
PARSE_DLQ = f"{PROJECT_NAME}-email-parse-dlq"
ENRICH_DLQ = f"{PROJECT_NAME}-enrich-dlq"
SCRAPE_DLQ = f"{PROJECT_NAME}-scrape-dlq"
PLAYWRIGHT_DLQ = f"{PROJECT_NAME}-playwright-scraper-dlq"
SIMPLE_SCRAPER_DLQ = f"{PROJECT_NAME}-simple-scraper-dlq"

# ============================================================================
# Queue Name Mapping (for programmatic access)
# ============================================================================

QUEUE_NAMES = {
    'parse': PARSE_QUEUE,
    'enrich': ENRICH_QUEUE,
    'scrape': SCRAPE_QUEUE,
    'playwright': PLAYWRIGHT_QUEUE,
    'simple_scraper': SIMPLE_SCRAPER_QUEUE,
    'parse_dlq': PARSE_DLQ,
    'enrich_dlq': ENRICH_DLQ,
    'scrape_dlq': SCRAPE_DLQ,
    'playwright_dlq': PLAYWRIGHT_DLQ,
    'simple_scraper_dlq': SIMPLE_SCRAPER_DLQ,
}

# ============================================================================
# Queue URL Construction (for test scripts)
# ============================================================================


def get_queue_url(queue_type: str, region: str = 'us-east-1', account_id: str = '123456789012') -> str:
    """
    Get full SQS queue URL for a given queue type.

    Args:
        queue_type: One of 'parse', 'enrich', 'scrape', 'playwright', 'simple_scraper'
                   or their DLQ variants (e.g., 'parse_dlq')
        region: AWS region (default: us-east-1)
        account_id: AWS account ID (default: production account)

    Returns:
        Full SQS queue URL

    Raises:
        ValueError: If queue_type is not recognized
    """
    queue_name = QUEUE_NAMES.get(queue_type)
    if not queue_name:
        valid_types = ', '.join(sorted(QUEUE_NAMES.keys()))
        raise ValueError(f"Unknown queue type: {queue_type}. Valid types: {valid_types}")

    return f"https://sqs.{region}.amazonaws.com/{account_id}/{queue_name}"


# ============================================================================
# Validation (for pre-commit checks)
# ============================================================================


def validate_queue_name(name: str) -> tuple[bool, str]:
    """
    Validate that a queue name matches official names.

    Args:
        name: Queue name to validate

    Returns:
        tuple: (is_valid, error_message)
    """
    if name in QUEUE_NAMES.values():
        return True, ""

    # Check for common typos
    typo_suggestions = {
        f"{PROJECT_NAME}-playwright-queue": PLAYWRIGHT_QUEUE,
        f"{PROJECT_NAME}-playwright-scraper": PLAYWRIGHT_QUEUE,
        f"{PROJECT_NAME}-enricher-queue": ENRICH_QUEUE,
        f"{PROJECT_NAME}-enrichment-queue": ENRICH_QUEUE,
    }

    suggestion = typo_suggestions.get(name)
    if suggestion:
        return False, f"Typo detected: '{name}' should be '{suggestion}'"

    return False, f"Unknown queue name: '{name}'. See shared/queue_names.py for official names."
