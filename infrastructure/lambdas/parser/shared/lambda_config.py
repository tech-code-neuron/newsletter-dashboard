"""
Lambda Configuration - Single Source of Truth
==============================================
Centralized configuration for Lambda invocation and testing.
Used by: invoke_lambda.py, test_parser.py, test_enricher.py

Pre-commit Check 31 validates usage of this module.
"""

# ============================================================================
# Lambda Function Registry
# ============================================================================

LAMBDA_CONFIG = {
    'parser': {
        'function_name': 'reitsheet-parser',
        's3_bucket': 'reitsheet-email-ingest',
        'payload_type': 'SQS_S3_EMAIL',
        'required_fields': ['bucket', 'key', 'idempotency_key'],
        'required_env_vars': [
            'S3_BUCKET_NAME',
            'ENRICH_QUEUE_URL',
            'PLAYWRIGHT_QUEUE_URL',
            'SCRAPE_QUEUE_URL',
            'COMPANY_CONFIG_TABLE',
            'INBOUND_LOG_TABLE',
        ],
        'description': 'Parses emails from S3, routes to enricher/playwright/scraper',
    },
    'enricher': {
        'function_name': 'reitsheet-enricher',
        's3_bucket': 'reitsheet-email-ingest',
        'payload_type': 'SQS_MESSAGE',
        'schema': 'PARSER_TO_ENRICHER',
        'required_env_vars': [
            'S3_BUCKET_NAME',
            'PLAYWRIGHT_QUEUE_URL',
            'SCRAPE_QUEUE_URL',
            'COMPANY_CONFIG_TABLE',
            'PRESS_RELEASES_TABLE',
        ],
        'description': 'Validates/constructs URLs, saves to DynamoDB or routes to playwright',
    },
    'playwright': {
        'function_name': 'reitsheet-playwright-scraper',
        'payload_type': 'SQS_MESSAGE',
        'schema': 'PARSER_TO_PLAYWRIGHT',
        'required_env_vars': [
            'COMPANY_CONFIG_TABLE',
            'PRESS_RELEASES_TABLE',
        ],
        'description': 'Browser-based scraper for JS-rendered pages',
    },
    'scraper': {
        'function_name': 'reitsheet-scraper',
        'payload_type': 'SQS_MESSAGE',
        'schema': 'PARSER_TO_SCRAPER',
        'required_env_vars': [
            'PRESS_RELEASES_TABLE',
        ],
        'description': 'HTTP-based scraper for newswire URLs',
    },
    'producer': {
        'function_name': 'reitsheet-producer',
        's3_bucket': 'reitsheet-email-ingest',
        'payload_type': 'MANUAL',
        'required_env_vars': [
            'PARSE_QUEUE_URL',
        ],
        'description': 'Scans S3 bucket and queues emails for parsing',
    },
    'email-forwarder': {
        'function_name': 'reitsheet-email-forwarder',
        's3_bucket': 'reitsheet-email-ingest',
        'payload_type': 'SES_EVENT',
        'required_env_vars': [
            'S3_BUCKET_NAME',
            'PARSE_QUEUE_URL',
        ],
        'description': 'Processes SES emails, forwards to parser queue',
    },
}

# ============================================================================
# S3 Bucket Registry
# ============================================================================

S3_BUCKETS = {
    'email_ingest': 'reitsheet-email-ingest',
    'email_access_logs': 'reitsheet-email-access-logs',
    'codebuild_source': 'reitsheet-codebuild-source',
    'tf_state': 'reitsheet-tf-state',
}

# Default bucket for email operations
DEFAULT_EMAIL_BUCKET = S3_BUCKETS['email_ingest']

# ============================================================================
# DynamoDB Table Registry
# ============================================================================

DYNAMODB_TABLES = {
    'companies_config': 'reitsheet-companies-config',
    'press_releases': 'reitsheet-press-releases',
    'inbound_log': 'reitsheet-inbound-log',
    'idempotency': 'reitsheet-idempotency',
}

# ============================================================================
# SQS Queue Registry (complementary to queue_names.py)
# ============================================================================

SQS_QUEUES = {
    'parse': 'reitsheet-email-parse-queue',
    'enrich': 'reitsheet-enrich-queue',
    'playwright': 'reitsheet-playwright-scraper-queue',
    'scrape': 'reitsheet-scrape-queue',
}

# ============================================================================
# Helper Functions
# ============================================================================


def get_lambda_config(lambda_name: str) -> dict:
    """
    Get configuration for a Lambda function.

    Args:
        lambda_name: Short name (parser, enricher, playwright, scraper)

    Returns:
        dict: Lambda configuration

    Raises:
        ValueError: If lambda_name is not found
    """
    if lambda_name not in LAMBDA_CONFIG:
        valid = ', '.join(LAMBDA_CONFIG.keys())
        raise ValueError(f"Unknown Lambda: '{lambda_name}'. Valid: {valid}")
    return LAMBDA_CONFIG[lambda_name]


def get_function_name(lambda_name: str) -> str:
    """Get AWS function name for a Lambda."""
    return get_lambda_config(lambda_name)['function_name']


def get_default_bucket(lambda_name: str) -> str:
    """Get default S3 bucket for a Lambda."""
    config = get_lambda_config(lambda_name)
    return config.get('s3_bucket', DEFAULT_EMAIL_BUCKET)


def get_required_env_vars(lambda_name: str) -> list:
    """Get required environment variables for a Lambda."""
    config = get_lambda_config(lambda_name)
    return config.get('required_env_vars', [])


def list_lambdas() -> list:
    """List all configured Lambda names."""
    return list(LAMBDA_CONFIG.keys())


def get_table_name(table_key: str) -> str:
    """
    Get DynamoDB table name.

    Args:
        table_key: Table key (companies_config, press_releases, etc.)

    Returns:
        str: Full table name
    """
    if table_key not in DYNAMODB_TABLES:
        valid = ', '.join(DYNAMODB_TABLES.keys())
        raise ValueError(f"Unknown table: '{table_key}'. Valid: {valid}")
    return DYNAMODB_TABLES[table_key]


def get_bucket_name(bucket_key: str) -> str:
    """
    Get S3 bucket name.

    Args:
        bucket_key: Bucket key (email_ingest, email_access_logs, etc.)

    Returns:
        str: Full bucket name
    """
    if bucket_key not in S3_BUCKETS:
        valid = ', '.join(S3_BUCKETS.keys())
        raise ValueError(f"Unknown bucket: '{bucket_key}'. Valid: {valid}")
    return S3_BUCKETS[bucket_key]
