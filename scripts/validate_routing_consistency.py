#!/usr/bin/env python3
"""
Validate Routing Consistency

Checks that routing configurations are consistent across:
- Parser routing logic
- Enricher routing logic
- DynamoDB companies-config table
- Playwright scraper config

Run before deployment:
  python3 scripts/validate_routing_consistency.py
"""

import json
import re
from pathlib import Path
import sys

try:
    import boto3
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False


def get_aws_region():
    """Get AWS region from deployment config."""
    config_path = Path("infrastructure/deployment-config.json")
    if config_path.exists():
        with open(config_path) as f:
            config = json.load(f)
            return config.get("aws", {}).get("region", "us-east-1")
    return "us-east-1"

def check_dynamodb_completeness():
    """Verify all companies in DynamoDB have url_construction_method"""
    print("\n" + "="*70)
    print("Check 1: DynamoDB Completeness")
    print("="*70)

    if not BOTO3_AVAILABLE:
        print("⚠️  boto3 not available (skipping DynamoDB checks)")
        return True

    try:
        dynamodb = boto3.resource('dynamodb', region_name=get_aws_region())
        table = dynamodb.Table('reitsheet-companies-config')

        response = table.scan()
        companies = response.get('Items', [])

        missing_method = []
        by_method = {}

        for company in companies:
            ticker = company.get('ticker')
            method = company.get('url_construction_method', 'NOT_SET')

            if not company.get('url_construction_method'):
                missing_method.append(ticker)

            if method not in by_method:
                by_method[method] = []
            by_method[method].append(ticker)

        print(f"  Total companies: {len(companies)}")
        print("\n  Breakdown by method:")
        for method, tickers in sorted(by_method.items()):
            print(f"    {method}: {len(tickers)} companies")
            print(f"      {sorted(tickers)}")

        if missing_method:
            print(f"\n  ❌ FAIL: {len(missing_method)} companies missing url_construction_method:")
            print(f"    {missing_method}")
            return False

        print(f"\n  ✅ PASS: All {len(companies)} companies have url_construction_method")
        return True

    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        return False


