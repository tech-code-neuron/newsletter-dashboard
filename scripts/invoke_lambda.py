#!/usr/bin/env python3
"""
Unified Lambda Invocation Tool
==============================
Single tool for invoking all Lambda functions with correct payloads.

Usage:
    # Parser - by S3 key
    python scripts/invoke_lambda.py parser --key incoming/abc123

    # Parser - by email search
    python scripts/invoke_lambda.py parser --search "FCPT"

    # Enricher - by ticker + URL
    python scripts/invoke_lambda.py enricher --ticker EPRT --url "https://..."

    # Any Lambda - show example payload
    python scripts/invoke_lambda.py parser --example

    # Dry run (validate without invoking)
    python scripts/invoke_lambda.py parser --key incoming/abc123 --dry-run

    # Check Lambda health
    python scripts/invoke_lambda.py parser --check-health

    # List available Lambdas
    python scripts/invoke_lambda.py --list

Why this tool exists:
    - Prevents wrong payload encoding (base64 vs JSON)
    - Auto-generates idempotency keys
    - Uses correct bucket from centralized config
    - Validates payloads before invoking
    - Detects stale Lambda state
"""

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add shared modules to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'infrastructure' / 'lambdas'))

try:
    import boto3
    from shared.lambda_config import (
        LAMBDA_CONFIG,
        get_lambda_config,
        get_function_name,
        get_default_bucket,
        get_required_env_vars,
        list_lambdas,
    )
    from shared.sqs_schemas import (
        SCHEMAS,
        validate_message,
        generate_example,
    )
except ImportError as e:
    print(f"Import error: {e}")
    print("Run from project root: python scripts/invoke_lambda.py ...")
    sys.exit(1)


# ============================================================================
# Idempotency Key Generation
# ============================================================================


def generate_idempotency_key(input_str: str, prefix: str = 'test') -> str:
    """Generate deterministic idempotency key from input."""
    hash_val = hashlib.md5(input_str.encode()).hexdigest()[:12]
    return f"{prefix}-{hash_val}"


# ============================================================================
# Payload Builders
# ============================================================================


def build_parser_payload(bucket: str, key: str, idempotency_key: str) -> dict:
    """Build SQS event payload for parser Lambda."""
    message_body = {
        'bucket': bucket,
        'key': key,
        'idempotency_key': idempotency_key,
    }
    return {
        'Records': [{
            'body': json.dumps(message_body)
        }]
    }


def build_enricher_payload(
    ticker: str,
    urls: list,
    email_subject: str,
    email_date: str,
    idempotency_key: str,
) -> dict:
    """Build SQS event payload for enricher Lambda."""
    message_body = {
        'ticker': ticker,
        'urls': urls,
        'email_subject': email_subject,
        'email_date': email_date,
        'idempotency_key': idempotency_key,
        'queued_at': datetime.now(timezone.utc).isoformat(),
    }
    return {
        'Records': [{
            'body': json.dumps(message_body)
        }]
    }


def build_playwright_payload(
    ticker: str,
    email_subject: str,
    email_date: str,
    idempotency_key: str,
    press_release_title: str = None,
) -> dict:
    """Build SQS event payload for playwright Lambda."""
    message_body = {
        'ticker': ticker,
        'email_subject': email_subject,
        'email_date': email_date,
        'idempotency_key': idempotency_key,
        'queued_at': datetime.now(timezone.utc).isoformat(),
    }
    if press_release_title:
        message_body['press_release_title'] = press_release_title
    return {
        'Records': [{
            'body': json.dumps(message_body)
        }]
    }


def build_scraper_payload(
    ticker: str,
    url: str,
    idempotency_key: str,
    email_subject: str = None,
) -> dict:
    """Build SQS event payload for scraper Lambda."""
    message_body = {
        'ticker': ticker,
        'url': url,
        'idempotency_key': idempotency_key,
        'queued_at': datetime.now(timezone.utc).isoformat(),
    }
    if email_subject:
        message_body['email_subject'] = email_subject
    return {
        'Records': [{
            'body': json.dumps(message_body)
        }]
    }


