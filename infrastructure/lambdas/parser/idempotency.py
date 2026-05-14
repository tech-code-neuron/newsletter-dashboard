"""
Parser Lambda - Idempotency
============================
Prevent duplicate processing of emails

SOLID Principles:
- Single Responsibility: Each function does ONE thing
- No Hardcoded Values: All constants imported

Last Updated: 2026-03-09
"""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from constants import IDEMPOTENCY_TTL_DAYS

logger = logging.getLogger()

# ============================================================================
# Idempotency Check
# ============================================================================


def check_idempotency(idempotency_key, inbound_log_table):
    """
    Check if email has already been processed

    Single Responsibility: Only checks for duplicates

    Args:
        idempotency_key: Unique key for this email
        inbound_log_table: DynamoDB table resource

    Returns:
        bool: True if already processed, False if new
    """
    try:
        response = inbound_log_table.get_item(Key={'idempotency_key': idempotency_key})
        if 'Item' in response:
            logger.info(f"Email already processed (idempotency): {idempotency_key}")
            return True
        return False
    except Exception as e:
        logger.error(f"Error checking idempotency: {e}")
        # Fail open - allow processing if check fails
        return False


# ============================================================================
# Mark as Processed
# ============================================================================


def mark_as_processed(idempotency_key, metadata, inbound_log_table):
    """
    Mark email as processed in idempotency log

    Single Responsibility: Only writes to log

    Args:
        idempotency_key: Unique key for this email
        metadata: Processing metadata (ticker, subject, routing, etc.)
        inbound_log_table: DynamoDB table resource

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Calculate TTL (auto-delete after N days)
        ttl = int((datetime.now(timezone.utc) + timedelta(days=IDEMPOTENCY_TTL_DAYS)).timestamp())

        # Convert floats to Decimal for DynamoDB compatibility
        sanitized_metadata = {}
        for key, value in metadata.items():
            if isinstance(value, float):
                sanitized_metadata[key] = Decimal(str(value))
            else:
                sanitized_metadata[key] = value

        # Build item
        item = {
            'idempotency_key': idempotency_key,
            'processed_at': datetime.now(timezone.utc).isoformat(),
            'ttl': ttl,
            **sanitized_metadata  # Include all metadata (ticker, subject, routing, etc.)
        }

        # Save to DynamoDB
        inbound_log_table.put_item(Item=item)

        logger.info(f"Marked as processed: {idempotency_key}")
        return True

    except Exception as e:
        logger.error(f"Error marking as processed: {e}")
        return False
