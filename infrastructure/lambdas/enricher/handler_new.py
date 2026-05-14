"""
DEPRECATED - DO NOT USE
========================

This file is a backup from the March 2026 SOLID refactoring.
The active handler is handler.py (Terraform: handler.lambda_handler).

This file uses the old enricher.* package architecture which has circular imports.
Kept for rollback reference only.

DELETION SCHEDULED: 2026-05-01

---
Original docstring:

Press Release Pipeline - URL Enricher Lambda (Refactored - SOLID 10/10)
============================================================
Purpose: Construct and validate press release URLs
Triggered by: SQS Enrichment Queue

SOLID Refactoring Complete:
- Single Responsibility: Each module does ONE thing
- Strategy Pattern: URL construction methods
- Open/Closed: Add URL methods without modifying existing code
- Dependency Injection: Testable components

Code Reduction: 777 lines → 60 lines handler (92% reduction)

Last Refactored: 2026-03-11
"""

import json
import logging
import boto3
import os

# Import refactored modules
from enricher.url_construction import construct_url_for_company
from enricher.url_validation import validate_url_exists
from enricher.url_selection import select_best_url_from_email
from enricher.url_classification import classify_url
from enricher.database_ops import initialize_tables as init_db_tables
from enricher.queue_ops import initialize_sqs
from enricher.company_lookup import initialize_tables as init_company_tables, get_company_config
from enricher.enrichment_processor import process_enrichment_job

# ============================================================================
# AWS Clients Initialization
# ============================================================================

s3 = boto3.client('s3')
sqs = boto3.client('sqs')
dynamodb = boto3.resource('dynamodb')

# ============================================================================
# Environment Variables
# ============================================================================

SCRAPE_QUEUE_URL = os.environ['SCRAPE_QUEUE_URL']
PLAYWRIGHT_QUEUE_URL = os.environ.get('PLAYWRIGHT_QUEUE_URL', '')
REIT_NEWS_TABLE = os.environ['REIT_NEWS_TABLE']
COMPANIES_TABLE = os.environ['COMPANIES_TABLE']
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

# ============================================================================
# DynamoDB Tables
# ============================================================================

reit_news_table = dynamodb.Table(REIT_NEWS_TABLE)
companies_table = dynamodb.Table(COMPANIES_TABLE)

# Initialize modules with dependencies
init_db_tables(reit_news_table)
init_company_tables(companies_table)
initialize_sqs(sqs, SCRAPE_QUEUE_URL)

# ============================================================================
# Logging Configuration
# ============================================================================

logger = logging.getLogger()
logger.setLevel(getattr(logging, LOG_LEVEL))


# ============================================================================
# Lambda Handler
# ============================================================================

def lambda_handler(event, context):
    """
    Main Lambda handler - process enrichment jobs from SQS

    Single Responsibility: Only handles SQS batch processing

    Message format (from Parser):
    {
        "ticker": "EPRT",
        "email_subject": "Essential Properties Announces Dividend",
        "email_date": "2026-03-09",
        "idempotency_key": "abc123",
        "urls": ["http://..."]
    }

    Returns:
        dict: Batch processing results for SQS partial failure handling
    """
    logger.info(f"📨 Received {len(event['Records'])} enrichment job(s)")

    results = {
        'saved': 0,
        'queued_scraping': 0,
        'failed': 0
    }

    batch_failures = []

    for record in event['Records']:
        try:
            job = json.loads(record['body'])
            result = process_enrichment_job(job)

            status = result.get('status', 'failed')
            results[status] = results.get(status, 0) + 1

        except Exception as e:
            logger.error(f"Error processing job: {e}", exc_info=True)
            results['failed'] += 1

            # Mark message for retry
            batch_failures.append({
                'itemIdentifier': record['messageId']
            })

    logger.info(f"✅ Enrichment complete: {results}")

    return {
        'statusCode': 200,
        'batchItemFailures': batch_failures,
        'body': json.dumps(results)
    }