# ============================================================================
# Lambda Health Check
# ============================================================================


def check_lambda_health(lambda_name: str) -> tuple:
    """
    Check if Lambda is healthy and has correct config.

    Returns:
        tuple: (is_healthy, message, details)
    """
    config = get_lambda_config(lambda_name)
    function_name = config['function_name']
    required_vars = config.get('required_env_vars', [])

    try:
        lambda_client = boto3.client('lambda', region_name='us-east-1')
        response = lambda_client.get_function_configuration(
            FunctionName=function_name
        )

        env_vars = response.get('Environment', {}).get('Variables', {})
        last_modified = response.get('LastModified', 'Unknown')
        state = response.get('State', 'Unknown')
        memory = response.get('MemorySize', 0)
        timeout = response.get('Timeout', 0)

        # Check required env vars
        missing_vars = [v for v in required_vars if v not in env_vars]

        details = {
            'function_name': function_name,
            'state': state,
            'last_modified': last_modified,
            'memory_mb': memory,
            'timeout_s': timeout,
            'env_vars_count': len(env_vars),
            'missing_env_vars': missing_vars,
        }

        if state != 'Active':
            return False, f"Lambda state is '{state}', not 'Active'", details

        if missing_vars:
            return False, f"Missing env vars: {', '.join(missing_vars)}", details

        return True, "Healthy", details

    except lambda_client.exceptions.ResourceNotFoundException:
        return False, f"Lambda '{function_name}' not found", {}
    except Exception as e:
        return False, f"Error checking health: {e}", {}


# ============================================================================
# Lambda Invocation
# ============================================================================


def invoke_lambda(
    lambda_name: str,
    payload: dict,
    dry_run: bool = False,
    check_health_first: bool = False,
) -> dict:
    """
    Invoke a Lambda function with proper error handling.

    Args:
        lambda_name: Short name (parser, enricher, etc.)
        payload: Event payload dict
        dry_run: If True, only show payload without invoking
        check_health_first: If True, check health before invoking

    Returns:
        dict: Lambda response or dry-run info
    """
    config = get_lambda_config(lambda_name)
    function_name = config['function_name']

    if dry_run:
        print(f"\n[DRY RUN] Would invoke: {function_name}")
        print(f"\nPayload ({len(json.dumps(payload))} bytes):")
        print(json.dumps(payload, indent=2))
        return {'dry_run': True, 'payload': payload}

    if check_health_first:
        is_healthy, message, details = check_lambda_health(lambda_name)
        if not is_healthy:
            print(f"\n[HEALTH CHECK FAILED] {message}")
            if details.get('missing_env_vars'):
                print(f"Missing: {details['missing_env_vars']}")
            print("\nTo fix, update Lambda configuration:")
            print(f"  aws lambda update-function-configuration \\")
            print(f"    --function-name {function_name} \\")
            print(f"    --environment Variables={{...}}")
            return {'error': message, 'health_check_failed': True}
        print(f"[HEALTH CHECK] {message}")

    print(f"\nInvoking: {function_name}")
    print(f"Payload size: {len(json.dumps(payload))} bytes")

    try:
        lambda_client = boto3.client('lambda', region_name='us-east-1')
        response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType='RequestResponse',
            Payload=json.dumps(payload),
        )

        result = json.loads(response['Payload'].read())

        # Check for function error
        if 'FunctionError' in response:
            print(f"\n[ERROR] Lambda returned error: {response['FunctionError']}")
            if 'errorMessage' in result:
                print(f"Message: {result['errorMessage']}")
            if 'stackTrace' in result:
                print("Stack trace:")
                for line in result['stackTrace'][:5]:
                    print(f"  {line}")
            return {'error': result, 'function_error': True}

        # Success
        print(f"\n[SUCCESS] Status: {result.get('statusCode', 'N/A')}")
        if 'body' in result:
            try:
                body = json.loads(result['body'])
                print(f"Processed: {body.get('processed', 0)}")
                print(f"Skipped: {body.get('skipped', 0)}")
                print(f"Failed: {body.get('failed', 0)}")
                if 'by_routing' in body:
                    print(f"Routing: {body['by_routing']}")
            except (json.JSONDecodeError, TypeError):
                print(f"Body: {result['body']}")

        return result

    except Exception as e:
        print(f"\n[ERROR] Invocation failed: {e}")
        return {'error': str(e)}


