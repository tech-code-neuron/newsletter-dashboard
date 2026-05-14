"""
Environment Variable Registry - Single Source of Truth
=======================================================
Pre-commit Check 26 validates:
1. All os.environ['X'] in Lambda code exist in this registry
2. All registry entries have matching Terraform definitions

Usage:
    from shared.env_registry import LAMBDA_ENV_VARS, get_env_vars_for_lambda

    # Get all env vars for a Lambda
    required, optional = get_env_vars_for_lambda('parser')

    # Validate env var usage
    is_valid, error = validate_env_var('parser', 'S3_BUCKET_NAME')
"""

# ============================================================================
# Lambda Environment Variables
# ============================================================================

LAMBDA_ENV_VARS = {
    'parser': {
        'required': [
            'S3_BUCKET_NAME',      # Source bucket for emails
            'SCRAPE_QUEUE_URL',    # Newswire URL queue
            'ENRICH_QUEUE_URL',    # Enrichment queue
            'PLAYWRIGHT_QUEUE_URL', # JavaScript-rendered pages queue
            'INBOUND_LOG_TABLE',   # Email tracking table
            'REIT_NEWS_TABLE',     # Press release storage
            'COMPANIES_TABLE',     # Company configuration
        ],
        'optional': [
            'LOG_LEVEL',           # Logging verbosity
            'USE_GSI_MATCHING',    # Enable GSI-based company matching
            'USE_CONFIDENCE_SCORING',  # Enable confidence-based matching
            'MAX_MESSAGE_AGE_MINUTES',  # Stale message rejection
        ],
    },
    'enricher': {
        'required': [
            'SCRAPE_QUEUE_URL',    # Newswire URL queue (fallback)
            'PLAYWRIGHT_QUEUE_URL', # JavaScript-rendered pages queue (fallback)
            'REIT_NEWS_TABLE',     # Press release storage
            'COMPANIES_TABLE',     # Company configuration
            'ENRICH_DLQ_URL',      # Dead letter queue for manual review (circuit breaker gap fix)
        ],
        'optional': [
            'LOG_LEVEL',           # Logging verbosity
            'ENABLE_TITLE_CLEANUP',  # Enable title cleanup (default: true)
        ],
    },
    'playwright-scraper': {
        'required': [
            'REIT_NEWS_TABLE',     # Press release storage
            'COMPANIES_TABLE',     # Company configuration
        ],
        'optional': [
            'LOG_LEVEL',           # Logging verbosity
            'MAX_MESSAGE_AGE_MINUTES',  # Stale message rejection
            'PLAYWRIGHT_DLQ_URL',  # Dead letter queue
        ],
    },
    'scraper': {
        'required': [
            'REIT_NEWS_TABLE',     # Press release storage
            'COMPANIES_TABLE',     # Company configuration
        ],
        'optional': [
            'LOG_LEVEL',           # Logging verbosity
            'URL_CACHE_TABLE',     # URL validation cache table
        ],
    },
    'producer': {
        'required': [
            'S3_BUCKET_NAME',      # Source bucket for emails
            'PARSE_QUEUE_URL',     # Parse queue URL
        ],
        'optional': [
            'LOG_LEVEL',           # Logging verbosity
        ],
    },
    'email-forwarder': {
        'required': [
            'S3_BUCKET_NAME',      # Source bucket for emails
        ],
        'optional': [
            'LOG_LEVEL',           # Logging verbosity
            'FORWARD_TO_EMAIL',    # Outlook forwarding address
        ],
    },
    'dlq-processor': {
        'required': [
            'REIT_NEWS_TABLE',     # Press release storage
            'COMPANIES_TABLE',     # Company configuration
        ],
        'optional': [
            'LOG_LEVEL',           # Logging verbosity
            'ENRICH_QUEUE_URL',    # Re-queue URL
        ],
    },
}

# ============================================================================
# AWS Runtime-Provided Environment Variables (excluded from validation)
# ============================================================================

# These are automatically provided by AWS Lambda runtime
# and should NOT be defined in Terraform
AWS_RUNTIME_ENV_VARS = {
    'AWS_REGION',
    'AWS_DEFAULT_REGION',
    'AWS_LAMBDA_FUNCTION_NAME',
    'AWS_LAMBDA_FUNCTION_VERSION',
    'AWS_LAMBDA_FUNCTION_MEMORY_SIZE',
    'AWS_LAMBDA_LOG_GROUP_NAME',
    'AWS_LAMBDA_LOG_STREAM_NAME',
    'AWS_EXECUTION_ENV',
    'AWS_ACCESS_KEY_ID',
    'AWS_SECRET_ACCESS_KEY',
    'AWS_SESSION_TOKEN',
    'LAMBDA_TASK_ROOT',
    'LAMBDA_RUNTIME_DIR',
    '_HANDLER',
    '_X_AMZN_TRACE_ID',
    'TZ',
    'PATH',
    'LD_LIBRARY_PATH',
    'PYTHONPATH',
}

# ============================================================================
# Terraform File Paths (for cross-validation)
# ============================================================================

TERRAFORM_LAMBDA_FILES = {
    'parser': 'infrastructure/terraform/lambdas.tf',
    'enricher': 'infrastructure/terraform/lambda-enricher.tf',
    'playwright-scraper': 'infrastructure/terraform/lambda-playwright-scraper.tf',
    'scraper': 'infrastructure/terraform/lambda-scraper.tf',
    'producer': 'infrastructure/terraform/lambdas.tf',
    'email-forwarder': 'infrastructure/terraform/lambda-email-forwarder.tf',
    'dlq-processor': 'infrastructure/terraform/lambda-dlq-processor.tf',
}

# ============================================================================
# Helper Functions
# ============================================================================


def get_env_vars_for_lambda(lambda_name: str) -> tuple[list, list]:
    """
    Get required and optional env vars for a Lambda.

    Args:
        lambda_name: Lambda function name (e.g., 'parser', 'enricher')

    Returns:
        tuple: (required_vars, optional_vars)
    """
    config = LAMBDA_ENV_VARS.get(lambda_name, {})
    return config.get('required', []), config.get('optional', [])


def validate_env_var(lambda_name: str, var_name: str) -> tuple[bool, str]:
    """
    Validate that an environment variable is registered.

    Args:
        lambda_name: Lambda function name
        var_name: Environment variable name

    Returns:
        tuple: (is_valid, error_message)
    """
    # Check if it's an AWS runtime variable
    if var_name in AWS_RUNTIME_ENV_VARS:
        return True, ""

    config = LAMBDA_ENV_VARS.get(lambda_name)
    if not config:
        return False, f"Unknown Lambda: {lambda_name}"

    all_vars = set(config.get('required', [])) | set(config.get('optional', []))
    if var_name in all_vars:
        return True, ""

    return False, f"Env var '{var_name}' not in registry for {lambda_name}. Add to shared/env_registry.py"


def is_required_env_var(lambda_name: str, var_name: str) -> bool:
    """Check if an env var is required (not optional)."""
    config = LAMBDA_ENV_VARS.get(lambda_name, {})
    return var_name in config.get('required', [])


def get_terraform_file(lambda_name: str) -> str:
    """Get Terraform file path for a Lambda."""
    return TERRAFORM_LAMBDA_FILES.get(lambda_name, '')


def get_all_lambda_names() -> list:
    """Get all registered Lambda names."""
    return list(LAMBDA_ENV_VARS.keys())