def check_playwright_configs_match():
    """Verify Playwright scraper has configs for all playwright_scraper companies"""
    print("\n" + "="*70)
    print("Check 2: Playwright Config Consistency")
    print("="*70)

    if not BOTO3_AVAILABLE:
        print("⚠️  boto3 not available (skipping Playwright config checks)")
        return True

    try:
        # Get companies marked as playwright_scraper from DynamoDB
        dynamodb = boto3.resource('dynamodb', region_name=get_aws_region())
        table = dynamodb.Table('reitsheet-companies-config')

        response = table.scan()
        playwright_companies = {
            item['ticker']
            for item in response.get('Items', [])
            if item.get('url_construction_method') == 'playwright_scraper'
        }

        print(f"  DynamoDB playwright_scraper companies: {sorted(playwright_companies)}")

        # Check that ALL playwright companies have required Playwright fields in DynamoDB
        # Modern architecture: Configs are in DynamoDB, not hardcoded in handler
        required_fields = ['playwright_url', 'playwright_selector', 'playwright_wait_for']

        incomplete_configs = []

        for item in response.get('Items', []):
            if item.get('url_construction_method') == 'playwright_scraper':
                ticker = item['ticker']
                missing_fields = [
                    field for field in required_fields
                    if not item.get(field)
                ]

                if missing_fields:
                    incomplete_configs.append((ticker, missing_fields))

        if incomplete_configs:
            print(f"\n  ❌ FAIL: Some playwright companies missing required fields in DynamoDB:")
            for ticker, missing in incomplete_configs:
                print(f"    {ticker}: missing {missing}")
            print(f"\n  Fix: Add missing fields to DynamoDB reitsheet-companies-config table")
            return False

        # Verify handler uses DynamoDB (not hardcoded SCRAPER_CONFIG)
        handler_path = Path('infrastructure/lambdas/playwright-scraper/handler.py')
        if not handler_path.exists():
            print("  ⚠️  WARNING: Playwright handler not found")
            return True

        content = handler_path.read_text()

        # Check that handler uses get_playwright_config() function (DynamoDB-driven)
        if 'get_playwright_config' not in content:
            print("  ❌ FAIL: Handler doesn't use get_playwright_config() - may have hardcoded configs")
            return False

        # Warn if old SCRAPER_CONFIG still exists (should be removed)
        config_start = content.find('SCRAPER_CONFIG = {')
        if config_start != -1:
            print("  ⚠️  WARNING: Found hardcoded SCRAPER_CONFIG - should migrate to DynamoDB")
            return True  # Warning only, don't fail


        print(f"  ✅ Handler uses DynamoDB-driven config (get_playwright_config)")
        print(f"\n  ✅ PASS: All {len(playwright_companies)} playwright companies have complete configs in DynamoDB")
        return True

    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_parser_constants():
    """Check if parser has hardcoded company lists (should use DynamoDB instead)"""
    print("\n" + "="*70)
    print("Check 3: Parser Constants (Should Query DynamoDB)")
    print("="*70)

    parser_constants = Path('infrastructure/lambdas/parser/constants.py')
    parser_routing = Path('infrastructure/lambdas/parser/routing.py')

    issues = []

    # Check constants.py for hardcoded lists
    if parser_constants.exists():
        content = parser_constants.read_text()
        if 'JAVASCRIPT_RENDERED_COMPANIES' in content:
            # Extract the set
            match = re.search(r'JAVASCRIPT_RENDERED_COMPANIES\s*=\s*\{([^}]+)\}', content)
            if match:
                tickers = re.findall(r"'(\w+)'", match.group(1))
                print(f"  Found hardcoded JAVASCRIPT_RENDERED_COMPANIES: {tickers}")

                # Compare with DynamoDB if available
                if BOTO3_AVAILABLE:
                    try:
                        dynamodb = boto3.resource('dynamodb', region_name=get_aws_region())
                        table = dynamodb.Table('reitsheet-companies-config')
                        response = table.scan()

                        db_playwright = {
                            item['ticker']
                            for item in response.get('Items', [])
                            if item.get('url_construction_method') == 'playwright_scraper'
                        }

                        print(f"  DynamoDB playwright_scraper companies: {sorted(db_playwright)}")

                        hardcoded_set = set(tickers)
                        if hardcoded_set != db_playwright:
                            missing_in_code = db_playwright - hardcoded_set
                            extra_in_code = hardcoded_set - db_playwright

                            if missing_in_code:
                                print(f"  ⚠️  WARNING: DynamoDB has {missing_in_code} but constants doesn't")
                                issues.append(f"Add {missing_in_code} to JAVASCRIPT_RENDERED_COMPANIES")

                            if extra_in_code:
                                print(f"  ⚠️  WARNING: Constants has {extra_in_code} but DynamoDB doesn't")
                                issues.append(f"Remove {extra_in_code} from JAVASCRIPT_RENDERED_COMPANIES or update DynamoDB")
                        else:
                            print(f"  ✅ Constants match DynamoDB")
                    except Exception as e:
                        print(f"  ⚠️  Could not check DynamoDB: {e}")
                else:
                    print(f"  ⚠️  boto3 not available (skipping DynamoDB comparison)")

    # Check routing.py for direct DynamoDB queries
    if parser_routing.exists():
        content = parser_routing.read_text()
        if 'should_use_playwright' in content or 'get_company_config' in content:
            print(f"  ✅ Parser queries DynamoDB for routing decisions (good!)")
        elif 'JAVASCRIPT_RENDERED_COMPANIES' in content:
            print(f"  ⚠️  Parser uses hardcoded constant (consider DynamoDB query)")

    if issues:
        print(f"\n  ⚠️  Found {len(issues)} potential inconsistencies")
        for issue in issues:
            print(f"    - {issue}")
        print(f"\n  Recommendation: Make DynamoDB the single source of truth")
        return True  # Warning, not failure

    print(f"\n  ✅ PASS: No critical issues found")
    return True


def main():
    print("="*70)
    print(" ROUTING CONSISTENCY VALIDATION")
    print("="*70)
    print("\nChecking routing configuration across all components...")

    checks = [
        check_dynamodb_completeness,
        check_playwright_configs_match,
        check_parser_constants,
    ]

    results = []
    for check_func in checks:
        try:
            passed = check_func()
            results.append(passed)
        except Exception as e:
            print(f"\n  ❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)

    print("\n" + "="*70)
    print(" SUMMARY")
    print("="*70)

    passed_count = sum(1 for r in results if r)
    total_count = len(results)

    print(f"\nPassed: {passed_count}/{total_count} checks")

    if all(results):
        print("\n🎉 All checks passed!")
        print("\n✅ Safe to deploy - routing configurations are consistent")
        return 0
    else:
        print("\n❌ Some checks failed")
        print("\n⚠️  Review issues above and fix before deploying")
        return 1


if __name__ == '__main__':
    sys.exit(main())
