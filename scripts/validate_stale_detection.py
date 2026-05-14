#!/usr/bin/env python3
"""
Stale Message Detection Validation Script
==========================================
Validates that Phase 1 implementation is correct across all Lambda handlers

Usage:
    python3 scripts/validate_stale_detection.py
"""

import sys
import os
from pathlib import Path

# ANSI colors
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'


def check_file_contains(file_path: str, patterns: list[str]) -> tuple[bool, list[str]]:
    """
    Check if file contains all required patterns

    Returns:
        (all_found, missing_patterns)
    """
    try:
        with open(file_path, 'r') as f:
            content = f.read()

        missing = []
        for pattern in patterns:
            if pattern not in content:
                missing.append(pattern)

        return len(missing) == 0, missing
    except FileNotFoundError:
        return False, patterns


def validate_lambda_handler(name: str, file_path: str) -> bool:
    """
    Validate a Lambda handler has stale detection implemented

    Returns:
        True if valid, False otherwise
    """
    required_patterns = [
        'from datetime import datetime, timezone, timedelta',
        'MAX_MESSAGE_AGE_MINUTES',
        'def is_message_stale',
        'queued_at = message_body.get(\'queued_at\')',
        'stale_dropped'
    ]

    print(f"\n{'='*70}")
    print(f"Validating: {name}")
    print(f"File: {file_path}")
    print(f"{'='*70}")

    all_found, missing = check_file_contains(file_path, required_patterns)

    if all_found:
        print(f"{GREEN}✓ All required patterns found{RESET}")
        return True
    else:
        print(f"{RED}✗ Missing patterns:{RESET}")
        for pattern in missing:
            print(f"  - {pattern}")
        return False


def validate_terraform(name: str, file_path: str) -> bool:
    """
    Validate Terraform config has MAX_MESSAGE_AGE_MINUTES

    Returns:
        True if valid, False otherwise
    """
    required_patterns = [
        'MAX_MESSAGE_AGE_MINUTES'
    ]

    print(f"\n{'='*70}")
    print(f"Validating Terraform: {name}")
    print(f"File: {file_path}")
    print(f"{'='*70}")

    all_found, missing = check_file_contains(file_path, required_patterns)

    if all_found:
        print(f"{GREEN}✓ MAX_MESSAGE_AGE_MINUTES found{RESET}")
        return True
    else:
        print(f"{RED}✗ MAX_MESSAGE_AGE_MINUTES not found{RESET}")
        return False


def main():
    """Main validation workflow"""
    print(f"\n{YELLOW}Stale Message Detection - Phase 1 Validation{RESET}")
    print("=" * 70)

    base_path = Path(__file__).parent.parent
    all_valid = True

    # Validate Lambda handlers
    lambdas = [
        ('Parser', 'infrastructure/lambdas/parser/handler.py'),
        ('Enricher', 'infrastructure/lambdas/enricher/handler.py'),
        ('Playwright Scraper', 'infrastructure/lambdas/playwright-scraper/handler.py'),
        ('Scraper', 'infrastructure/lambdas/scraper/handler.py')
    ]

    for name, path in lambdas:
        file_path = base_path / path
        if not validate_lambda_handler(name, str(file_path)):
            all_valid = False

    # Validate Terraform configs
    terraform_files = [
        ('Parser + Scraper', 'infrastructure/terraform/lambdas.tf'),
        ('Enricher', 'infrastructure/terraform/lambda-enricher.tf'),
        ('Playwright', 'infrastructure/terraform/lambda-playwright-scraper.tf')
    ]

    for name, path in terraform_files:
        file_path = base_path / path
        if not validate_terraform(name, str(file_path)):
            all_valid = False

    # Validate unit tests exist
    print(f"\n{'='*70}")
    print("Validating Unit Tests")
    print(f"{'='*70}")

    test_file = base_path / 'tests' / 'test_stale_message_detection.py'
    if test_file.exists():
        print(f"{GREEN}✓ Unit tests found: {test_file}{RESET}")
    else:
        print(f"{RED}✗ Unit tests not found: {test_file}{RESET}")
        all_valid = False

    # Validate documentation
    print(f"\n{'='*70}")
    print("Validating Documentation")
    print(f"{'='*70}")

    doc_file = base_path / 'docs' / 'STALE_MESSAGE_PREVENTION_PHASE1.md'
    if doc_file.exists():
        print(f"{GREEN}✓ Documentation found: {doc_file}{RESET}")
    else:
        print(f"{RED}✗ Documentation not found: {doc_file}{RESET}")
        all_valid = False

    # Final summary
    print(f"\n{'='*70}")
    print("Validation Summary")
    print(f"{'='*70}")

    if all_valid:
        print(f"{GREEN}✓ All validations passed!{RESET}")
        print("\nNext steps:")
        print("1. Run unit tests: python3 -m pytest tests/test_stale_message_detection.py -v")
        print("2. Build Lambda packages")
        print("3. Deploy to AWS")
        print("4. Apply Terraform changes")
        print("5. Integration testing")
        return 0
    else:
        print(f"{RED}✗ Some validations failed{RESET}")
        print("\nPlease fix the issues above before deployment")
        return 1


if __name__ == '__main__':
    sys.exit(main())
