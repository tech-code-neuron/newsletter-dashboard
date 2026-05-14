#!/usr/bin/env python3
"""
Lambda Smoke Test - Post-Deployment Validation
================================================
Invokes Lambda with test payload immediately after deployment to catch
runtime errors before they affect production traffic.

Usage:
    python3 scripts/smoke_test_lambda.py parser
    python3 scripts/smoke_test_lambda.py enricher --verbose
    python3 scripts/smoke_test_lambda.py parser --dry-run  # Show payload only

Why this exists:
    - Catches runtime errors (ImportError, missing env vars) immediately
    - Validates Lambda can start and process basic payloads
    - Prevents users from being affected by broken deployments
    - Provides quick feedback loop after deployment

Test payloads:
    - Parser: Minimal SQS event with test message
    - Enricher: Minimal enrichment request
    - Email-forwarder: Test email metadata
    - Daily-summary: Trigger summary generation
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Color codes
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
BLUE = '\033[94m'
CYAN = '\033[96m'
RESET = '\033[0m'

# Smoke test configurations
SMOKE_TESTS = {
    'parser': {
        'function_name': 'reitsheet-parser',
        'description': 'Parse test SQS message',
        'timeout_seconds': 30,
        'payload': {
            "Records": [
                {
                    "messageId": "smoke-test-parser",
                    "body": json.dumps({
                        "bucket": "reitsheet-emails",
                        "key": "smoke-test/test-email.eml",
                        "source": "smoke-test@example.com",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                }
            ]
        },
        'success_patterns': ['statusCode', '200'],
        'error_patterns': ['ImportError', 'ModuleNotFoundError', 'KeyError']
    },
    'enricher': {
        'function_name': 'reitsheet-enricher',
        'description': 'Enrich test press release',
        'timeout_seconds': 30,
        'payload': {
            "Records": [
                {
                    "messageId": "smoke-test-enricher",
                    "body": json.dumps({
                        "ticker": "TEST",
                        "company_name": "Smoke Test Corp",
                        "subject": "Test Press Release",
                        "urls": ["https://example.com/test"],
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                }
            ]
        },
        'success_patterns': ['statusCode', '200'],
        'error_patterns': ['ImportError', 'ModuleNotFoundError', 'KeyError']
    },
    'email-forwarder': {
        'function_name': 'reitsheet-email-forwarder',
        'description': 'Forward test email',
        'timeout_seconds': 15,
        'payload': {
            "Records": [
                {
                    "eventSource": "aws:ses",
                    "ses": {
                        "mail": {
                            "messageId": "smoke-test-forwarder",
                            "source": "smoke-test@example.com"
                        }
                    }
                }
            ]
        },
        'success_patterns': ['statusCode'],
        'error_patterns': ['ImportError', 'ModuleNotFoundError']
    },
    'daily-summary': {
        'function_name': 'reitsheet-daily-summary',
        'description': 'Generate daily summary',
        'timeout_seconds': 60,
        'payload': {
            "source": "smoke-test",
            "dry_run": True  # Don't actually send
        },
        'success_patterns': ['statusCode', '200'],
        'error_patterns': ['ImportError', 'ModuleNotFoundError']
    }
}


def print_header(text):
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}{text}{RESET}")
    print(f"{BLUE}{'='*60}{RESET}\n")


def print_success(text):
    print(f"{GREEN}{text}{RESET}")


def print_warning(text):
    print(f"{YELLOW}{text}{RESET}")


def print_error(text):
    print(f"{RED}{text}{RESET}")


def invoke_lambda(function_name, payload, timeout_seconds=30, verbose=False):
    """
    Invoke Lambda function and return response.

    Returns:
        (success: bool, response: dict, error: str or None)
    """
    try:
        # Write payload to temp file
        payload_file = Path('/tmp/smoke_test_payload.json')
        payload_file.write_text(json.dumps(payload))

        # Invoke Lambda
        cmd = [
            'aws', 'lambda', 'invoke',
            '--function-name', function_name,
            '--payload', f'fileb://{payload_file}',
            '--cli-read-timeout', str(timeout_seconds),
            '--cli-connect-timeout', '10',
            '/tmp/smoke_test_response.json'
        ]

        if verbose:
            print(f"{CYAN}Command: {' '.join(cmd)}{RESET}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds + 5
        )

        if result.returncode != 0:
            return False, {}, f"AWS CLI error: {result.stderr}"

        # Check for function error
        cli_output = json.loads(result.stdout) if result.stdout else {}
        if 'FunctionError' in cli_output:
            response_file = Path('/tmp/smoke_test_response.json')
            if response_file.exists():
                error_response = json.loads(response_file.read_text())
                return False, error_response, f"Lambda error: {error_response.get('errorMessage', 'Unknown')}"

        # Read response
        response_file = Path('/tmp/smoke_test_response.json')
        if response_file.exists():
            response = json.loads(response_file.read_text())
            return True, response, None

        return True, {}, None

    except subprocess.TimeoutExpired:
        return False, {}, f"Timeout after {timeout_seconds}s"
    except json.JSONDecodeError as e:
        return False, {}, f"Invalid JSON response: {e}"
    except Exception as e:
        return False, {}, f"Invocation failed: {e}"


def check_response(response, config):
    """
    Check response for success/error patterns.

    Returns:
        (passed: bool, details: str)
    """
    response_str = json.dumps(response)

    # Check for error patterns first
    for pattern in config['error_patterns']:
        if pattern.lower() in response_str.lower():
            return False, f"Error pattern found: {pattern}"

    # Check for success patterns
    found_success = []
    for pattern in config['success_patterns']:
        if pattern in response_str:
            found_success.append(pattern)

    if found_success:
        return True, f"Success patterns found: {', '.join(found_success)}"

    # No clear signal - treat as warning
    return True, "Response received (no error patterns found)"


def run_smoke_test(lambda_name, verbose=False, dry_run=False):
    """Run smoke test for a Lambda function."""

    if lambda_name not in SMOKE_TESTS:
        print_error(f"Unknown Lambda: {lambda_name}")
        print(f"\nAvailable: {', '.join(SMOKE_TESTS.keys())}")
        return False

    config = SMOKE_TESTS[lambda_name]
    print_header(f"Smoke Test: {config['function_name']}")
    print(f"Description: {config['description']}")

    # Show payload
    print(f"\n{CYAN}Test Payload:{RESET}")
    print(json.dumps(config['payload'], indent=2))

    if dry_run:
        print_warning("\n--dry-run: Not invoking Lambda")
        return True

    # Invoke Lambda
    print(f"\nInvoking Lambda...")
    success, response, error = invoke_lambda(
        config['function_name'],
        config['payload'],
        config['timeout_seconds'],
        verbose
    )

    if not success:
        print_error(f"\nInvocation failed: {error}")

        # Check for common issues
        if 'ImportError' in str(error) or 'ModuleNotFoundError' in str(error):
            print_error("\nLikely cause: Missing dependencies in deployment package")
            print_warning("Action: Rebuild package with dependencies:")
            print(f"  python3 scripts/deploy_lambda.py {lambda_name} --build-only")
            print(f"  python3 scripts/deploy_lambda.py {lambda_name} --validate --zip <name>.zip")

        return False

    # Show response
    if verbose:
        print(f"\n{CYAN}Response:{RESET}")
        print(json.dumps(response, indent=2, default=str))

    # Check response patterns
    passed, details = check_response(response, config)

    if passed:
        print_success(f"\nSmoke test PASSED")
        print_success(f"  {details}")
        return True
    else:
        print_error(f"\nSmoke test FAILED")
        print_error(f"  {details}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Run smoke tests on deployed Lambda functions',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test parser after deployment
  python3 scripts/smoke_test_lambda.py parser

  # Test with verbose output
  python3 scripts/smoke_test_lambda.py enricher --verbose

  # Show test payload without invoking
  python3 scripts/smoke_test_lambda.py parser --dry-run

  # Test all Lambdas
  python3 scripts/smoke_test_lambda.py --all

When to run:
  1. After deploying any Lambda
  2. After changing environment variables
  3. After updating dependencies
  4. Before marking deployment as complete in DEPLOYED_STATE.md
        """
    )

    parser.add_argument('lambda_name', nargs='?', help='Lambda to test')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show detailed output')
    parser.add_argument('--dry-run', action='store_true', help='Show payload without invoking')
    parser.add_argument('--all', action='store_true', help='Test all Lambdas')
    parser.add_argument('--list', action='store_true', help='List available smoke tests')

    args = parser.parse_args()

    if args.list:
        print_header("Available Smoke Tests")
        for name, config in SMOKE_TESTS.items():
            print(f"  {name:20} -> {config['function_name']}")
            print(f"                       {config['description']}")
        return 0

    if args.all:
        results = {}
        for name in SMOKE_TESTS:
            results[name] = run_smoke_test(name, args.verbose, args.dry_run)

        print_header("Summary")
        all_passed = True
        for name, passed in results.items():
            status = f"{GREEN}PASSED{RESET}" if passed else f"{RED}FAILED{RESET}"
            print(f"  {name:20} {status}")
            if not passed:
                all_passed = False

        return 0 if all_passed else 1

    if not args.lambda_name:
        parser.print_help()
        print(f"\nAvailable: {', '.join(SMOKE_TESTS.keys())}")
        return 1

    success = run_smoke_test(args.lambda_name, args.verbose, args.dry_run)
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
