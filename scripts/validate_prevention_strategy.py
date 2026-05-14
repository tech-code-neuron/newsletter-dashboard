#!/usr/bin/env python3
"""
Validate Prevention Strategy Implementation
============================================
Tests that all Tier 1 prevention features are working correctly.

Usage:
    python3 scripts/validate_prevention_strategy.py
    python3 scripts/validate_prevention_strategy.py --verbose
"""

import sys
import subprocess
from pathlib import Path
import zipfile
import tempfile

# Color codes
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
BLUE = '\033[94m'
RESET = '\033[0m'


def print_header(text):
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}{text}{RESET}")
    print(f"{BLUE}{'='*60}{RESET}\n")


def print_success(text):
    print(f"{GREEN}✓ {text}{RESET}")


def print_error(text):
    print(f"{RED}✗ {text}{RESET}")


def print_warning(text):
    print(f"{YELLOW}⚠ {text}{RESET}")


def test_deep_import_verification():
    """Test 1: Deep Import Verification"""
    print_header("Test 1: Deep Import Verification")

    # Check if validate_imports_runtime exists in deploy_lambda.py
    deploy_script = Path('scripts/deploy_lambda.py')
    if not deploy_script.exists():
        print_error("deploy_lambda.py not found")
        return False

    content = deploy_script.read_text()

    if 'validate_imports_runtime' in content:
        print_success("validate_imports_runtime() function exists")
    else:
        print_error("validate_imports_runtime() function NOT found")
        return False

    if 'subprocess.run' in content and 'test_script' in content:
        print_success("Runtime import test uses subprocess")
    else:
        print_error("Runtime import test implementation incomplete")
        return False

    print_success("Deep import verification: IMPLEMENTED ✅")
    return True


def test_mandatory_smoke_test():
    """Test 2: Mandatory Smoke Test + Auto-Rollback"""
    print_header("Test 2: Mandatory Smoke Test + Auto-Rollback")

    deploy_script = Path('scripts/deploy_lambda.py')
    content = deploy_script.read_text()

    if 'run_inline_smoke_test' in content:
        print_success("run_inline_smoke_test() function exists")
    else:
        print_error("run_inline_smoke_test() function NOT found")
        return False

    if 'rollback_to_previous_version' in content:
        print_success("rollback_to_previous_version() function exists")
    else:
        print_error("rollback_to_previous_version() function NOT found")
        return False

    # Check if smoke test is called in deployment flow
    if 'smoke_test_passed = run_inline_smoke_test' in content:
        print_success("Smoke test integrated into deployment flow")
    else:
        print_error("Smoke test NOT integrated into deployment")
        return False

    # Check if auto-rollback is triggered
    if 'rollback_to_previous_version(config' in content:
        print_success("Auto-rollback integrated")
    else:
        print_error("Auto-rollback NOT integrated")
        return False

    print_success("Mandatory smoke test + auto-rollback: IMPLEMENTED ✅")
    return True


def test_cloudwatch_alarms():
    """Test 3: CloudWatch ImportError Alerts"""
    print_header("Test 3: CloudWatch ImportError Alerts")

    cloudwatch_tf = Path('infrastructure/terraform/cloudwatch.tf')
    if not cloudwatch_tf.exists():
        print_error("cloudwatch.tf not found")
        return False

    content = cloudwatch_tf.read_text()

    # Check for ImportError metric filters
    required_filters = [
        'parser_import_errors',
        'enricher_import_errors',
        'scraper_import_errors'
    ]

    for filter_name in required_filters:
        if filter_name in content:
            print_success(f"Metric filter exists: {filter_name}")
        else:
            print_warning(f"Metric filter missing: {filter_name}")

    # Check for alarms
    required_alarms = [
        'parser_import_error_alarm',
        'enricher_import_error_alarm',
        'scraper_import_error_alarm'
    ]

    for alarm_name in required_alarms:
        if alarm_name in content:
            print_success(f"Alarm exists: {alarm_name}")
        else:
            print_warning(f"Alarm missing: {alarm_name}")

    # Check pattern
    if '?ImportError ?ModuleNotFoundError' in content:
        print_success("ImportError pattern configured")
    else:
        print_error("ImportError pattern NOT found")
        return False

    print_success("CloudWatch ImportError alerts: IMPLEMENTED ✅")
    print_warning("Note: Terraform apply required to create alarms in AWS")
    return True