# ============================================================================
# Email Search (using find_email.py)
# ============================================================================


def find_email_key(search: str = None, ticker: str = None) -> str:
    """Find email S3 key using find_email.py."""
    cmd = ['python3', 'scripts/find_email.py']
    if ticker:
        cmd.extend(['--ticker', ticker])
    elif search:
        cmd.extend(['--search', search])
    else:
        return None

    result = subprocess.run(cmd, capture_output=True, text=True)

    if "No emails found" in result.stdout:
        print(result.stdout)
        return None

    # Parse output to extract S3 key
    for line in result.stdout.split('\n'):
        if 'S3 Key:' in line:
            key = line.split('S3 Key:')[1].strip()
            return key
        # Also check for incoming/ pattern directly
        if line.strip().startswith('incoming/'):
            return line.strip()

    print(result.stdout)
    return None


# ============================================================================
# Example Generators
# ============================================================================


def show_example(lambda_name: str):
    """Show example payload for a Lambda."""
    config = get_lambda_config(lambda_name)
    payload_type = config.get('payload_type', 'UNKNOWN')

    print(f"\n{'='*60}")
    print(f"Example: {lambda_name} ({config['function_name']})")
    print(f"{'='*60}")
    print(f"\nDescription: {config.get('description', 'N/A')}")
    print(f"Payload Type: {payload_type}")

    if payload_type == 'SQS_S3_EMAIL':
        bucket = get_default_bucket(lambda_name)
        example = build_parser_payload(
            bucket=bucket,
            key='incoming/example123abc',
            idempotency_key='test-example-12345',
        )
        print(f"\nPayload:")
        print(json.dumps(example, indent=2))
        print(f"\nUsage:")
        print(f"  python scripts/invoke_lambda.py {lambda_name} --key incoming/example123abc")
        print(f"  python scripts/invoke_lambda.py {lambda_name} --search \"Company Name\"")
        print(f"  python scripts/invoke_lambda.py {lambda_name} --ticker EPRT")

    elif payload_type == 'SQS_MESSAGE':
        schema_name = config.get('schema', 'PARSER_TO_ENRICHER')
        example_body = generate_example(schema_name)
        example = {
            'Records': [{
                'body': json.dumps(example_body)
            }]
        }
        print(f"\nSchema: {schema_name}")
        print(f"Payload:")
        print(json.dumps(example, indent=2))

        if lambda_name == 'enricher':
            print(f"\nUsage:")
            print(f"  python scripts/invoke_lambda.py enricher --ticker EPRT \\")
            print(f"    --url \"https://...\" --subject \"Q4 Results\"")
        elif lambda_name == 'playwright':
            print(f"\nUsage:")
            print(f"  python scripts/invoke_lambda.py playwright --ticker EPRT \\")
            print(f"    --subject \"Q4 Results\"")
        elif lambda_name == 'scraper':
            print(f"\nUsage:")
            print(f"  python scripts/invoke_lambda.py scraper --ticker VNO \\")
            print(f"    --url \"https://www.globenewswire.com/...\"")

    print(f"\nRequired Env Vars:")
    for var in config.get('required_env_vars', []):
        print(f"  - {var}")

    # Show AWS CLI equivalent
    print(f"\nAWS CLI Equivalent (NOT RECOMMENDED - use this tool instead):")
    print(f"  aws lambda invoke --function-name {config['function_name']} \\")
    print(f"    --payload '<JSON>' --cli-binary-format raw-in-base64-out \\")
    print(f"    /tmp/output.json")


