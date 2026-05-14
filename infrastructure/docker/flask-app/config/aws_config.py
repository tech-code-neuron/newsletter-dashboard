"""
AWS Configuration - Auto-detection for ECS vs Local environments

SOLID: Single Responsibility - Only handles AWS environment detection and configuration

Usage:
    from config.aws_config import aws_config

    if aws_config.is_ecs:
        # Use DynamoDB, Secrets Manager
        db = aws_config.get_dynamodb_table('reitsheet-reit-news-v2')
    else:
        # Use SQLite
        db = get_local_session()
"""
import os
import json
import logging
from functools import lru_cache
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class AWSConfig:
    """
    AWS configuration manager with environment auto-detection.

    Auto-detects ECS environment via IS_ECS env var or ECS metadata endpoint.
    Provides lazy-loaded boto3 resources with caching.
    """

    def __init__(self):
        self._boto3 = None
        self._dynamodb = None
        self._secretsmanager = None
        self._s3 = None
        self._secrets_cache: Dict[str, Any] = {}

    @property
    def is_ecs(self) -> bool:
        """Check if running in ECS environment."""
        # Explicit environment variable (set in task definition)
        if os.environ.get('IS_ECS', '').lower() == 'true':
            return True

        # ECS metadata endpoint exists
        if os.environ.get('ECS_CONTAINER_METADATA_URI_V4'):
            return True

        return False

    @property
    def is_local(self) -> bool:
        """Check if running locally (inverse of is_ecs)."""
        return not self.is_ecs

    @property
    def aws_region(self) -> str:
        """Get AWS region from environment or default."""
        return os.environ.get('AWS_REGION', 'us-east-1')

    @property
    def boto3(self):
        """Lazy-load boto3 module."""
        if self._boto3 is None:
            import boto3
            self._boto3 = boto3
        return self._boto3

    @property
    def dynamodb(self):
        """Get DynamoDB resource (cached)."""
        if self._dynamodb is None:
            self._dynamodb = self.boto3.resource('dynamodb', region_name=self.aws_region)
        return self._dynamodb

    @property
    def secretsmanager(self):
        """Get Secrets Manager client (cached)."""
        if self._secretsmanager is None:
            self._secretsmanager = self.boto3.client('secretsmanager', region_name=self.aws_region)
        return self._secretsmanager

    @property
    def s3(self):
        """Get S3 resource (cached)."""
        if self._s3 is None:
            self._s3 = self.boto3.resource('s3', region_name=self.aws_region)
        return self._s3

    def get_dynamodb_table(self, table_name: str):
        """Get a DynamoDB table resource."""
        return self.dynamodb.Table(table_name)

    def get_secret(self, secret_name: str, key: Optional[str] = None) -> Any:
        """
        Retrieve a secret from Secrets Manager (cached).

        Args:
            secret_name: Name of the secret (e.g., 'reitsheet/flask-app/secrets')
            key: Optional key within the JSON secret

        Returns:
            Full secret dict if key is None, otherwise the specific key's value
        """
        if secret_name not in self._secrets_cache:
            try:
                response = self.secretsmanager.get_secret_value(SecretId=secret_name)
                secret_string = response.get('SecretString', '{}')
                self._secrets_cache[secret_name] = json.loads(secret_string)
                logger.info(f"Retrieved secret: {secret_name}")
            except Exception as e:
                logger.error(f"Failed to retrieve secret {secret_name}: {e}")
                self._secrets_cache[secret_name] = {}

        secret = self._secrets_cache[secret_name]

        if key:
            return secret.get(key)
        return secret

    def get_env_or_secret(self, env_var: str, secret_name: str = None, secret_key: str = None) -> Optional[str]:
        """
        Get value from environment variable, falling back to Secrets Manager.

        Args:
            env_var: Environment variable name
            secret_name: Secrets Manager secret name (optional)
            secret_key: Key within the secret (defaults to env_var name)

        Returns:
            Value from env var or secret, or None if not found
        """
        # First try environment variable
        value = os.environ.get(env_var)
        if value and value != 'PLACEHOLDER_CHANGE_ME_AFTER_DEPLOY':
            return value

        # Fall back to Secrets Manager if in ECS
        if self.is_ecs and secret_name:
            key = secret_key or env_var
            return self.get_secret(secret_name, key)

        return None

    # -------------------------------------------------------------------------
    # Convenience methods for common secrets
    # -------------------------------------------------------------------------

    @property
    def flask_secret_key(self) -> str:
        """Get Flask secret key."""
        key = self.get_env_or_secret(
            'FLASK_SECRET_KEY',
            'reitsheet/flask-app/secrets',
            'FLASK_SECRET_KEY'
        )
        return key or 'dev-secret-key-change-in-production'

    @property
    def anthropic_api_key(self) -> Optional[str]:
        """Get Anthropic API key."""
        return self.get_env_or_secret(
            'ANTHROPIC_API_KEY',
            'reitsheet/flask-app/secrets',
            'ANTHROPIC_API_KEY'
        )

    @property
    def gmail_credentials(self) -> Optional[Dict]:
        """Get Gmail API credentials as dict."""
        creds_str = self.get_env_or_secret(
            'GMAIL_CREDENTIALS',
            'reitsheet/flask-app/secrets',
            'GMAIL_CREDENTIALS'
        )
        if creds_str and creds_str != '{}':
            try:
                return json.loads(creds_str) if isinstance(creds_str, str) else creds_str
            except json.JSONDecodeError:
                logger.error("Failed to parse GMAIL_CREDENTIALS as JSON")
        return None

    # -------------------------------------------------------------------------
    # Table name helpers
    # -------------------------------------------------------------------------

    @property
    def reit_news_table_name(self) -> str:
        """Get REIT news table name."""
        return os.environ.get('REIT_NEWS_TABLE', 'reitsheet-reit-news-v2')

    @property
    def companies_table_name(self) -> str:
        """Get companies config table name."""
        return os.environ.get('COMPANIES_TABLE', 'reitsheet-companies-config')

    @property
    def comments_table_name(self) -> str:
        """Get URL comments table name."""
        return os.environ.get('COMMENTS_TABLE', 'reitsheet-url-test-comments')

    @property
    def audit_table_name(self) -> str:
        """Get audit table name."""
        return os.environ.get('AUDIT_TABLE', 'reitsheet-press-release-audit')


# Global singleton instance
aws_config = AWSConfig()


# Convenience exports
def is_ecs() -> bool:
    """Check if running in ECS."""
    return aws_config.is_ecs


def is_local() -> bool:
    """Check if running locally."""
    return aws_config.is_local


def get_dynamodb_table(table_name: str):
    """Get a DynamoDB table resource."""
    return aws_config.get_dynamodb_table(table_name)