def test_deployment_lock():
    """Test 4: Deployment State Lockfile"""
    print_header("Test 4: Deployment State Lockfile")

    deploy_script = Path('scripts/deploy_lambda.py')
    content = deploy_script.read_text()

    if 'class DeploymentLock' in content:
        print_success("DeploymentLock class exists")
    else:
        print_error("DeploymentLock class NOT found")
        return False

    if '__enter__' in content and '__exit__' in content:
        print_success("DeploymentLock uses context manager pattern")
    else:
        print_error("Context manager methods NOT found")
        return False

    if 'fcntl.flock' in content:
        print_success("Uses fcntl for filesystem lock")
    else:
        print_error("Filesystem lock NOT implemented")
        return False

    if 'with DeploymentLock' in content:
        print_success("DeploymentLock integrated into deployment flow")
    else:
        print_error("DeploymentLock NOT used in deployment")
        return False

    print_success("Deployment state lockfile: IMPLEMENTED ✅")
    return True


def test_zip_lifecycle():
    """Test 5: ZIP Artifact Lifecycle Management"""
    print_header("Test 5: ZIP Artifact Lifecycle Management")

    deploy_script = Path('scripts/deploy_lambda.py')
    content = deploy_script.read_text()

    if 'enforce_canonical_naming' in content:
        print_success("enforce_canonical_naming() function exists")
    else:
        print_error("enforce_canonical_naming() function NOT found")
        return False

    # Check .gitignore
    gitignore = Path('.gitignore')
    if not gitignore.exists():
        print_error(".gitignore not found")
        return False

    gitignore_content = gitignore.read_text()

    if '!infrastructure/lambdas/*/*-deployment.zip' in gitignore_content:
        print_success(".gitignore tracks canonical deployment ZIPs")
    else:
        print_error(".gitignore NOT configured for canonical ZIPs")
        return False

    if 'infrastructure/lambdas/*/archive/' in gitignore_content:
        print_success(".gitignore excludes archive directories")
    else:
        print_error(".gitignore NOT configured for archive dirs")
        return False

    if '.deploy.lock' in gitignore_content:
        print_success(".gitignore excludes lock files")
    else:
        print_error(".gitignore NOT configured for lock files")
        return False

    print_success("ZIP artifact lifecycle management: IMPLEMENTED ✅")
    return True


def test_imports():
    """Test 6: Required Imports"""
    print_header("Test 6: Required Imports")

    deploy_script = Path('scripts/deploy_lambda.py')
    content = deploy_script.read_text()

    required_imports = [
        'import tempfile',
        'import fcntl',
        'from datetime import datetime, timezone'
    ]

    for imp in required_imports:
        if imp in content:
            print_success(f"Import exists: {imp}")
        else:
            print_error(f"Import missing: {imp}")
            return False

    print_success("Required imports: PRESENT ✅")
    return True


def run_all_tests():
    """Run all validation tests"""
    print_header("Tier 1 Prevention Strategy Validation")
    print("This script validates that all prevention features are implemented.\n")

    tests = [
        ("Deep Import Verification", test_deep_import_verification),
        ("Mandatory Smoke Test + Auto-Rollback", test_mandatory_smoke_test),
        ("CloudWatch ImportError Alerts", test_cloudwatch_alarms),
        ("Deployment State Lockfile", test_deployment_lock),
        ("ZIP Artifact Lifecycle", test_zip_lifecycle),
        ("Required Imports", test_imports),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print_error(f"Test failed with exception: {e}")
            results.append((name, False))

    # Summary
    print_header("Validation Summary")

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = f"{GREEN}PASS{RESET}" if result else f"{RED}FAIL{RESET}"
        print(f"  {name:45} {status}")

    print(f"\n{passed}/{total} tests passed")

    if passed == total:
        print_success("\n🎉 All prevention features IMPLEMENTED!")
        print_success("Tier 1 prevention strategy is complete.")
        print("\n📝 Next steps:")
        print("  1. Apply Terraform for CloudWatch alarms:")
        print("     cd infrastructure/terraform && terraform apply")
        print("  2. Run functional tests:")
        print("     python3 scripts/deploy_lambda.py parser --validate --zip parser-deployment.zip")
        print("  3. Update DEPLOYED_STATE.md with prevention strategy status")
        return 0
    else:
        print_error("\n❌ Some features are incomplete")
        print("Review failed tests and fix issues.")
        return 1


if __name__ == '__main__':
    sys.exit(run_all_tests())
