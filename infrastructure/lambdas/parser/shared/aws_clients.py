"""
AWS Client Initialization
=========================
SOLID: Single Responsibility - Centralized AWS client management

All Lambda functions use these shared clients to avoid duplication.
"""

import boto3
import os

# ============================================================================
# AWS Clients - Single Source of Truth
# ============================================================================

# S3 Client (used by parser for email downloads)
s3 = boto3.client('s3')

# SQS Client (used by parser for queue operations)
sqs = boto3.client('sqs')

# DynamoDB Resource (used by all Lambdas)
dynamodb = boto3.resource('dynamodb')


# ============================================================================
# Environment Variables - Configuration
# ============================================================================

def get_env_var(key, default=None, required=False):
    """
    Get environment variable with optional default and required validation

    Args:
        key: Environment variable name
        default: Default value if not set (optional)
        required: Raise error if not set (default: False)

    Returns:
        Environment variable value

    Raises:
        ValueError: If required=True and variable not set
    """
    value = os.environ.get(key, default)
    if required and value is None:
        raise ValueError(f"Required environment variable not set: {key}")
    return value


# Common environment variables (loaded once)
S3_BUCKET = get_env_var('S3_BUCKET_NAME')
SCRAPE_QUEUE_URL = get_env_var('SCRAPE_QUEUE_URL')
PLAYWRIGHT_QUEUE_URL = get_env_var('PLAYWRIGHT_QUEUE_URL', '')
INBOUND_LOG_TABLE = get_env_var('INBOUND_LOG_TABLE')
REIT_NEWS_TABLE = get_env_var('REIT_NEWS_TABLE')
COMPANIES_TABLE = get_env_var('COMPANIES_TABLE')
URL_CACHE_TABLE = get_env_var('URL_CACHE_TABLE', 'reitsheet-url-cache')
LOG_LEVEL = get_env_var('LOG_LEVEL', 'INFO')
USER_AGENT = get_env_var('USER_AGENT', 'PressReleasePipeline/1.0 (+https://your-domain.com)')


# ============================================================================
# DynamoDB Table References
# ============================================================================

def get_table(table_name):
    """
    Get DynamoDB table reference

    Args:
        table_name: Table name from environment variable

    Returns:
        DynamoDB Table resource
    """
    if not table_name:
        raise ValueError("Table name cannot be empty")
    return dynamodb.Table(table_name)


# Pre-initialized tables (lazy loading pattern)
_tables = {}

def get_inbound_log_table():
    """Get inbound log table (cached)"""
    if 'inbound_log' not in _tables and INBOUND_LOG_TABLE:
        _tables['inbound_log'] = get_table(INBOUND_LOG_TABLE)
    return _tables.get('inbound_log')

def get_reit_news_table():
    """Get REIT news table (cached)"""
    if 'reit_news' not in _tables and REIT_NEWS_TABLE:
        _tables['reit_news'] = get_table(REIT_NEWS_TABLE)
    return _tables.get('reit_news')

def get_companies_table():
    """Get companies table (cached)"""
    if 'companies' not in _tables and COMPANIES_TABLE:
        _tables['companies'] = get_table(COMPANIES_TABLE)
    return _tables.get('companies')

def get_url_cache_table():
    """Get URL cache table (cached)"""
    if 'url_cache' not in _tables and URL_CACHE_TABLE:
        _tables['url_cache'] = get_table(URL_CACHE_TABLE)
    return _tables.get('url_cache')