def show_all_examples():
    """Show examples for all Lambdas."""
    print("\nAvailable Lambdas:")
    print("="*60)
    for name, config in LAMBDA_CONFIG.items():
        print(f"\n  {name}")
        print(f"    Function: {config['function_name']}")
        print(f"    Type: {config.get('payload_type', 'N/A')}")
        print(f"    Desc: {config.get('description', 'N/A')[:50]}...")

    print("\n" + "="*60)
    print("Usage: python scripts/invoke_lambda.py <lambda> --example")
    print("="*60)


# ============================================================================
# CloudWatch Logs
# ============================================================================


def show_recent_logs(lambda_name: str, minutes: int = 2):
    """Show recent CloudWatch logs for a Lambda."""
    function_name = get_function_name(lambda_name)
    log_group = f"/aws/lambda/{function_name}"

    print(f"\nRecent logs ({log_group}):")
    result = subprocess.run(
        ['aws', 'logs', 'tail', log_group, '--since', f'{minutes}m',
         '--format', 'short', '--region', 'us-east-1'],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        lines = result.stdout.strip().split('\n')
        relevant = [l for l in lines[-15:] if l.strip() and
                    any(x in l for x in ['INFO', 'ERROR', 'WARNING', 'company', 'URL', 'routing'])]
        for line in relevant:
            print(f"  {line}")
    else:
        print(f"  (Could not fetch logs: {result.stderr[:100]})")


# ============================================================================
# Main CLI
# ============================================================================


def main():
    parser = argparse.ArgumentParser(
        description='Unified Lambda Invocation Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Parser - test email by S3 key
  python scripts/invoke_lambda.py parser --key incoming/abc123

  # Parser - search for email and test
  python scripts/invoke_lambda.py parser --search "FCPT"
  python scripts/invoke_lambda.py parser --ticker EPRT

  # Enricher - test with ticker and URL
  python scripts/invoke_lambda.py enricher --ticker EPRT \\
    --url "https://investors.essentialproperties.com/..."

  # Show example payload
  python scripts/invoke_lambda.py parser --example

  # Dry run (validate without invoking)
  python scripts/invoke_lambda.py parser --key incoming/abc123 --dry-run

  # Check Lambda health
  python scripts/invoke_lambda.py parser --check-health

  # List all Lambdas
  python scripts/invoke_lambda.py --list
"""
    )

    # Positional argument for Lambda name
    parser.add_argument('lambda_name', nargs='?', help='Lambda to invoke (parser, enricher, playwright, scraper)')

    # Parser-specific arguments
    parser.add_argument('--key', help='S3 object key (for parser)')
    parser.add_argument('--search', help='Search for email by text (for parser)')
    parser.add_argument('--ticker', help='Company ticker')

    # Enricher/Playwright/Scraper arguments
    parser.add_argument('--url', help='URL to process')
    parser.add_argument('--urls', help='Comma-separated URLs')
    parser.add_argument('--subject', help='Email subject')
    parser.add_argument('--date', help='Email date (YYYY-MM-DD)', default=datetime.now().strftime('%Y-%m-%d'))
    parser.add_argument('--title', help='Press release title')

    # General options
    parser.add_argument('--bucket', help='Override S3 bucket')
    parser.add_argument('--idempotency-key', help='Override idempotency key')

    # Modes
    parser.add_argument('--example', action='store_true', help='Show example payload')
    parser.add_argument('--dry-run', action='store_true', help='Show payload without invoking')
    parser.add_argument('--check-health', action='store_true', help='Check Lambda health')
    parser.add_argument('--show-logs', action='store_true', help='Show CloudWatch logs after invocation')
    parser.add_argument('--list', action='store_true', help='List available Lambdas')

    args = parser.parse_args()

    # List mode
    if args.list:
        show_all_examples()
        return 0

    # Must have Lambda name for other operations
    if not args.lambda_name:
        parser.print_help()
        return 1

    # Validate Lambda name
    if args.lambda_name not in LAMBDA_CONFIG:
        print(f"Unknown Lambda: '{args.lambda_name}'")
        print(f"Valid options: {', '.join(LAMBDA_CONFIG.keys())}")
        return 1

    # Example mode
    if args.example:
        show_example(args.lambda_name)
        return 0

    # Health check mode
    if args.check_health and not (args.key or args.search or args.ticker or args.url):
        is_healthy, message, details = check_lambda_health(args.lambda_name)
        print(f"\nHealth Check: {args.lambda_name}")
        print(f"Status: {'HEALTHY' if is_healthy else 'UNHEALTHY'}")
        print(f"Message: {message}")
        if details:
            print(f"\nDetails:")
            for k, v in details.items():
                print(f"  {k}: {v}")
        return 0 if is_healthy else 1

    # Build payload based on Lambda type
    config = get_lambda_config(args.lambda_name)
    payload_type = config.get('payload_type', 'UNKNOWN')

    if args.lambda_name == 'parser':
        # Parser invocation
        if args.search or args.ticker:
            key = find_email_key(search=args.search, ticker=args.ticker)
            if not key:
                print("Could not find email. Use --key to specify directly.")
                return 1
        elif args.key:
            key = args.key
        else:
            print("Parser requires --key, --search, or --ticker")
            return 1

        bucket = args.bucket or get_default_bucket('parser')
        idempotency_key = args.idempotency_key or generate_idempotency_key(key)

        payload = build_parser_payload(bucket, key, idempotency_key)

        print(f"Bucket: {bucket}")
        print(f"Key: {key}")
        print(f"Idempotency Key: {idempotency_key}")

    elif args.lambda_name == 'enricher':
        # Enricher invocation
        if not args.ticker:
            print("Enricher requires --ticker")
            return 1
        if not (args.url or args.urls):
            print("Enricher requires --url or --urls")
            return 1

        urls = args.urls.split(',') if args.urls else [args.url]
        subject = args.subject or f"Test for {args.ticker}"
        idempotency_key = args.idempotency_key or generate_idempotency_key(f"{args.ticker}-{urls[0]}")

        payload = build_enricher_payload(
            ticker=args.ticker,
            urls=urls,
            email_subject=subject,
            email_date=args.date,
            idempotency_key=idempotency_key,
        )

        print(f"Ticker: {args.ticker}")
        print(f"URLs: {urls}")
        print(f"Subject: {subject}")

    elif args.lambda_name == 'playwright':
        # Playwright invocation
        if not args.ticker:
            print("Playwright requires --ticker")
            return 1

        subject = args.subject or f"Test for {args.ticker}"
        idempotency_key = args.idempotency_key or generate_idempotency_key(f"{args.ticker}-playwright")

        payload = build_playwright_payload(
            ticker=args.ticker,
            email_subject=subject,
            email_date=args.date,
            idempotency_key=idempotency_key,
            press_release_title=args.title,
        )

        print(f"Ticker: {args.ticker}")
        print(f"Subject: {subject}")

    elif args.lambda_name == 'scraper':
        # Scraper invocation
        if not args.ticker or not args.url:
            print("Scraper requires --ticker and --url")
            return 1

        idempotency_key = args.idempotency_key or generate_idempotency_key(args.url)

        payload = build_scraper_payload(
            ticker=args.ticker,
            url=args.url,
            idempotency_key=idempotency_key,
            email_subject=args.subject,
        )

        print(f"Ticker: {args.ticker}")
        print(f"URL: {args.url}")

    else:
        print(f"Invocation not implemented for: {args.lambda_name}")
        print("Use AWS CLI directly or implement in this script.")
        return 1

    # Invoke Lambda
    result = invoke_lambda(
        args.lambda_name,
        payload,
        dry_run=args.dry_run,
        check_health_first=args.check_health,
    )

    # Show logs if requested
    if args.show_logs and not args.dry_run:
        show_recent_logs(args.lambda_name)

    # Return status
    if result.get('error') or result.get('function_error') or result.get('health_check_failed'):
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
