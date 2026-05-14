"""
Shared Lambda Components
========================
SOLID-compliant shared code for all Lambda functions

Modules:
- aws_clients: AWS client initialization (S3, SQS, DynamoDB)
- constants: Shared constants and configurations
- logging_config: Centralized logging configuration
- url_strategies: URL construction strategies (Strategy Pattern)
- scraper_layers: Scraper layer base class and implementations
"""

__all__ = [
    'aws_clients',
    'constants',
    'dynamodb_update_builder',
    'logging_config',
    'url_strategies',
    'scraper_layers'
]
