"""
Lazy Configuration Loader for Lambda Handlers
==============================================
Defers environment variable access and DynamoDB table initialization
until first use, enabling local smoke tests to import handlers without
requiring actual environment variables.

Usage in handler.py:
    from shared.config_loader import get_env, get_table, get_sqs_client, get_dynamodb

    # Instead of: S3_BUCKET = os.environ['S3_BUCKET_NAME']
    # Use: get_env('S3_BUCKET_NAME')  # Called when needed

    # Instead of: reit_news_table = dynamodb.Table(REIT_NEWS_TABLE)
    # Use: get_table('reit_news')  # Lazily initialized

Why this pattern:
    - AST-based smoke tests can import handler.py without env vars
    - Lambda runtime works identically (env vars ARE set)
    - @lru_cache ensures single lookup (no performance impact)
    - Fail-fast: Missing env vars raise immediately on first use

Added: 2026-03-19
"""

import os
import boto3
from functools import lru_cache
from typing import Any, Optional, Dict


# =============================================================================
# Environment Variable Access (Lazy)
# =============================================================================

def get_env(name: str, default: Optional[str] = None) -> str:
    """
    Get environment variable with optional default.

    Defers access until called (not at module import time).

    Args:
        name: Environment variable name
        default: Default value if not set (None = required)

    Returns:
        Environment variable value

    Raises:
        KeyError: If required (no default) and not set
    """
    if default is None:
        return os.environ[name]
    return os.environ.get(name, default)


def get_env_bool(name: str, default: bool = False) -> bool:
    """
    Get boolean environment variable.

    Args:
        name: Environment variable name
        default: Default value if not set

    Returns:
        True if value is 'true' (case-insensitive)
    """
    return os.environ.get(name, str(default)).lower() == 'true'


def get_env_int(name: str, default: int) -> int:
    """
    Get integer environment variable.

    Args:
        name: Environment variable name
        default: Default value if not set

    Returns:
        Integer value
    """
    return int(os.environ.get(name, str(default)))


def get_env_list(name: str, default: str = '') -> list:
    """
    Get comma-separated list from environment variable.

    Args:
        name: Environment variable name
        default: Default comma-separated string

    Returns:
        List of strings (empty list if empty string)
    """
    value = os.environ.get(name, default)
    return value.split(',') if value else []


# =============================================================================
# AWS Clients (Lazy Singletons)
# =============================================================================

_clients: Dict[str, Any] = {}


def get_dynamodb():
    """Get DynamoDB resource (lazy singleton)."""
    if 'dynamodb' not in _clients:
        _clients['dynamodb'] = boto3.resource('dynamodb')
    return _clients['dynamodb']


def get_sqs_client():
    """Get SQS client (lazy singleton)."""
    if 'sqs' not in _clients:
        _clients['sqs'] = boto3.client('sqs')
    return _clients['sqs']


def get_s3_client():
    """Get S3 client (lazy singleton)."""
    if 's3' not in _clients:
        _clients['s3'] = boto3.client('s3')
    return _clients['s3']


def get_ses_client():
    """Get SES client (lazy singleton)."""
    if 'ses' not in _clients:
        _clients['ses'] = boto3.client('ses')
    return _clients['ses']


def get_sns_client():
    """Get SNS client (lazy singleton)."""
    if 'sns' not in _clients:
        _clients['sns'] = boto3.client('sns')
    return _clients['sns']


def get_cloudwatch_client():
    """Get CloudWatch client (lazy singleton)."""
    if 'cloudwatch' not in _clients:
        _clients['cloudwatch'] = boto3.client('cloudwatch')
    return _clients['cloudwatch']


# =============================================================================
# DynamoDB Tables (Lazy Initialization)
# =============================================================================

_tables: Dict[str, Any] = {}


def get_table(table_env_var: str, default_name: Optional[str] = None):
    """
    Get DynamoDB table (lazy initialization).

    Args:
        table_env_var: Environment variable containing table name
        default_name: Default table name if env var not set

    Returns:
        DynamoDB Table resource

    Example:
        # Instead of: reit_news_table = dynamodb.Table(os.environ['REIT_NEWS_TABLE'])
        # Use: get_table('REIT_NEWS_TABLE')
    """
    if table_env_var not in _tables:
        if default_name is not None:
            table_name = os.environ.get(table_env_var, default_name)
        else:
            table_name = os.environ[table_env_var]
        _tables[table_env_var] = get_dynamodb().Table(table_name)
    return _tables[table_env_var]


# =============================================================================
# Testing Support
# =============================================================================

def reset_for_testing():
    """
    Reset all cached clients and tables (for unit testing).

    Call this in test setup to ensure fresh state.
    """
    global _clients, _tables
    _clients = {}
    _tables = {}


def mock_env(env_vars: Dict[str, str]):
    """
    Context manager to temporarily set environment variables (for testing).

    Usage:
        with mock_env({'S3_BUCKET_NAME': 'test-bucket'}):
            assert get_env('S3_BUCKET_NAME') == 'test-bucket'
    """
    import contextlib

    @contextlib.contextmanager
    def _mock():
        original = {}
        for key, value in env_vars.items():
            original[key] = os.environ.get(key)
            os.environ[key] = value
        try:
            yield
        finally:
            for key, orig_value in original.items():
                if orig_value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = orig_value

    return _mock()
