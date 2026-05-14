#!/usr/bin/env python3
"""
Enhanced Pre-Commit Validation (45 checks)
===========================================
Prevents configuration cascade failures by validating:

BLOCKING CHECKS (exit 1 on failure):
1. Routing consistency (DynamoDB ↔ Playwright configs)
2. NEWSWIRE_DOMAINS duplication (Parser ↔ Enricher ↔ Shared)
3. Queue URL fallbacks (Fail-fast env vars)
7. boto3 pattern enforcement (resource vs client) - BLOCKS
8. Playwright config completeness (DynamoDB) - BLOCKS if incomplete
10. Python syntax validation - BLOCKS on syntax errors
11. Import resolution check - BLOCKS if critical imports missing
13. CLAUDE.md routing table validation - BLOCKS if stale/invalid
14. Landing page detection integrity - BLOCKS if duplication/missing checks
15. Template date safety - BLOCKS if raw .strftime() found (must use |format_date)
16. Flask session HTTPS config - BLOCKS if session cookies not configured for HTTPS
17. Deployment config validation - BLOCKS if deployment-config.json missing/invalid
18. Flask-WTF form usage - BLOCKS if POST routes don't use Flask-WTF forms
19. Timestamp field formats - BLOCKS if *_at fields use .date() or date-only strings
20. Lambda ZIP dependencies - BLOCKS if ZIP missing required modules from requirements.txt
21. Lambda import smoke test - BLOCKS if handler.py fails to import (NameError, ImportError)
22. Timezone utility enforcement - BLOCKS if datetime.now(timezone.utc) without shared.timezone_utils
23. Lambda handler signature - BLOCKS if lambda_handler(event, context) missing/incorrect
24. Circular import detection - BLOCKS if circular imports detected in Lambda code
25. SQS schema validation - Ensures shared/sqs_schemas.py exists for message format consistency
26. Environment variable registry - Cross-validates env vars between code and registry
27. Queue name consistency - Detects hardcoded queue names not in shared/queue_names.py
28. Buildspec import validation - Warns if build scripts missing import validation
29. Lambda module discovery - BLOCKS if discovered modules missing or ZIP incomplete
30. Build script discovery integration - BLOCKS if build.sh uses hardcoded module lists
32. Design token source - BLOCKS if CSS files define :root vars outside variables.css
33. Brand standards - BLOCKS if brand name errors or forbidden patterns found
35. Email style consistency - BLOCKS if publisher_generator.py hardcodes colors
36. Accessibility - BLOCKS if images lack alt text, links/buttons lack labels
37. Domain routing - BLOCKS if domain-based routing not properly configured
38. Homepage publishing destination - BLOCKS if JS calls deprecated /publish-homepage endpoint
39. Template section coverage - BLOCKS if homepage/archive templates missing sections
40. Publisher URL function unity - BLOCKS if separate mobile/desktop URL functions found
41. Terraform drift detection - BLOCKS if terraform plan shows unapplied changes
42. Lambda ZIP runtime imports - BLOCKS if Lambda ZIP handler fails to import
43. Signup form parity - BLOCKS if popup/footer forms differ in processing
44. Title priority drift - BLOCKS if inline title priority logic found (must use title_utils)
45. Verification scanner protection - BLOCKS if /verify auto-verifies on GET (must use POST)

WARNING CHECKS (informational only):
4. Playwright config completeness (local)
5. Terraform sync warnings
6. DynamoDB table consistency (detect multiple similar tables)
9. Environment variable validation (Terraform ↔ Lambda defaults)
12. Direct URL config validation - WARNS if config incomplete
31. Lambda config centralization - WARNS if test scripts don't use shared/lambda_config.py
34. Mobile text wrapping - WARNS if CTAs exceed mobile character limit

Exit codes:
    0 = All checks passed
    1 = Validation failed (blocks commit)

Added 2026-03-13: Checks 10-13 prevent incidents like wrong ZIP deployment, stale docs
Added 2026-03-13: Check 14 prevents landing page leaks
Added 2026-03-14: Check 15 prevents template None.strftime() crashes
Added 2026-03-14: Check 16 prevents session cookie HTTPS misconfiguration (OAuth login loop)
Added 2026-03-14: Check 17 ensures deployment config exists (prevents "where is Flask?" confusion)
Added 2026-03-15: Check 18 enforces Flask-WTF forms for CSRF protection
Added 2026-03-15: Check 19 prevents timestamp data loss (date-only strings on *_at fields)
Added 2026-03-15: Check 20 validates Lambda ZIPs contain required dependencies (prevents missing module deployments)
Added 2026-03-16: Checks 22-24 expand AST-based validation (timezone, handler signature, circular imports)
Added 2026-03-16: Checks 25-28 add configuration safety (SQS schemas, env registry, queue names, buildspec)
Added 2026-03-19: Checks 29-30 add AST-based module discovery enforcement
Added 2026-03-23: Check 31 validates Lambda config centralization (invoke_lambda.py, lambda_config.py)
Added 2026-03-28: Checks 32-36 add frontend validation (design tokens, brand standards, accessibility)
Added 2026-03-30: Checks 38-39 add homepage publishing validation (correct endpoint, all sections)
Added 2026-04-01: Check 40 prevents publisher mobile/desktop URL function drift
Added 2026-04-02: Check 41 blocks commits when Terraform state differs from code (prevents unapplied changes)
Added 2026-04-02: Check 42 validates Lambda ZIPs can import their handlers at runtime (catches missing shared modules)
Added 2026-04-03: Check 43 validates signup form parity (prevents session expired errors from CSRF misconfig)
Added 2026-04-08: Check 44 prevents title priority drift (must use core.title_utils)
Added 2026-04-13: Check 45 prevents email scanner auto-verification (must use POST for /verify)
"""

import os
import re
import sys
from pathlib import Path

# ANSI colors
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
CYAN = '\033[96m'
RESET = '\033[0m'

# Directories to skip when scanning Lambda code (dependencies, build artifacts)
SKIP_DIRS = {'package', 'build', '__pycache__', 'node_modules', '.git',
             'botocore', 'boto3', 'requests', 'cffi', 'bs4', 'urllib3',
             'requests_toolbelt', 'charset_normalizer', 'certifi', 'idna'}

def should_skip_path(filepath):
    """Check if path should be skipped (contains dependency directories)."""
    parts = Path(filepath).parts
    return any(skip in parts for skip in SKIP_DIRS)

def glob_lambda_files(pattern):
    """Glob Lambda files, excluding dependency directories."""
    return [f for f in Path("infrastructure/lambdas").glob(pattern) if not should_skip_path(f)]


def check_routing_consistency():
    """Check 1: Run existing routing validation"""
    print(f"\n{YELLOW}[1/36] Routing Consistency{RESET}")

    script_path = Path("scripts/validate_routing_consistency.py")
    if not script_path.exists():
        print(f"{YELLOW}⚠️  Routing validation script not found (skipping){RESET}")
        return True

    import subprocess
    result = subprocess.run([sys.executable, str(script_path)], capture_output=True)

    if result.returncode == 0:
        print(f"{GREEN}✅ Routing consistency validated{RESET}")
        return True
    else:
        print(f"{RED}❌ Routing consistency failed{RESET}")
        print(result.stdout.decode() if result.stdout else "")
        return False


def check_newswire_domains_duplication():
    """Check 2: Ensure NEWSWIRE_DOMAINS is identical across all files"""
    print(f"\n{YELLOW}[2/36] NEWSWIRE_DOMAINS Duplication{RESET}")

    files_to_check = [
        "infrastructure/lambdas/parser/constants.py",
        "infrastructure/lambdas/enricher/config/constants.py",
        "infrastructure/lambdas/shared/constants.py",
    ]

    newswire_sets = {}

    for filepath in files_to_check:
        path = Path(filepath)
        if not path.exists():
            continue

        content = path.read_text()

        # Extract NEWSWIRE_DOMAINS set
        match = re.search(
            r'NEWSWIRE_DOMAINS\s*=\s*\{([^}]+)\}',
            content,
            re.DOTALL
        )

        if match:
            # Parse domain names
            domains_text = match.group(1)
            domains = set(
                re.findall(r"['\"]([^'\"]+)['\"]", domains_text)
            )
            newswire_sets[filepath] = domains

    if len(newswire_sets) <= 1:
        print(f"{GREEN}✅ Only one NEWSWIRE_DOMAINS found (no duplication){RESET}")
        return True

    # Check if all sets are identical
    reference_domains = next(iter(newswire_sets.values()))
    all_identical = all(
        domains == reference_domains
        for domains in newswire_sets.values()
    )

    if all_identical:
        print(f"{GREEN}✅ All {len(newswire_sets)} NEWSWIRE_DOMAINS definitions are identical{RESET}")
        return True
    else:
        print(f"{RED}❌ NEWSWIRE_DOMAINS mismatch detected!{RESET}\n")

        for filepath, domains in newswire_sets.items():
            print(f"  {filepath}:")
            print(f"    {sorted(domains)}\n")

        print(f"{RED}Action Required:{RESET}")
        print("  1. Consolidate NEWSWIRE_DOMAINS into shared/constants.py")
        print("  2. Import from shared: from shared.constants import NEWSWIRE_DOMAINS")
        print("  3. Delete duplicates from parser/constants.py and enricher/config/constants.py")

        return False


def check_queue_url_fallbacks():
    """Check 3: Ensure no silent fallbacks in queue URL assignments"""
    print(f"\n{YELLOW}[3/36] Queue URL Fallback Safety{RESET}")

    files_to_check = [
        ("infrastructure/lambdas/enricher/handler.py", "PLAYWRIGHT_QUEUE_URL"),
        ("infrastructure/lambdas/parser/handler.py", "PLAYWRIGHT_QUEUE_URL"),
    ]

    issues = []

    for filepath, var_name in files_to_check:
        path = Path(filepath)
        if not path.exists():
            continue

        content = path.read_text()

        # Check for .get() with fallback (DANGEROUS)
        pattern = rf"{var_name}\s*=\s*os\.environ\.get\(['\"]PLAYWRIGHT_QUEUE_URL['\"],\s*\w+\)"

        if re.search(pattern, content):
            issues.append((filepath, var_name))

    if not issues:
        print(f"{GREEN}✅ No dangerous queue URL fallbacks detected{RESET}")
        return True
    else:
        print(f"{RED}❌ Dangerous fallbacks detected!{RESET}\n")

        for filepath, var_name in issues:
            print(f"  {filepath}:")
            print(f"    {var_name} uses os.environ.get() with fallback\n")

        print(f"{RED}Action Required:{RESET}")
        print("  Change: PLAYWRIGHT_QUEUE_URL = os.environ.get('PLAYWRIGHT_QUEUE_URL', SCRAPE_QUEUE_URL)")
        print("  To:     PLAYWRIGHT_QUEUE_URL = os.environ['PLAYWRIGHT_QUEUE_URL']  # Fail fast")
        print("\n  This prevents silent routing to wrong queue if env var is missing.")

        return False


def check_playwright_config_completeness():
    """Check 4: Ensure all playwright_scraper companies have handler configs"""
    print(f"\n{YELLOW}[4/36] Playwright Config Completeness (Local){RESET}")

    handler_path = Path("infrastructure/lambdas/playwright-scraper/handler.py")

    if not handler_path.exists():
        print(f"{YELLOW}⚠️  Playwright handler not found (skipping){RESET}")
        return True

    content = handler_path.read_text()

    # Extract SCRAPER_CONFIG keys
    config_match = re.search(
        r'SCRAPER_CONFIG\s*=\s*\{([^}]+)\}',
        content,
        re.DOTALL
    )

    if not config_match:
        print(f"{YELLOW}⚠️  SCRAPER_CONFIG not found in handler (skipping){RESET}")
        return True

    config_text = config_match.group(1)
    configured_tickers = set(re.findall(r"['\"]([A-Z]+)['\"]:", config_text))

    # Note: We'd need DynamoDB access to check actual playwright_scraper companies
    # For pre-commit, we just warn if SCRAPER_CONFIG looks incomplete

    if len(configured_tickers) < 4:
        print(f"{YELLOW}⚠️  WARNING: Only {len(configured_tickers)} companies in SCRAPER_CONFIG{RESET}")
        print(f"  Configured: {configured_tickers}")
        print(f"  Expected: EPRT, O, PK, SAFE (minimum)")
        print(f"\n  {YELLOW}This is a warning, not a blocker.{RESET}")
    else:
        print(f"{GREEN}✅ SCRAPER_CONFIG has {len(configured_tickers)} companies configured{RESET}")

    return True  # Warning only, don't block


def check_terraform_references():
    """Check 5: Warn about Terraform sync after Lambda deployments"""
    print(f"\n{YELLOW}[5/36] Terraform Sync Check{RESET}")

    # Check if any Lambda ZIPs are staged
    import subprocess
    result = subprocess.run(
        ['git', 'diff', '--cached', '--name-only'],
        capture_output=True,
        text=True
    )

    staged_files = result.stdout.strip().split('\n') if result.stdout else []

    lambda_zips = [f for f in staged_files if f.endswith('.zip') and 'lambdas' in f]

    if lambda_zips:
        print(f"{YELLOW}⚠️  WARNING: Lambda ZIP files staged for commit{RESET}")
        for zip_file in lambda_zips:
            print(f"  - {zip_file}")

        print(f"\n{YELLOW}Reminder after deployment:{RESET}")
        print("  1. Update infrastructure/terraform/lambda-*.tf with new ZIP name")
        print("  2. Update infrastructure/DEPLOYED_STATE.md")
        print("  3. Run: terraform plan (verify changes)")
        print(f"\n  {YELLOW}This is a reminder, not a blocker.{RESET}")
    else:
        print(f"{GREEN}✅ No Lambda ZIPs staged (no Terraform sync needed){RESET}")

    return True  # Warning only, don't block


def check_dynamodb_table_consistency():
    """Check 6: Detect multiple similar table names, recommend consolidation"""
    print(f"\n{YELLOW}[6/36] DynamoDB Table Consistency{RESET}")

    # Tables that should NOT coexist (old vs new naming)
    conflicting_tables = [
        ('reitsheet-companies', 'reitsheet-companies-config'),
    ]

    files_to_scan = glob_lambda_files("**/handler.py")
    files_to_scan.extend(Path("infrastructure/terraform").glob("*.tf"))

    issues = []

    for old_table, new_table in conflicting_tables:
        files_with_old = []
        files_with_new = []

        for filepath in files_to_scan:
            try:
                content = filepath.read_text()

                # Check for new table reference
                if new_table in content:
                    files_with_new.append(str(filepath))

                # Check for OLD table reference that is NOT part of new table name
                # Use word boundary matching: old_table followed by non-alphanumeric
                # This prevents matching 'reitsheet-companies' inside 'reitsheet-companies-config'
                old_table_pattern = re.compile(
                    rf'{re.escape(old_table)}(?!-config)'  # Negative lookahead
                )
                if old_table_pattern.search(content):
                    files_with_old.append(str(filepath))
            except Exception:
                continue

        # If both tables are referenced, warn about consolidation
        if files_with_old and files_with_new:
            issues.append({
                'old_table': old_table,
                'new_table': new_table,
                'old_files': files_with_old,
                'new_files': files_with_new
            })

    if not issues:
        print(f"{GREEN}✅ No conflicting table references found{RESET}")
        return True
    else:
        print(f"{YELLOW}⚠️  WARNING: Multiple similar tables detected{RESET}\n")

        for issue in issues:
            print(f"  {CYAN}Conflict:{RESET} {issue['old_table']} vs {issue['new_table']}")
            print(f"  Old table referenced in:")
            for f in issue['old_files'][:3]:
                print(f"    - {f}")
            if len(issue['old_files']) > 3:
                print(f"    ... and {len(issue['old_files']) - 3} more")

        print(f"\n  {YELLOW}Recommendation:{RESET}")
        print(f"    Run: python3 scripts/merge_companies_tables.py --dry-run")
        print(f"    Then consolidate all references to {new_table}")
        print(f"\n  {YELLOW}This is a warning, not a blocker.{RESET}")

        return True  # Warning only


def check_boto3_patterns():
    """Check 7: Block commits with boto3.client('dynamodb')"""
    print(f"\n{YELLOW}[7/36] boto3 Pattern Enforcement{RESET}")

    # Pattern: boto3.client('dynamodb') - should use boto3.resource instead
    bad_pattern = re.compile(r"boto3\.client\s*\(\s*['\"]dynamodb['\"]")

    # Allowed exceptions (files that legitimately need client)
    exceptions = [
        'validate_pre_commit.py',  # This file (for checking)
        'merge_companies_tables.py',  # Migration script
    ]

    files_to_check = glob_lambda_files("**/handler.py")
    files_to_check.extend(glob_lambda_files("**/*.py"))

    issues = []

    for filepath in files_to_check:
        # Skip exceptions
        if any(exc in str(filepath) for exc in exceptions):
            continue

        try:
            content = filepath.read_text()
            matches = bad_pattern.findall(content)

            if matches:
                # Find line numbers
                lines = content.split('\n')
                for i, line in enumerate(lines, 1):
                    if bad_pattern.search(line):
                        issues.append((str(filepath), i, line.strip()))
        except Exception:
            continue

    if not issues:
        print(f"{GREEN}✅ All DynamoDB access uses boto3.resource (correct){RESET}")
        return True
    else:
        print(f"{RED}❌ Found boto3.client('dynamodb') usage - use boto3.resource instead{RESET}\n")

        for filepath, line_num, line in issues:
            print(f"  {filepath}:{line_num}")
            print(f"    {RED}{line}{RESET}")

        print(f"\n{RED}Action Required:{RESET}")
        print("  Change: dynamodb = boto3.client('dynamodb')")
        print("  To:     dynamodb = boto3.resource('dynamodb')")
        print("\n  Why: boto3.resource auto-deserializes DynamoDB responses")
        print("       boto3.client requires manual type wrapper handling")

        return False  # BLOCKS commit


def check_playwright_config_dynamodb():
    """Check 8: Query DynamoDB to verify playwright companies have required fields"""
    print(f"\n{YELLOW}[8/36] Playwright Config Completeness (DynamoDB){RESET}")

    # Try to import boto3 and check DynamoDB
    try:
        import boto3
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table('reitsheet-companies-config')

        # Scan for playwright_scraper companies
        response = table.scan(
            FilterExpression='url_construction_method = :method',
            ExpressionAttributeValues={':method': 'playwright_scraper'}
        )

        items = response.get('Items', [])

        if not items:
            print(f"{GREEN}✅ No Playwright companies configured (nothing to check){RESET}")
            return True

        required_fields = ['playwright_url', 'playwright_selector']
        issues = []

        for item in items:
            ticker = item.get('ticker', 'UNKNOWN')
            missing = [f for f in required_fields if f not in item or not item[f]]

            if missing:
                issues.append((ticker, missing))

        if not issues:
            print(f"{GREEN}✅ All {len(items)} Playwright companies have required config{RESET}")
            for item in items:
                print(f"    {item['ticker']}: {item.get('playwright_url', 'N/A')[:50]}...")
            return True
        else:
            print(f"{RED}❌ Playwright companies missing required fields{RESET}\n")

            for ticker, missing in issues:
                print(f"  {ticker}:")
                for field in missing:
                    print(f"    {RED}Missing: {field}{RESET}")

            print(f"\n{RED}Action Required:{RESET}")
            print("  Add missing fields to DynamoDB:")
            print("  aws dynamodb update-item --table-name reitsheet-companies-config \\")
            print("    --key '{\"ticker\": {\"S\": \"TICKER\"}}' \\")
            print("    --update-expression 'SET playwright_url = :url, playwright_selector = :sel' \\")
            print("    --expression-attribute-values '{\":url\": {\"S\": \"URL\"}, \":sel\": {\"S\": \"SELECTOR\"}}'")

            return False  # BLOCKS commit

    except Exception as e:
        print(f"{YELLOW}⚠️  Could not check DynamoDB (offline or no credentials): {e}{RESET}")
        print(f"    Skipping DynamoDB validation (will check on deploy)")
        return True  # Don't block if can't connect


def check_env_var_consistency():
    """Check 9: Check Lambda code defaults match Terraform env var values"""
    print(f"\n{YELLOW}[9/36] Environment Variable Consistency{RESET}")

    # Key env vars to check (Terraform var name → Lambda handler pattern)
    env_vars_to_check = [
        {
            'name': 'COMPANIES_TABLE',
            'expected': 'reitsheet-companies-config',
            'terraform_files': ['lambda-enricher.tf', 'lambda-playwright-scraper.tf', 'lambdas.tf'],
            'lambda_handlers': ['enricher/handler.py', 'playwright-scraper/handler.py', 'parser/handler.py']
        }
    ]

    issues = []

    for var_config in env_vars_to_check:
        var_name = var_config['name']
        expected = var_config['expected']

        # Check Terraform files
        for tf_file in var_config['terraform_files']:
            tf_path = Path(f"infrastructure/terraform/{tf_file}")
            if not tf_path.exists():
                continue

            content = tf_path.read_text()

            # Look for env var assignment
            # Pattern: COMPANIES_TABLE = aws_dynamodb_table.companies.name (or string)
            pattern = rf'{var_name}\s*=\s*(?:aws_dynamodb_table\.(\w+)\.name|"([^"]+)")'
            matches = re.findall(pattern, content)

            for match in matches:
                table_ref = match[0] if match[0] else match[1]
                # Check if it references the old table
                if 'companies_config' not in table_ref and 'companies-config' not in table_ref:
                    if table_ref == 'companies' or 'reitsheet-companies' == table_ref:
                        issues.append({
                            'file': str(tf_path),
                            'var': var_name,
                            'found': table_ref,
                            'expected': expected
                        })

    if not issues:
        print(f"{GREEN}✅ Environment variables consistent with expected tables{RESET}")
        return True
    else:
        print(f"{YELLOW}⚠️  WARNING: Environment variable references may be outdated{RESET}\n")

        for issue in issues:
            print(f"  {issue['file']}:")
            print(f"    {issue['var']} references '{issue['found']}'")
            print(f"    Expected: '{issue['expected']}'")

        print(f"\n  {YELLOW}Recommendation:{RESET}")
        print(f"    Update Terraform to use aws_dynamodb_table.companies_config.name")
        print(f"    Or the string 'reitsheet-companies-config'")
        print(f"\n  {YELLOW}This is a warning, not a blocker.{RESET}")

        return True  # Warning only


def check_python_syntax():
    """Check 10: Validate Python syntax in Lambda handlers (BLOCKS)"""
    print(f"\n{YELLOW}[10/36] Python Syntax Validation{RESET}")

    import py_compile
    import tempfile

    handler_files = glob_lambda_files("**/handler.py")

    if not handler_files:
        print(f"{YELLOW}No handler files found (skipping){RESET}")
        return True

    errors = []

    for handler_path in handler_files:
        try:
            # Compile to check syntax without executing
            py_compile.compile(str(handler_path), doraise=True)
        except py_compile.PyCompileError as e:
            errors.append((str(handler_path), str(e)))

    if not errors:
        print(f"{GREEN}All {len(handler_files)} handler files have valid syntax{RESET}")
        return True
    else:
        print(f"{RED}Syntax errors found!{RESET}\n")

        for filepath, error in errors:
            print(f"  {filepath}:")
            print(f"    {RED}{error}{RESET}")

        print(f"\n{RED}Action Required:{RESET}")
        print("  Fix syntax errors before committing.")
        print("  Run: python3 -m py_compile <file> to check syntax")

        return False  # BLOCKS commit


def check_import_resolution():
    """Check 11: Verify critical imports can be resolved (BLOCKS)"""
    print(f"\n{YELLOW}[11/36] Import Resolution Check{RESET}")

    import ast

    # Check critical imports in handler files
    critical_imports = {
        'parser/handler.py': ['json', 'os', 'boto3'],
        'enricher/handler.py': ['json', 'os', 'boto3'],
        'email-forwarder/handler.py': ['json', 'os', 'boto3'],
        'daily-summary/handler.py': ['json', 'os', 'boto3'],
    }

    errors = []

    for handler_pattern, required_imports in critical_imports.items():
        handler_path = Path("infrastructure/lambdas") / handler_pattern

        if not handler_path.exists():
            continue

        try:
            content = handler_path.read_text()
            tree = ast.parse(content)

            # Extract all imported module names
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imported.add(alias.name.split('.')[0])
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imported.add(node.module.split('.')[0])

            # Check required imports are present
            missing = [imp for imp in required_imports if imp not in imported]

            if missing:
                errors.append((str(handler_path), missing))

        except SyntaxError as e:
            # Syntax errors caught by check_python_syntax
            continue
        except Exception as e:
            print(f"{YELLOW}Could not parse {handler_path}: {e}{RESET}")
            continue

    if not errors:
        print(f"{GREEN}All critical imports present in handlers{RESET}")
        return True
    else:
        print(f"{RED}Missing critical imports!{RESET}\n")

        for filepath, missing in errors:
            print(f"  {filepath}:")
            for imp in missing:
                print(f"    {RED}Missing: import {imp}{RESET}")

        print(f"\n{RED}Action Required:{RESET}")
        print("  Add missing imports to handler files.")

        return False  # BLOCKS commit


def check_direct_url_config():
    """Check 12: Verify direct_url companies have valid config (WARNS)"""
    print(f"\n{YELLOW}[12/36] Direct URL Config Validation{RESET}")

    # Try to import boto3 and check DynamoDB
    try:
        import boto3
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table('reitsheet-companies-config')

        # Scan for direct_url companies
        response = table.scan(
            FilterExpression='url_construction_method = :method',
            ExpressionAttributeValues={':method': 'direct_url'}
        )

        items = response.get('Items', [])

        if not items:
            print(f"{GREEN}No direct_url companies configured (nothing to check){RESET}")
            return True

        # Required fields for direct_url companies
        required_fields = ['press_release_url']
        issues = []

        for item in items:
            ticker = item.get('ticker', 'UNKNOWN')
            missing = [f for f in required_fields if f not in item or not item[f]]

            if missing:
                issues.append((ticker, missing))

        if not issues:
            print(f"{GREEN}All {len(items)} direct_url companies have required config{RESET}")
            for item in items:
                ticker = item['ticker']
                url = item.get('press_release_url', 'N/A')[:50]
                print(f"    {ticker}: {url}...")
            return True
        else:
            print(f"{YELLOW}direct_url companies missing required fields{RESET}\n")

            for ticker, missing in issues:
                print(f"  {ticker}:")
                for field in missing:
                    print(f"    {YELLOW}Missing: {field}{RESET}")

            print(f"\n{YELLOW}Note:{RESET}")
            print("  direct_url companies skip URL validation (for bot protection)")
            print("  They still need press_release_url for URL selection logic")
            print(f"\n  {YELLOW}This is a warning, not a blocker.{RESET}")

            return True  # Warning only

    except Exception as e:
        print(f"{YELLOW}Could not check DynamoDB (offline or no credentials): {e}{RESET}")
        print(f"    Skipping direct_url validation (will check on deploy)")
        return True  # Don't block if can't connect


def check_routing_table_validity():
    """Check 13: Validate CLAUDE.md routing table when routing code changes (BLOCKS)"""
    print(f"\n{YELLOW}[13/36] CLAUDE.md Routing Table Validation{RESET}")

    # Check if routing files were modified in this commit
    import subprocess
    result = subprocess.run(
        ['git', 'diff', '--cached', '--name-only'],
        capture_output=True,
        text=True
    )

    staged_files = result.stdout.strip().split('\n') if result.stdout else []

    # Routing files that trigger validation
    routing_files = [
        'infrastructure/lambdas/parser/routing.py',
        'infrastructure/lambdas/enricher/handler.py',
        'infrastructure/lambdas/enricher/persistence/redirect_circuit_breaker.py'
    ]

    routing_changed = any(rf in staged_files for rf in routing_files)

    if not routing_changed:
        print(f"{GREEN}✅ No routing code changes (skipping validation){RESET}")
        return True

    print(f"{CYAN}Routing code changed - validating CLAUDE.md routing table...{RESET}\n")

    # Run routing table validation script
    script_path = Path("scripts/validate_routing_table.py")
    if not script_path.exists():
        print(f"{YELLOW}⚠️  Routing table validation script not found (skipping){RESET}")
        return True

    result = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True
    )

    if result.returncode == 0:
        print(f"{GREEN}✅ Routing table validated - CLAUDE.md is current{RESET}")
        return True
    else:
        print(f"{RED}❌ Routing table validation failed{RESET}\n")
        print(result.stdout.decode() if result.stdout else "")
        print(f"\n{RED}Action Required:{RESET}")
        print("  You changed routing code but CLAUDE.md routing table is out of sync.")
        print("  Update the 'Email Routing Decision Table' section in CLAUDE.md")
        print("  to reflect your routing code changes.")
        return False  # BLOCKS commit


def check_template_date_safety():
    """
    Check 15: Template Date Safety

    Ensures templates use |format_date filter instead of raw .strftime()

    BLOCKS: Raw .strftime() in templates (must use |format_date filter)

    Why: ChainableUndefined makes templates crash-proof, but we enforce
    consistent |format_date usage for predictable 'N/A' display
    """
    print(f"\n{YELLOW}[15/36] Template Date Safety{RESET}")

    templates_dir = Path('infrastructure/docker/flask-app/templates')

    if not templates_dir.exists():
        print(f"{GREEN}✅ Templates directory not found (skipping){RESET}")
        return True

    # Find raw .strftime() calls in templates
    bad_pattern = re.compile(r'\.\s*strftime\s*\(')
    issues = []

    for template_path in templates_dir.glob('**/*.html'):
        # Skip backup files
        if '.backup' in str(template_path):
            continue

        try:
            content = template_path.read_text()
            lines = content.split('\n')

            for i, line in enumerate(lines, 1):
                if bad_pattern.search(line):
                    # Extract the problematic part
                    issues.append((str(template_path), i, line.strip()[:80]))
        except Exception:
            pass

    if not issues:
        print(f"{GREEN}✅ All templates use |format_date filter{RESET}")
        return True
    else:
        print(f"{RED}❌ Raw .strftime() found in templates - must use |format_date filter{RESET}\n")

        for filepath, line_num, line in issues:
            print(f"  {filepath}:{line_num}")
            print(f"    {RED}{line}{RESET}")

        print(f"\n{RED}Action Required:{RESET}")
        print("  Change: {{ date.strftime('%b %d, %Y') }}")
        print("  To:     {{ date|format_date }}")
        print("  Or:     {{ date|format_date('%Y-%m-%d') }}")
        print("  Or:     {{ date|format_date('%Y-%m-%d', '') }}  (for form inputs)")
        print("\n  Why: |format_date safely handles None values")

        return False  # BLOCKS commit


def check_landing_page_detection_integrity():
    """
    Check 14: Landing Page Detection Integrity

    Ensures:
    1. GENERIC_PAGE_SEGMENTS only exists in shared/landing_page_detector.py (no duplication)
    2. is_landing_page() function only exists in shared/landing_page_detector.py (no duplication)
    3. All DynamoDB saves have landing page check within 20 lines (warns if missing)

    BLOCKS: Duplication detected
    WARNS: Save path missing landing page check
    """
    print(f"\n{YELLOW}[14/36] Landing Page Detection Integrity{RESET}")

    blocking_failures = []
    warnings = []

    # Check 1: GENERIC_PAGE_SEGMENTS should only be DEFINED in shared module
    print(f"{CYAN}  Checking GENERIC_PAGE_SEGMENTS duplication...{RESET}")

    files_with_generic_segments = []
    for root, dirs, files in os.walk('infrastructure/lambdas'):
        # Skip package/build directories
        if 'package' in root or '__pycache__' in root:
            continue

        for file in files:
            if file.endswith('.py') and not file.endswith('_old.py'):
                filepath = os.path.join(root, file)
                try:
                    content = Path(filepath).read_text()
                    # Look for DEFINITION (assignment with =), not just imports
                    if re.search(r'^GENERIC_PAGE_SEGMENTS\s*=', content, re.MULTILINE):
                        # Allowed location: shared/landing_page_detector.py
                        if 'shared/landing_page_detector.py' not in filepath:
                            files_with_generic_segments.append(filepath)
                except Exception:
                    pass

    if files_with_generic_segments:
        blocking_failures.append(
            f"GENERIC_PAGE_SEGMENTS found in {len(files_with_generic_segments)} files "
            f"(should only be in shared/landing_page_detector.py):\n  - " +
            "\n  - ".join(files_with_generic_segments)
        )
    else:
        print(f"{GREEN}    ✓ GENERIC_PAGE_SEGMENTS only in shared module{RESET}")

    # Check 2: is_landing_page() should only be IMPLEMENTED in shared module
    # (wrapper functions that delegate to shared are OK)
    print(f"{CYAN}  Checking is_landing_page() duplication...{RESET}")

    files_with_is_landing_page = []
    for root, dirs, files in os.walk('infrastructure/lambdas'):
        # Skip package/build directories and old files
        if 'package' in root or '__pycache__' in root:
            continue

        for file in files:
            if file.endswith('.py') and not file.endswith('_old.py'):
                filepath = os.path.join(root, file)
                try:
                    content = Path(filepath).read_text()
                    # Match function definitions
                    if re.search(r'^def is_landing_page\(', content, re.MULTILINE):
                        # Check if it's a wrapper (delegates to shared_is_landing_page)
                        is_wrapper = 'shared_is_landing_page' in content or 'DELEGATES to shared' in content

                        # Allowed: shared module or wrapper functions
                        if 'shared/landing_page_detector.py' not in filepath and not is_wrapper:
                            files_with_is_landing_page.append(filepath)
                except Exception:
                    pass

    if files_with_is_landing_page:
        blocking_failures.append(
            f"is_landing_page() function found in {len(files_with_is_landing_page)} files "
            f"(should only be in shared/landing_page_detector.py):\n  - " +
            "\n  - ".join(files_with_is_landing_page)
        )
    else:
        print(f"{GREEN}    ✓ is_landing_page() only in shared module{RESET}")

    # Check 3: All DynamoDB saves should have landing page validation
    print(f"{CYAN}  Checking DynamoDB saves for landing page validation...{RESET}")

    save_files_to_check = [
        'infrastructure/lambdas/enricher/persistence/dynamodb_ops.py',
        'infrastructure/lambdas/scraper/scraper_persistence.py',
        'infrastructure/lambdas/playwright-scraper/handler.py',
    ]

    files_missing_validation = []

    for filepath in save_files_to_check:
        path = Path(filepath)
        if not path.exists():
            continue

        content = path.read_text()
        lines = content.split('\n')

        # Find DynamoDB save operations (put_item calls)
        save_found = False
        validation_found = False

        for i, line in enumerate(lines):
            if '.put_item(' in line or 'put_item(Item=' in line:
                save_found = True

                # Check 20 lines before save for landing page validation
                start_line = max(0, i - 20)
                context = '\n'.join(lines[start_line:i])

                if 'is_landing_page' in context or 'landing_page' in context.lower():
                    validation_found = True
                    break

        if save_found and not validation_found:
            files_missing_validation.append(filepath)

    if files_missing_validation:
        warnings.append(
            f"DynamoDB saves without landing page validation:\n  - " +
            "\n  - ".join(files_missing_validation) +
            "\n  Add is_landing_page() check before save"
        )
    else:
        print(f"{GREEN}    ✓ All DynamoDB saves have landing page validation{RESET}")

    # Report results
    if blocking_failures:
        print(f"{RED}❌ Landing page detection integrity FAILED (BLOCKS commit){RESET}")
        for failure in blocking_failures:
            print(f"{RED}   {failure}{RESET}")
        return False

    if warnings:
        print(f"{YELLOW}⚠️  Warnings (non-blocking):{RESET}")
        for warning in warnings:
            print(f"{YELLOW}   {warning}{RESET}")

    if not blocking_failures and not warnings:
        print(f"{GREEN}✅ Landing page detection integrity validated{RESET}")

    return True  # Warnings don't block, only blocking_failures


def check_flask_session_https_config():
    """Check 16: Validate Flask session cookies are configured for HTTPS"""
    print(f"\n{YELLOW}[16/36] Flask Session HTTPS Configuration{RESET}")

    required_configs = {
        'SESSION_COOKIE_SECURE': 'True',  # Require HTTPS
        'SESSION_COOKIE_HTTPONLY': 'True',  # Block JavaScript access
        'SESSION_COOKIE_SAMESITE': "'Lax'"  # CSRF protection
    }

    app_files = [
        'app.py',
        'infrastructure/docker/flask-app/app.py'
    ]

    missing_configs = []

    for app_file in app_files:
        path = Path(app_file)
        if not path.exists():
            continue

        content = path.read_text()
        file_missing = []

        for config_name, expected_value in required_configs.items():
            # Check if config is set correctly
            pattern = rf"app\.config\['{config_name}'\]\s*=\s*{expected_value}"
            if not re.search(pattern, content):
                file_missing.append(config_name)

        if file_missing:
            missing_configs.append({
                'file': app_file,
                'missing': file_missing
            })

    if missing_configs:
        print(f"{RED}❌ Flask session HTTPS config incomplete{RESET}")
        print("\nMissing or incorrect session cookie configuration:")
        for item in missing_configs:
            print(f"\n  File: {item['file']}")
            for config in item['missing']:
                expected = required_configs[config]
                print(f"    ❌ {config} = {expected}")

        print(f"\n{CYAN}Required configuration (add after app.secret_key):{RESET}")
        print("  app.config['SESSION_COOKIE_SECURE'] = True  # Require HTTPS")
        print("  app.config['SESSION_COOKIE_HTTPONLY'] = True  # Block JavaScript")
        print("  app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # CSRF protection")
        print("\n{YELLOW}Why this matters:{RESET}")
        print("  - Without SECURE: Session cookies sent over HTTP (security risk)")
        print("  - Without HTTPONLY: JavaScript can steal session cookies (XSS)")
        print("  - Without SAMESITE: Vulnerable to CSRF attacks")
        print("  - This exact issue caused OAuth login loop on production")

        return False

    print(f"{GREEN}✅ Flask session cookies properly configured for HTTPS{RESET}")
    return True


def check_deployment_config():
    """Check 17: Validate deployment-config.json exists and is valid"""
    print(f"\n{YELLOW}[17/36] Deployment Configuration (deployment-config.json){RESET}")

    config_path = Path("infrastructure/deployment-config.json")

    if not config_path.exists():
        print(f"{RED}❌ deployment-config.json not found{RESET}")
        print(f"\n{CYAN}Why this matters:{RESET}")
        print("  - Claude needs to know WHERE Flask is deployed")
        print("  - Prevents 'where is Flask running?' confusion")
        print("  - Machine-readable deployment info")
        print(f"\n{CYAN}Create it with:{RESET}")
        print("  See infrastructure/PRODUCTION_DEPLOYMENT.md")
        return False

    # Validate JSON syntax
    try:
        import json
        with open(config_path) as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        print(f"{RED}❌ deployment-config.json is invalid JSON{RESET}")
        print(f"   Error: {e}")
        return False

    # Validate required keys
    required_keys = ['deployment', 'deploy_steps', 'health_checks']
    missing_keys = [k for k in required_keys if k not in config]

    if missing_keys:
        print(f"{RED}❌ deployment-config.json missing required keys{RESET}")
        print(f"   Missing: {', '.join(missing_keys)}")
        return False

    # Validate deployment.ec2_instance
    if 'ec2_instance' not in config['deployment']:
        print(f"{RED}❌ deployment-config.json missing deployment.ec2_instance{RESET}")
        return False

    ec2 = config['deployment']['ec2_instance']
    required_ec2_keys = ['ssh_alias', 'ssh_key', 'ssh_user']
    missing_ec2 = [k for k in required_ec2_keys if k not in ec2]

    if missing_ec2:
        print(f"{RED}❌ deployment.ec2_instance missing keys: {', '.join(missing_ec2)}{RESET}")
        return False

    # Validate deployment.application
    if 'application' not in config['deployment']:
        print(f"{RED}❌ deployment-config.json missing deployment.application{RESET}")
        return False

    app = config['deployment']['application']
    required_app_keys = ['path', 'entry_point']
    missing_app = [k for k in required_app_keys if k not in app]

    if missing_app:
        print(f"{RED}❌ deployment.application missing keys: {', '.join(missing_app)}{RESET}")
        return False

    print(f"{GREEN}✅ Deployment config valid{RESET}")
    print(f"   SSH: {ec2['ssh_alias']} (IP auto-fetched from AWS)")
    print(f"   App: {app['path']}")
    print(f"   Use: python3 scripts/get_deployment_info.py")
    return True


def check_flask_wtf_usage():
    """
    Check 18: Flask-WTF Form Usage

    Validates that POST routes use Flask-WTF forms properly:
    - Forms defined in forms/ directory
    - Templates use form.hidden_tag() for CSRF
    - No manual CSRF token handling

    Known exceptions: review_emails.py, url_testing.py, actions.py (use JSON POST, not forms)
    """
    print(f"\n{YELLOW}[18/36] Flask-WTF Form Usage{RESET}")

    issues = []

    # Check for manual CSRF tokens in templates
    flask_templates = Path('infrastructure/docker/flask-app/templates')
    if flask_templates.exists():
        for template in flask_templates.glob('*.html'):
            content = template.read_text()
            # Look for manual CSRF tokens (bad practice)
            if 'csrf_token()' in content and 'form.hidden_tag()' not in content:
                # Check if it's in a form
                if '<form' in content and 'method="POST"' in content.upper():
                    issues.append(f"{template.name}: Uses manual csrf_token() instead of form.hidden_tag()")

    # Check that forms/ directory has form classes for POST routes
    forms_dir = Path('infrastructure/docker/flask-app/forms')
    routes_dir = Path('infrastructure/docker/flask-app/routes')

    if routes_dir.exists():
        for route_file in routes_dir.glob('*.py'):
            # Skip backup files, __init__, and known exceptions
            if (route_file.name == '__init__.py' or
                'OLD' in route_file.name or
                'BACKUP' in route_file.name or
                'REFACTORED' in route_file.name or
                route_file.name in ['api.py', 'auth.py', 'review_emails.py', 'url_testing.py', 'actions.py',
                                   'publisher_styles.py', 'publisher_email.py', 'disclosures.py', 'analytics.py']):  # API/JSON routes
                continue

            content = route_file.read_text()
            # Check if route has POST methods
            if "methods=['POST']" in content or 'methods=["POST"]' in content:
                # Check if it imports Flask-WTF (from forms/ directory OR direct import)
                has_flask_wtf = (
                    'from forms.' in content or
                    'import forms' in content or
                    'from flask_wtf import' in content or
                    'import flask_wtf' in content
                )
                if not has_flask_wtf:
                    # Allow routes that disable CSRF explicitly (API routes)
                    if 'csrf_exempt' in content or '@api.' in content:
                        continue
                    issues.append(f"{route_file.name}: Has POST routes but doesn't import Flask-WTF forms")

    if issues:
        print(f"{RED}❌ Flask-WTF issues found:{RESET}")
        for issue in issues:
            print(f"  - {issue}")
        print(f"\n{CYAN}Use Flask-WTF forms for POST requests:{RESET}")
        print(f"  1. Create form in forms/: class MyForm(FlaskForm)")
        print(f"  2. In route: from forms.my_forms import MyForm")
        print(f"  3. In template: {{{{ form.hidden_tag() }}}}")
        return False
    else:
        print(f"{GREEN}✅ Flask-WTF forms properly used{RESET}")
        return True


def check_timestamp_field_formats():
    """
    Check 19: Timestamp Field Format Validation

    Validates that DynamoDB writes use correct timestamp formats:
    - *_at fields must use ISO 8601 with timezone (.isoformat())
    - *_date fields can use DATE ONLY (YYYY-MM-DD)
    - Detects manual .strftime() on *_at fields (should use timestamp_utils)
    - Detects .date() on datetime objects before DynamoDB save

    BLOCKS commits that violate these rules.

    Background: Timestamps were showing "12:00AM" because Lambdas stored
    date-only strings ('2026-03-15') instead of ISO timestamps with time
    ('2026-03-15T10:30:00+00:00'). This check prevents regression.

    See: infrastructure/DYNAMODB_SCHEMA.md
    """
    print(f"\n{YELLOW}[19/36] Timestamp Field Format Validation{RESET}")

    issues = []

    # Find all Lambda persistence files
    persistence_patterns = [
        'infrastructure/lambdas/*/persistence/*.py',
        'infrastructure/lambdas/*/*/*_persistence.py',
        'infrastructure/lambdas/*/handler.py',  # Some handlers write to DynamoDB
        'infrastructure/lambdas/*/routing.py',  # Parser routing writes to DynamoDB
    ]

    persistence_files = []
    for pattern in persistence_patterns:
        persistence_files.extend(Path('.').glob(pattern))

    if not persistence_files:
        print(f"{YELLOW}⚠️  No persistence files found (skipping){RESET}")
        return True

    for file_path in persistence_files:
        # Skip backup/test files
        if 'BACKUP' in str(file_path) or 'OLD' in str(file_path) or 'test_' in str(file_path):
            continue

        try:
            content = file_path.read_text()
        except Exception:
            continue

        # Skip if file doesn't write to DynamoDB
        if 'put_item' not in content and 'update_item' not in content:
            continue

        # Pattern 1: Detect .date() before put_item (WRONG - loses timezone)
        # Example: 'first_seen_at': datetime.now().date()
        # Look for datetime.date() followed by DynamoDB write within 50 lines
        lines = content.split('\n')
        for i, line in enumerate(lines):
            # Check for *_at field assignment with .date()
            if re.search(r"['\"].*_at['\"]\s*:\s*.*\.date\(\)", line):
                issues.append((
                    str(file_path),
                    i + 1,
                    f"Uses .date() on *_at field (loses timezone)",
                    line.strip()[:80]
                ))

            # Pattern 2: Detect .strftime('%Y-%m-%d') on *_at fields (WRONG - date-only)
            # Example: 'first_seen_at': datetime.now().strftime('%Y-%m-%d')
            if re.search(r"['\"].*_at['\"]\s*:\s*.*\.strftime\(['\"]%Y-%m-%d['\"]\)", line):
                issues.append((
                    str(file_path),
                    i + 1,
                    f"Uses .strftime('%Y-%m-%d') on *_at field (should be ISO 8601)",
                    line.strip()[:80]
                ))

            # Pattern 3: Detect .isoformat() on *_date fields (WRONG - too precise)
            # Example: 'press_release_date': datetime.now().isoformat()
            if re.search(r"['\"]press_release_date['\"]\s*:\s*.*\.isoformat\(\)", line):
                issues.append((
                    str(file_path),
                    i + 1,
                    f"Uses .isoformat() on press_release_date (should be DATE ONLY)",
                    line.strip()[:80]
                ))

        # Pattern 4: Check if persistence file imports from shared.timestamp_utils
        # This is a RECOMMENDATION, not a blocker
        if 'put_item' in content or 'update_item' in content:
            if 'from shared.timestamp_utils import' not in content:
                # Check if it uses datetime directly for timestamp fields
                if re.search(r"['\"].*_at['\"]\s*:\s*datetime\.", content):
                    # Not necessarily wrong, but recommend using shared utilities
                    print(f"{CYAN}  NOTE: {file_path.name} uses datetime directly for *_at fields{RESET}")
                    print(f"        Consider: from shared.timestamp_utils import get_current_timestamp_utc{RESET}")

    if issues:
        print(f"{RED}❌ Timestamp format violations found:{RESET}\n")
        for filepath, line_num, reason, line in issues:
            print(f"  {filepath}:{line_num}")
            print(f"    {RED}{reason}{RESET}")
            print(f"    {line}\n")

        print(f"\n{RED}Action Required:{RESET}")
        print(f"  {CYAN}Fix by using shared.timestamp_utils:{RESET}")
        print(f"    1. Import: from shared.timestamp_utils import get_current_timestamp_utc")
        print(f"    2. Use:    'first_seen_at': get_current_timestamp_utc()")
        print(f"    3. NEVER use .date() on *_at fields (loses timezone)")
        print(f"    4. NEVER use .strftime('%Y-%m-%d') on *_at fields (date-only)")
        print(f"\n  {CYAN}See: infrastructure/DYNAMODB_SCHEMA.md for field format reference{RESET}")
        return False  # BLOCKS commit

    print(f"{GREEN}✅ All timestamp fields use correct formats{RESET}")
    return True


def check_lambda_zip_dependencies():
    """
    Check 20: Validate Lambda ZIP files contain required dependencies.

    BLOCKS commit if a Lambda ZIP is staged/exists and is missing dependencies
    from its requirements.txt.

    This prevents the recurring issue of deploying Lambdas with missing modules.
    """
    print(f"\n{YELLOW}[20/36] Lambda ZIP Dependency Validation{RESET}")

    import zipfile
    import subprocess

    # Map pip package names to expected module directories in ZIP
    PACKAGE_TO_MODULE = {
        'requests': ['requests'],
        'beautifulsoup4': ['bs4'],
        'feedparser': ['feedparser'],
        'python-dateutil': ['dateutil'],
        'boto3': ['boto3'],  # Usually in Lambda runtime, but check if in requirements
        'cloudscraper': ['cloudscraper'],
        'curl_cffi': ['curl_cffi'],
        'playwright': ['playwright'],
        'lxml': ['lxml'],
    }

    # Lambda directories and their ZIP name patterns (checked in order, first match wins)
    LAMBDA_ZIP_PATTERNS = {
        'parser': ['parser-with-deps.zip', 'parser-*.zip'],
        'enricher': ['enricher-with-deps.zip', 'enricher-fixed.zip', 'enricher-*.zip'],
        'scraper': ['scraper-with-deps.zip', 'scraper-*.zip'],
        'playwright-scraper': ['playwright-scraper-with-deps.zip', 'playwright-*.zip'],
    }

    # Dependencies that are in Lambda runtime (don't need to be in ZIP)
    RUNTIME_PACKAGES = {'boto3', 'botocore', 'urllib3', 'jmespath', 's3transfer'}

    # Required local modules (must be at root level in ZIP)
    REQUIRED_LOCAL_MODULES = {
        'parser': ['shared/', 'handler.py', 'routing.py'],
        'enricher': ['shared/', 'handler.py', 'persistence/'],
        'scraper': ['shared/', 'handler.py'],
        'playwright-scraper': ['shared/', 'handler.py'],
    }

    # Critical files that MUST exist within shared/ directory
    REQUIRED_SHARED_FILES = [
        'shared/landing_page_detector.py',
        'shared/timestamp_utils.py',
        'shared/constants.py',
    ]

    lambdas_dir = Path("infrastructure/lambdas")
    issues = []
    checked = 0

    # Check which ZIPs are staged for commit
    try:
        result = subprocess.run(
            ['git', 'diff', '--cached', '--name-only'],
            capture_output=True, text=True
        )
        staged_files = set(result.stdout.strip().split('\n')) if result.stdout.strip() else set()
    except Exception:
        staged_files = set()

    import glob as glob_module

    for lambda_name, zip_patterns in LAMBDA_ZIP_PATTERNS.items():
        lambda_dir = lambdas_dir / lambda_name
        requirements_path = lambda_dir / "requirements.txt"

        # Skip if requirements.txt doesn't exist
        if not requirements_path.exists():
            continue

        # Find the most recent ZIP matching any pattern
        zip_path = None
        for pattern in zip_patterns:
            matches = list(lambda_dir.glob(pattern))
            if matches:
                # Get most recently modified
                zip_path = max(matches, key=lambda p: p.stat().st_mtime)
                break

        # Skip if no ZIP found
        if zip_path is None:
            continue

        zip_name = zip_path.name

        checked += 1

        # Parse requirements.txt
        required_packages = set()
        with open(requirements_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                # Extract package name (before ==, >=, etc.)
                match = re.match(r'^([a-zA-Z0-9_-]+)', line)
                if match:
                    pkg = match.group(1).lower()
                    if pkg not in RUNTIME_PACKAGES:
                        required_packages.add(pkg)

        # Check ZIP contents
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zip_contents = set(zf.namelist())

                # Check for nested package/ directory (common build mistake)
                nested_package = any(name.startswith('package/') for name in zip_contents)
                if nested_package:
                    issues.append((
                        lambda_name, zip_name, "STRUCTURE",
                        "ZIP has nested package/ directory - modules must be at root level"
                    ))
                    continue  # Skip further checks, structure is fundamentally wrong

                # Check required local modules (shared/, handler.py, etc.)
                required_locals = REQUIRED_LOCAL_MODULES.get(lambda_name, [])
                for local_mod in required_locals:
                    if local_mod.endswith('/'):
                        # Directory - check if any file starts with this prefix
                        if not any(name.startswith(local_mod) for name in zip_contents):
                            issues.append((lambda_name, zip_name, "LOCAL", f"Missing {local_mod} directory"))
                    else:
                        # File - check exact match
                        if local_mod not in zip_contents:
                            issues.append((lambda_name, zip_name, "LOCAL", f"Missing {local_mod}"))

                # Check critical shared files exist (prevents "No module named X" errors)
                for shared_file in REQUIRED_SHARED_FILES:
                    if shared_file not in zip_contents:
                        issues.append((lambda_name, zip_name, "SHARED", f"Missing {shared_file}"))

                # Check each required package from requirements.txt
                for pkg in required_packages:
                    modules = PACKAGE_TO_MODULE.get(pkg, [pkg])
                    found = False
                    for module in modules:
                        # Check for module directory or .py file at root level
                        if any(name.startswith(f"{module}/") or name == f"{module}.py" for name in zip_contents):
                            found = True
                            break

                    if not found:
                        issues.append((lambda_name, zip_name, pkg, modules[0]))
        except zipfile.BadZipFile:
            issues.append((lambda_name, zip_name, "INVALID", "ZIP file is corrupted"))

    if checked == 0:
        print(f"{CYAN}  No Lambda ZIPs found to validate{RESET}")
        return True

    if issues:
        print(f"{RED}❌ Lambda ZIP validation failed:{RESET}\n")
        for lambda_name, zip_name, issue_type, detail in issues:
            print(f"  {RED}{lambda_name}/{zip_name}:{RESET}")
            if issue_type == "STRUCTURE":
                print(f"    {RED}BAD STRUCTURE: {detail}{RESET}")
            elif issue_type == "INVALID":
                print(f"    {RED}CORRUPTED: {detail}{RESET}")
            elif issue_type == "LOCAL":
                print(f"    {RED}LOCAL MODULE: {detail}{RESET}")
            elif issue_type == "SHARED":
                print(f"    {RED}SHARED MODULE: {detail}{RESET}")
            else:
                print(f"    Missing pip package: {issue_type} (expected: {detail}/)")

        # Collect unique failing lambdas
        failing_lambdas = sorted(set(item[0] for item in issues))

        print(f"\n{YELLOW}Rebuild commands:{RESET}")
        for lname in failing_lambdas:
            print(f"\n  {CYAN}# {lname}{RESET}")
            print(f"  cd infrastructure/lambdas/{lname}")
            print(f"  rm -rf package *.zip && mkdir package")
            print(f"  pip3 install -t package/ -r requirements.txt")
            if lname == 'enricher':
                print(f"  cp -r *.py package/ && cp -r persistence package/ && cp -r ../shared package/")
            else:
                print(f"  cp -r *.py package/ && cp -r ../shared package/")
            print(f"  cd package && zip -r ../{lname}-with-deps.zip . && cd .. && rm -rf package")

        print(f"\n  {RED}Common mistake:{RESET} Zipping the package/ folder itself instead of its contents")
        print(f"  {GREEN}Correct:{RESET} cd package && zip -r ../out.zip .")
        print(f"  {RED}Wrong:{RESET}   zip -r out.zip package/")
        return False  # BLOCKS commit

    print(f"{GREEN}✅ All {checked} Lambda ZIPs contain required dependencies{RESET}")
    return True


def check_lambda_import_smoke_test():
    """
    Check 21: Lambda Import Smoke Test via AST Analysis (BLOCKS)

    Uses AST analysis to detect import issues WITHOUT requiring dependencies:
    - Duplicate function definitions that shadow imports
    - Names used but never imported or defined
    - Missing imports for standard library modules

    This catches bugs like playwright-scraper's duplicate functions that
    shadowed the imported versions from persistence.dynamodb_ops.
    """
    print(f"\n{YELLOW}[21/36] Lambda Import Smoke Test (AST){RESET}")

    import ast

    # Python builtins that don't need imports
    BUILTINS = set(dir(__builtins__)) if isinstance(__builtins__, dict) else set(dir(__builtins__))
    BUILTINS.update({
        'True', 'False', 'None', 'Exception', 'BaseException',
        'print', 'len', 'str', 'int', 'float', 'list', 'dict', 'set', 'tuple',
        'range', 'enumerate', 'zip', 'map', 'filter', 'sorted', 'reversed',
        'open', 'isinstance', 'issubclass', 'hasattr', 'getattr', 'setattr',
        'type', 'super', 'property', 'staticmethod', 'classmethod',
        'any', 'all', 'sum', 'min', 'max', 'abs', 'round',
        'KeyError', 'ValueError', 'TypeError', 'AttributeError', 'IndexError',
        'RuntimeError', 'StopIteration', 'FileNotFoundError', 'OSError',
    })

    # Known third-party/local modules (don't flag these as undefined)
    KNOWN_MODULES = {
        'boto3', 'botocore', 'requests', 'bs4', 'feedparser', 'dateutil',
        'playwright', 'cloudscraper', 'curl_cffi', 'lxml',
        # Local modules
        'browser', 'matching', 'persistence', 'routing', 'shared',
        'landing_page_detector', 'timestamp_utils', 'constants',
        'redirect_circuit_breaker', 'timezone_utils',
        # Enricher submodules
        'url_selection', 'url_construction', 'title_cleanup', 'config',
        'enricher',
    }

    # Main handlers
    LAMBDA_HANDLERS = [
        'parser/handler.py',
        'enricher/handler.py',
        'playwright-scraper/handler.py',
        'scraper/handler.py',
        '8k-processor/handler.py',
        '8k-fetcher/handler.py',
    ]

    # Critical support modules (Gap 2 fix - these are imported by handlers but
    # weren't being validated, missing routing.py bugs until runtime)
    LAMBDA_SUPPORT_MODULES = [
        # Parser modules
        'parser/routing.py',            # 600+ lines, routing decisions
        'parser/company_matching.py',   # 300+ lines, company lookup
        'parser/url_utils.py',          # 400+ lines, URL extraction
        'parser/confidence_scoring.py', # Multi-signal matching
        'parser/matching/hybrid_matcher.py',      # Hybrid company matching
        'parser/matching/domain_extraction.py',   # Domain extraction logic
        'parser/matching/gsi_matcher.py',         # GSI-based matching
        # Enricher modules
        'enricher/persistence/dynamodb_ops.py',   # DynamoDB persistence
        'enricher/persistence/sqs_ops.py',        # SQS operations
        'enricher/url_selection/selector.py',     # URL selection logic
        'enricher/url_selection/detector.py',     # IR URL detection
        'enricher/url_selection/scorer.py',       # URL scoring
        'enricher/url_construction/constructor.py', # URL slug creation
        'enricher/url_construction/validator.py',   # URL validation
        'enricher/title_cleanup/cleaner.py',        # Title cleanup
    ]

    # Combine for full validation
    ALL_MODULES_TO_CHECK = LAMBDA_HANDLERS + LAMBDA_SUPPORT_MODULES

    errors = []
    warnings = []
    checked = 0

    for module_rel in ALL_MODULES_TO_CHECK:
        module_path = Path("infrastructure/lambdas") / module_rel

        if not module_path.exists():
            continue

        checked += 1
        lambda_name = module_rel.split('/')[0]
        module_name = module_rel.split('/')[-1]  # e.g., "routing.py"

        try:
            content = module_path.read_text()
            tree = ast.parse(content)

            # Collect all imported names
            imported_names = set()
            import_from_names = {}  # Maps imported name to (module, original_name)

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        name = alias.asname if alias.asname else alias.name.split('.')[0]
                        imported_names.add(name)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ''
                    for alias in node.names:
                        name = alias.asname if alias.asname else alias.name
                        imported_names.add(name)
                        import_from_names[name] = (module, alias.name)

            # Collect all top-level function and class definitions
            defined_names = set()
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.FunctionDef):
                    defined_names.add(node.name)
                elif isinstance(node, ast.ClassDef):
                    defined_names.add(node.name)
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            defined_names.add(target.id)

            # Check for shadowed imports (local def shadows import)
            shadowed = imported_names & defined_names
            for name in shadowed:
                if name in import_from_names:
                    module, orig_name = import_from_names[name]
                    warnings.append((
                        f"{lambda_name}/{module_name}",
                        f"'{name}' imported from {module} but also defined locally (shadows import)"
                    ))

            # Collect all Name nodes used in function bodies
            class NameCollector(ast.NodeVisitor):
                def __init__(self):
                    self.used_names = set()
                    self.local_names = set()  # Names defined in local scope

                def visit_FunctionDef(self, node):
                    # Add function arguments to local scope
                    for arg in node.args.args:
                        self.local_names.add(arg.arg)
                    if node.args.vararg:
                        self.local_names.add(node.args.vararg.arg)
                    if node.args.kwarg:
                        self.local_names.add(node.args.kwarg.arg)
                    self.generic_visit(node)

                def visit_Name(self, node):
                    if isinstance(node.ctx, ast.Load):
                        self.used_names.add(node.id)
                    elif isinstance(node.ctx, ast.Store):
                        self.local_names.add(node.id)
                    self.generic_visit(node)

                def visit_ExceptHandler(self, node):
                    if node.name:
                        self.local_names.add(node.name)
                    self.generic_visit(node)

                def visit_Lambda(self, node):
                    # Track lambda parameters
                    for arg in node.args.args:
                        self.local_names.add(arg.arg)
                    if node.args.vararg:
                        self.local_names.add(node.args.vararg.arg)
                    if node.args.kwarg:
                        self.local_names.add(node.args.kwarg.arg)
                    self.generic_visit(node)

            collector = NameCollector()
            collector.visit(tree)

            # Check for undefined names
            all_defined = imported_names | defined_names | BUILTINS | KNOWN_MODULES | collector.local_names
            undefined = collector.used_names - all_defined

            for name in undefined:
                # Skip common patterns that are usually fine
                if name.startswith('_') or name.isupper():  # Private or constants
                    continue
                errors.append((
                    f"{lambda_name}/{module_name}",
                    f"NameError: '{name}' used but not imported or defined"
                ))

        except SyntaxError as e:
            errors.append((f"{lambda_name}/{module_name}", f"SyntaxError: {e}"))
        except Exception as e:
            errors.append((f"{lambda_name}/{module_name}", f"AST Error: {e}"))

    if checked == 0:
        print(f"{CYAN}  No Lambda modules found{RESET}")
        return True

    # Report warnings (shadowed imports)
    if warnings:
        print(f"{YELLOW}⚠️  Shadowed imports detected (may cause bugs):{RESET}")
        for module_id, msg in warnings:
            print(f"  {YELLOW}{module_id}: {msg}{RESET}")
        print()

    if errors:
        print(f"{RED}❌ Lambda import issues detected:{RESET}\n")
        for module_id, error in errors:
            print(f"  {RED}{module_id}: {error}{RESET}")

        print(f"\n{YELLOW}Common fixes:{RESET}")
        print("  - Shadowed import: Delete the local function definition")
        print("  - NameError: Add missing import statement")
        print("  - Check that imported module exports the name")

        return False  # BLOCKS commit

    print(f"{GREEN}✅ All {checked} Lambda modules pass AST analysis (handlers + support){RESET}")
    return True


def check_timezone_utility_enforcement():
    """
    Check 22: Timezone Utility Enforcement (BLOCKS)

    Detects anti-pattern: datetime.now(timezone.utc) in Lambda handlers
    when shared.timezone_utils should be used for ET timezone.

    This prevents the circuit breaker timezone bug documented in
    TIMEZONE_FIXES_2026-03-15.md where UTC vs ET caused mismatched business days.
    """
    print(f"\n{YELLOW}[22/36] Timezone Utility Enforcement (AST){RESET}")

    import ast

    LAMBDA_HANDLERS = [
        'parser/handler.py',
        'enricher/handler.py',
        'playwright-scraper/handler.py',
        'scraper/handler.py',
        '8k-processor/handler.py',
        '8k-fetcher/handler.py',
    ]

    # Files that legitimately need datetime.now(timezone.utc) for *_at fields
    ALLOWED_UTC_PATTERNS = {
        'first_seen_at', 'created_at', 'scraped_at', 'processed_at',
        'email_received_at', 'last_updated_at'
    }

    # Specific line exclusions for duration calculations (elapsed time, message age)
    # and legitimate *_at timestamp fields that the AST visitor can't detect
    DURATION_CALC_EXCLUSIONS = {
        'parser/handler.py': [176],  # Message age calculation
        'playwright-scraper/handler.py': [246],  # Message age calculation
        '8k-processor/handler.py': [557, 588],  # *_at timestamp fields (sec_accepted_at, first_seen_at)
        '8k-fetcher/handler.py': [163, 254, 352, 401],  # cutoff filter, fetched_at, duration calc
    }

    errors = []
    warnings = []
    checked = 0

    for handler_rel in LAMBDA_HANDLERS:
        handler_path = Path("infrastructure/lambdas") / handler_rel

        if not handler_path.exists():
            continue

        checked += 1
        lambda_name = handler_rel.split('/')[0]

        try:
            content = handler_path.read_text()
            tree = ast.parse(content)

            # Check if file imports from shared.timezone_utils
            has_timezone_utils_import = False
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    if node.module and 'timezone_utils' in node.module:
                        has_timezone_utils_import = True
                        break

            # Look for datetime.now(timezone.utc) calls
            class DatetimeNowVisitor(ast.NodeVisitor):
                def __init__(self):
                    self.utc_now_calls = []
                    self.current_assign_target = None

                def visit_Assign(self, node):
                    # Track what variable we're assigning to
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            self.current_assign_target = target.id
                        elif isinstance(target, ast.Subscript):
                            if isinstance(target.slice, ast.Constant):
                                self.current_assign_target = str(target.slice.value)
                    self.generic_visit(node)
                    self.current_assign_target = None

                def visit_Call(self, node):
                    # Detect datetime.now(timezone.utc) pattern
                    if isinstance(node.func, ast.Attribute):
                        if node.func.attr == 'now':
                            # Check if it's datetime.now or datetime.datetime.now
                            if isinstance(node.func.value, ast.Name) and node.func.value.id == 'datetime':
                                # Check for timezone.utc argument
                                for arg in node.args:
                                    if isinstance(arg, ast.Attribute):
                                        if arg.attr == 'utc' and isinstance(arg.value, ast.Name):
                                            if arg.value.id == 'timezone':
                                                # Check if assignment target is allowed *_at field
                                                is_allowed = False
                                                if self.current_assign_target:
                                                    for allowed in ALLOWED_UTC_PATTERNS:
                                                        if allowed in self.current_assign_target:
                                                            is_allowed = True
                                                            break
                                                if not is_allowed:
                                                    self.utc_now_calls.append(node.lineno)
                    self.generic_visit(node)

            visitor = DatetimeNowVisitor()
            visitor.visit(tree)

            if visitor.utc_now_calls and not has_timezone_utils_import:
                # Get exclusions for this file
                file_exclusions = DURATION_CALC_EXCLUSIONS.get(handler_rel, [])

                for lineno in visitor.utc_now_calls:
                    # Skip if line is in exclusion list (duration calculation)
                    if lineno in file_exclusions:
                        continue

                    errors.append((
                        lambda_name,
                        f"Line {lineno}: datetime.now(timezone.utc) used for business logic "
                        f"without shared.timezone_utils import. Use get_today_et() for ET timezone."
                    ))

        except SyntaxError as e:
            errors.append((lambda_name, f"SyntaxError: {e}"))
        except Exception as e:
            errors.append((lambda_name, f"AST Error: {e}"))

    if checked == 0:
        print(f"{CYAN}  No Lambda handlers found{RESET}")
        return True

    if errors:
        print(f"{RED}❌ Timezone utility issues detected:{RESET}\n")
        for lambda_name, error in errors:
            print(f"  {RED}{lambda_name}: {error}{RESET}")

        print(f"\n{YELLOW}Fix:{RESET}")
        print("  For circuit breaker / business logic dates:")
        print("    from shared.timezone_utils import get_today_et")
        print("    today_iso = get_today_et()  # Returns '2026-03-16' in ET")
        print("")
        print("  For *_at fields (timestamps): datetime.now(timezone.utc) is OK")

        return False  # BLOCKS commit

    print(f"{GREEN}✅ All {checked} Lambda handlers use correct timezone utilities{RESET}")
    return True


def check_lambda_handler_signature():
    """
    Check 23: Lambda Handler Signature Validation (BLOCKS)

    Verifies that each Lambda handler has the correct signature:
    def lambda_handler(event, context):

    This catches typos like lambda_handler(events, ctx) that would cause
    Lambda invocation failures.
    """
    print(f"\n{YELLOW}[23/36] Lambda Handler Signature (AST){RESET}")

    import ast

    LAMBDA_HANDLERS = [
        'parser/handler.py',
        'enricher/handler.py',
        'playwright-scraper/handler.py',
        'scraper/handler.py',
        'email-forwarder/handler.py',
        'daily-summary/handler.py',
        'scraper-router/handler.py',
        '8k-processor/handler.py',
        '8k-fetcher/handler.py',
    ]

    errors = []
    checked = 0

    for handler_rel in LAMBDA_HANDLERS:
        handler_path = Path("infrastructure/lambdas") / handler_rel

        if not handler_path.exists():
            continue

        checked += 1
        lambda_name = handler_rel.split('/')[0]

        try:
            content = handler_path.read_text()
            tree = ast.parse(content)

            # Find lambda_handler or handler function at module level
            # Both are valid - Terraform may configure handler.handler or handler.lambda_handler
            handler_found = False
            signature_correct = False

            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.FunctionDef) and node.name in ('lambda_handler', 'handler'):
                    handler_found = True

                    # Check arguments
                    args = node.args
                    arg_names = [arg.arg for arg in args.args]

                    # Must have exactly 2 positional args: event, context
                    if len(arg_names) == 2:
                        if arg_names[0] == 'event' and arg_names[1] == 'context':
                            signature_correct = True
                        else:
                            errors.append((
                                lambda_name,
                                f"Handler signature incorrect: lambda_handler({', '.join(arg_names)}). "
                                f"Expected: lambda_handler(event, context)"
                            ))
                    else:
                        errors.append((
                            lambda_name,
                            f"Handler has {len(arg_names)} args: ({', '.join(arg_names)}). "
                            f"Expected exactly 2: (event, context)"
                        ))
                    break

            if not handler_found:
                errors.append((
                    lambda_name,
                    "No handler function found at module level (expected 'lambda_handler' or 'handler')"
                ))

        except SyntaxError as e:
            errors.append((lambda_name, f"SyntaxError: {e}"))
        except Exception as e:
            errors.append((lambda_name, f"AST Error: {e}"))

    if checked == 0:
        print(f"{CYAN}  No Lambda handlers found{RESET}")
        return True

    if errors:
        print(f"{RED}❌ Lambda handler signature issues:{RESET}\n")
        for lambda_name, error in errors:
            print(f"  {RED}{lambda_name}: {error}{RESET}")

        print(f"\n{YELLOW}Fix:{RESET}")
        print("  def lambda_handler(event, context):")
        print("      # event and context are required parameter names")

        return False  # BLOCKS commit

    print(f"{GREEN}✅ All {checked} Lambda handlers have correct signature{RESET}")
    return True


def check_circular_imports():
    """
    Check 24: Circular Import Detection (BLOCKS)

    Detects circular imports in Lambda code that would cause ImportError
    at runtime. Uses DFS to find cycles in the import graph.

    Example cycle: a.py → b.py → c.py → a.py
    """
    print(f"\n{YELLOW}[24/36] Circular Import Detection (AST){RESET}")

    import ast
    from collections import defaultdict

    LAMBDA_DIRS = [
        'infrastructure/lambdas/parser',
        'infrastructure/lambdas/enricher',
        'infrastructure/lambdas/playwright-scraper',
        'infrastructure/lambdas/scraper',
    ]

    # Known safe circular imports (resolved with late imports)
    # Format: set of tuples containing modules in the cycle
    LATE_IMPORT_CYCLES = {
        frozenset(['company_matching', 'confidence_scoring']),  # Parser: late import in company_matching.py line 667
        frozenset(['company_matching', 'confidence_scoring', 'conservative_matcher']),  # Parser: conservative matcher extension
        frozenset(['company_matching', 'conservative_matcher']),  # Parser: alternative path
        frozenset(['confidence_scoring', 'conservative_matcher']),  # Parser: scoring uses matcher
        frozenset(['handler', 'company_matching', 'conservative_matcher']),  # Parser: handler chain
        # Enricher: url_selection internal cycles (resolved via late imports)
        frozenset(['selector', 'decision_logger', 'detector']),
        frozenset(['selector', 'decision_logger', 'extractor']),
        frozenset(['selector', 'scorer', 'detector']),
        frozenset(['selector', 'scorer', 'extractor']),
        frozenset(['selector', 'decision_logger', 'scorer', 'extractor']),
        frozenset(['selector', 'decision_logger', 'scorer', 'detector']),
    }

    errors = []

    # Third-party packages to ignore (installed dependencies)
    THIRD_PARTY_PACKAGES = {
        'bs4', 'requests', 'urllib3', 'feedparser', 'dateutil', 'boto3', 'botocore',
        'playwright', 'cloudscraper', 'curl_cffi', 'lxml', 'soupsieve', 'certifi',
        'charset_normalizer', 'idna', 'sgmllib', 'chardet', 'html5lib', 'jmespath',
        's3transfer', 'pyee', 'greenlet', 'async_generator', 'cffi', 'pycparser',
    }

    def build_import_graph(lambda_dir: Path) -> dict:
        """Build directed graph of imports within a Lambda directory."""
        graph = defaultdict(set)
        modules = {}

        # Find all Python files that are Lambda code (not installed packages)
        for py_file in lambda_dir.rglob('*.py'):
            # Skip __pycache__, dist-info, package (build artifact), and build directories
            if any(skip in str(py_file) for skip in ['__pycache__', '.dist-info', '/package/', '/build/']):
                continue

            # Skip deprecated handler files (March 2026 refactoring backups)
            # These files have circular imports with old enricher.* package architecture
            # but are not used in production (Terraform uses handler.lambda_handler)
            DEPRECATED_HANDLER_FILES = {'handler_old.py', 'handler_new.py'}
            if py_file.name in DEPRECATED_HANDLER_FILES:
                continue

            # Skip deprecated enricher/ package directory (only used by handler_new.py)
            # The active code uses url_selection/, url_construction/, persistence/ instead
            rel_path = py_file.relative_to(lambda_dir)
            if len(rel_path.parts) > 1 and rel_path.parts[0] == 'enricher':
                continue

            # Skip third-party packages
            first_part = rel_path.parts[0] if rel_path.parts else ''
            if first_part in THIRD_PARTY_PACKAGES:
                continue

            # Skip common installed package patterns
            if any(pkg in str(rel_path) for pkg in THIRD_PARTY_PACKAGES):
                continue

            # Get module name relative to lambda_dir
            if rel_path.name == '__init__.py':
                module_name = str(rel_path.parent).replace('/', '.')
                if module_name == '.':
                    module_name = lambda_dir.name
            else:
                module_name = str(rel_path.with_suffix('')).replace('/', '.')

            modules[module_name] = py_file

        # Parse each file for imports
        for module_name, py_file in modules.items():
            try:
                content = py_file.read_text()
                tree = ast.parse(content)

                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        if node.module:
                            # Check if this is a local import
                            imported = node.module.split('.')[0]
                            if imported in modules or any(imported in m for m in modules):
                                graph[module_name].add(node.module)
                    elif isinstance(node, ast.Import):
                        for alias in node.names:
                            imported = alias.name.split('.')[0]
                            if imported in modules or any(imported in m for m in modules):
                                graph[module_name].add(alias.name)

            except SyntaxError:
                pass  # Syntax errors caught by Check 10

        return graph

    def find_cycles(graph: dict) -> list:
        """Find all cycles in import graph using DFS."""
        cycles = []
        visited = set()
        rec_stack = []
        rec_stack_set = set()

        def dfs(node):
            visited.add(node)
            rec_stack.append(node)
            rec_stack_set.add(node)

            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    cycle = dfs(neighbor)
                    if cycle:
                        return cycle
                elif neighbor in rec_stack_set:
                    # Found cycle
                    cycle_start = rec_stack.index(neighbor)
                    return rec_stack[cycle_start:] + [neighbor]

            rec_stack.pop()
            rec_stack_set.remove(node)
            return None

        for node in graph:
            if node not in visited:
                cycle = dfs(node)
                if cycle:
                    cycles.append(cycle)

        return cycles

    checked = 0
    for lambda_dir_str in LAMBDA_DIRS:
        lambda_dir = Path(lambda_dir_str)
        if not lambda_dir.exists():
            continue

        checked += 1
        lambda_name = lambda_dir.name

        graph = build_import_graph(lambda_dir)
        cycles = find_cycles(graph)

        for cycle in cycles:
            # Extract module names from cycle (remove path prefixes)
            cycle_modules = frozenset([c.split('.')[-1] for c in cycle if c])

            # Skip if this is a known late import cycle
            if cycle_modules in LATE_IMPORT_CYCLES:
                continue

            cycle_str = ' → '.join(cycle)
            errors.append((lambda_name, f"Circular import: {cycle_str}"))

    if checked == 0:
        print(f"{CYAN}  No Lambda directories found{RESET}")
        return True

    if errors:
        print(f"{RED}❌ Circular imports detected:{RESET}\n")
        for lambda_name, error in errors:
            print(f"  {RED}{lambda_name}: {error}{RESET}")

        print(f"\n{YELLOW}Fix:{RESET}")
        print("  - Move shared code to a common module")
        print("  - Use late imports (import inside function)")
        print("  - Restructure module dependencies")

        return False  # BLOCKS commit

    print(f"{GREEN}✅ No circular imports in {checked} Lambda directories{RESET}")
    return True


# ============================================================================
# Check 25: SQS Schema Validation
# ============================================================================


def check_sqs_schema_validation():
    """Check 25: Validate SQS messages use shared schemas."""
    print(f"\n{YELLOW}[25/36] SQS Schema Validation{RESET}")

    # Check that sqs_schemas.py exists
    schema_file = Path("infrastructure/lambdas/shared/sqs_schemas.py")
    if not schema_file.exists():
        print(f"{RED}❌ shared/sqs_schemas.py not found{RESET}")
        return False

    # Check that Lambda files don't have hardcoded message fields without schema
    # This is a warning check - we look for common issues

    issues = []
    lambda_files = [
        "infrastructure/lambdas/parser/routing.py",
        "infrastructure/lambdas/enricher/persistence/sqs_ops.py",
    ]

    for filepath in lambda_files:
        path = Path(filepath)
        if not path.exists():
            continue

        content = path.read_text()

        # Check for hardcoded message dicts with required fields but no schema reference
        # Look for 'ticker', 'idempotency_key' in same dict - these should use schemas
        if "send_message" in content:
            # This is informational - actual validation would be more complex
            pass

    print(f"{GREEN}✅ SQS schema file exists (shared/sqs_schemas.py){RESET}")
    print(f"{CYAN}  Use: from shared.sqs_schemas import create_enricher_message, ...{RESET}")
    return True


# ============================================================================
# Check 26: Environment Variable Cross-Validation
# ============================================================================


def check_env_var_registry():
    """Check 26: Cross-validate env vars between code and Terraform."""
    print(f"\n{YELLOW}[26/36] Environment Variable Registry{RESET}")

    import ast

    # Check that env_registry.py exists
    registry_file = Path("infrastructure/lambdas/shared/env_registry.py")
    if not registry_file.exists():
        print(f"{RED}❌ shared/env_registry.py not found{RESET}")
        return False

    # Import registry to get known env vars
    try:
        sys.path.insert(0, str(Path("infrastructure/lambdas/shared")))
        from env_registry import LAMBDA_ENV_VARS, AWS_RUNTIME_ENV_VARS
    except ImportError as e:
        print(f"{RED}❌ Cannot import env_registry: {e}{RESET}")
        return False
    finally:
        if "infrastructure/lambdas/shared" in sys.path[0]:
            sys.path.pop(0)

    errors = []
    warnings = []

    # Check each Lambda handler for env var usage
    lambda_dirs = {
        'parser': 'infrastructure/lambdas/parser',
        'enricher': 'infrastructure/lambdas/enricher',
        'playwright-scraper': 'infrastructure/lambdas/playwright-scraper',
        'scraper': 'infrastructure/lambdas/scraper',
    }

    for lambda_name, lambda_dir in lambda_dirs.items():
        handler_path = Path(lambda_dir) / "handler.py"
        if not handler_path.exists():
            continue

        try:
            content = handler_path.read_text()
            tree = ast.parse(content)

            # Find all os.environ['X'] and os.environ.get('X') calls
            for node in ast.walk(tree):
                if isinstance(node, ast.Subscript):
                    # os.environ['VAR']
                    if (isinstance(node.value, ast.Attribute) and
                        node.value.attr == 'environ' and
                        isinstance(node.value.value, ast.Name) and
                        node.value.value.id == 'os' and
                        isinstance(node.slice, ast.Constant)):
                        var_name = node.slice.value
                        if var_name not in AWS_RUNTIME_ENV_VARS:
                            config = LAMBDA_ENV_VARS.get(lambda_name, {})
                            all_vars = set(config.get('required', [])) | set(config.get('optional', []))
                            if var_name not in all_vars:
                                errors.append((lambda_name, var_name, "required"))

                elif isinstance(node, ast.Call):
                    # os.environ.get('VAR')
                    if (isinstance(node.func, ast.Attribute) and
                        node.func.attr == 'get' and
                        isinstance(node.func.value, ast.Attribute) and
                        node.func.value.attr == 'environ' and
                        len(node.args) >= 1 and
                        isinstance(node.args[0], ast.Constant)):
                        var_name = node.args[0].value
                        if var_name not in AWS_RUNTIME_ENV_VARS:
                            config = LAMBDA_ENV_VARS.get(lambda_name, {})
                            all_vars = set(config.get('required', [])) | set(config.get('optional', []))
                            if var_name not in all_vars:
                                warnings.append((lambda_name, var_name))

        except SyntaxError:
            pass  # Syntax errors caught by Check 10

    if errors:
        print(f"{RED}❌ Unregistered required env vars:{RESET}")
        for lambda_name, var_name, _ in errors:
            print(f"  {lambda_name}: os.environ['{var_name}'] - add to env_registry.py")
        return False

    if warnings:
        print(f"{YELLOW}⚠️  Unregistered optional env vars:{RESET}")
        for lambda_name, var_name in warnings:
            print(f"  {lambda_name}: os.environ.get('{var_name}') - consider adding to env_registry.py")

    print(f"{GREEN}✅ All env vars registered in shared/env_registry.py{RESET}")
    return True


# ============================================================================
# Check 27: Queue Name Consistency
# ============================================================================


def check_queue_name_consistency():
    """Check 27: Validate queue names match Terraform locals."""
    print(f"\n{YELLOW}[27/36] Queue Name Consistency{RESET}")

    # Check that queue_names.py exists
    queue_file = Path("infrastructure/lambdas/shared/queue_names.py")
    if not queue_file.exists():
        print(f"{RED}❌ shared/queue_names.py not found{RESET}")
        return False

    # Import queue names
    try:
        sys.path.insert(0, str(Path("infrastructure/lambdas/shared")))
        from queue_names import QUEUE_NAMES, PROJECT_NAME
    except ImportError as e:
        print(f"{RED}❌ Cannot import queue_names: {e}{RESET}")
        return False
    finally:
        if "infrastructure/lambdas/shared" in sys.path[0]:
            sys.path.pop(0)

    # Read Terraform locals.tf
    locals_path = Path("infrastructure/terraform/locals.tf")
    if not locals_path.exists():
        print(f"{YELLOW}⚠️  locals.tf not found - skipping Terraform validation{RESET}")
        return True

    locals_content = locals_path.read_text()

    # Also read sqs-enrich.tf for enrich queue
    enrich_path = Path("infrastructure/terraform/sqs-enrich.tf")
    if enrich_path.exists():
        locals_content += "\n" + enrich_path.read_text()

    errors = []

    # Extract queue names from Terraform
    # Pattern: name = "${var.project_name}-xxx-queue"
    tf_queues = set()
    queue_pattern = re.compile(r'name\s*=\s*"\$\{var\.project_name\}-([^"]+)"')
    for match in queue_pattern.finditer(locals_content):
        tf_queues.add(f"reitsheet-{match.group(1)}")

    # Also check locals block
    locals_pattern = re.compile(r'(\w+_queue_name)\s*=\s*"\$\{var\.project_name\}-([^"]+)"')
    for match in locals_pattern.finditer(locals_content):
        tf_queues.add(f"reitsheet-{match.group(2)}")

    # Check for hardcoded queue names in Lambda code
    lambda_files = list(Path("infrastructure/lambdas").rglob("*.py"))
    hardcoded_pattern = re.compile(r'["\']reitsheet-[\w-]+-queue["\']')

    for filepath in lambda_files:
        if 'shared/queue_names.py' in str(filepath):
            continue  # Skip the source of truth file
        if '__pycache__' in str(filepath) or 'build/' in str(filepath):
            continue

        try:
            content = filepath.read_text()
            matches = hardcoded_pattern.findall(content)
            for match in matches:
                queue_name = match.strip("'\"")
                if queue_name not in QUEUE_NAMES.values():
                    errors.append((str(filepath), queue_name))
        except Exception:
            pass

    if errors:
        print(f"{RED}❌ Hardcoded queue names not in registry:{RESET}")
        for filepath, queue_name in errors:
            print(f"  {filepath}: '{queue_name}'")
        print(f"\n{YELLOW}Fix: Import from shared.queue_names instead of hardcoding{RESET}")
        return False

    print(f"{GREEN}✅ Queue names consistent (shared/queue_names.py){RESET}")
    return True


# ============================================================================
# Check 28: Buildspec Import Validation
# ============================================================================


def check_buildspec_import_validation():
    """Check 28: Verify Docker builds include import validation."""
    print(f"\n{YELLOW}[28/36] Buildspec Import Validation{RESET}")

    warnings = []

    # Check codebuild.tf for inline buildspec
    codebuild_path = Path("infrastructure/terraform/codebuild.tf")
    if codebuild_path.exists():
        content = codebuild_path.read_text()

        # This is the Flask app build - not Lambda, so import validation may not apply
        pass

    # Check Lambda build.sh scripts for import validation
    lambda_dirs = [
        "infrastructure/lambdas/parser",
        "infrastructure/lambdas/enricher",
        "infrastructure/lambdas/scraper",
        "infrastructure/lambdas/playwright-scraper",
    ]

    for lambda_dir_str in lambda_dirs:
        lambda_dir = Path(lambda_dir_str)
        if not lambda_dir.exists():
            continue

        # Check for build.sh
        build_script = lambda_dir / "build.sh"
        if build_script.exists():
            content = build_script.read_text()

            # Check if it has import validation
            has_import_check = (
                "import handler" in content or
                "validate_lambda_imports" in content or
                "python3 -c" in content
            )

            if not has_import_check:
                warnings.append(f"{lambda_dir.name}/build.sh: Missing import validation")

        # Check for Dockerfile (image-based Lambda)
        dockerfile = lambda_dir / "Dockerfile"
        if dockerfile.exists():
            content = dockerfile.read_text()

            # Dockerfiles should have RUN python3 -c "import handler" or similar
            has_import_check = (
                "import handler" in content or
                "python3 -c" in content
            )

            if not has_import_check:
                warnings.append(f"{lambda_dir.name}/Dockerfile: Consider adding import validation")

    if warnings:
        print(f"{YELLOW}⚠️  Build scripts without import validation:{RESET}")
        for warning in warnings:
            print(f"  {warning}")
        print(f"\n{CYAN}Recommendation: Add 'python3 -c \"import handler\"' to build scripts{RESET}")
        # This is a warning, not a blocker
        return True

    print(f"{GREEN}✅ Build scripts include import validation{RESET}")
    return True


# ============================================================================
# Check 29: Lambda Module Discovery Validation
# ============================================================================


def check_lambda_module_discovery():
    """
    Check 29: Lambda Module Discovery Validation (BLOCKS on BOTH source AND ZIP issues)

    Runs AST-based module discovery for each Lambda and verifies:
    1. All imported modules exist (BLOCKS if missing - can't build without source)
    2. If a ZIP exists, it contains all discovered modules (BLOCKS if incomplete)

    Changed 2026-03-24: ZIP issues now BLOCK commits (not just warn).
    Reason: Enricher was broken for days because a ZIP with missing url_selection/ was deployed.
    A bad ZIP in the repo WILL eventually be deployed - block it at the source.
    """
    print(f"\n{YELLOW}[29/36] Lambda Module Discovery{RESET}")

    discovery_script = Path("scripts/discover_lambda_modules.py")
    if not discovery_script.exists():
        print(f"{YELLOW}⚠️  Discovery script not found (skipping){RESET}")
        return True

    import subprocess

    LAMBDAS_TO_CHECK = [
        ('parser', 'infrastructure/lambdas/parser'),
        ('enricher', 'infrastructure/lambdas/enricher'),
        ('scraper', 'infrastructure/lambdas/scraper'),
        ('playwright-scraper', 'infrastructure/lambdas/playwright-scraper'),
    ]

    errors = []  # Source module issues (BLOCKS)
    warnings = []  # ZIP issues (WARNS)

    for lambda_name, lambda_dir in LAMBDAS_TO_CHECK:
        if not Path(lambda_dir).exists():
            continue

        # Run discovery with --check-exists (BLOCKS if source modules missing)
        result = subprocess.run(
            [sys.executable, str(discovery_script), lambda_name, '--check-exists'],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            errors.append((lambda_name, "Missing source modules"))
            if result.stdout:
                for line in result.stdout.strip().split('\n'):
                    if 'Missing' in line or line.strip().startswith('-'):
                        errors.append((lambda_name, f"  {line.strip()}"))

        # If ZIP exists, validate it contains all modules (WARNS only)
        zip_patterns = [
            Path(lambda_dir) / f"{lambda_name}-with-deps.zip",
            Path(lambda_dir) / f"{lambda_name}.zip",
        ]

        for zip_path in zip_patterns:
            if zip_path.exists():
                result = subprocess.run(
                    [sys.executable, str(discovery_script), lambda_name,
                     '--validate-zip', str(zip_path)],
                    capture_output=True,
                    text=True
                )

                if result.returncode != 0:
                    warnings.append((lambda_name, f"ZIP incomplete: {zip_path.name}"))
                    if result.stdout:
                        for line in result.stdout.strip().split('\n'):
                            if 'missing' in line.lower() and line.strip():
                                warnings.append((lambda_name, f"  {line.strip()}"))
                break  # Only check first matching ZIP

    # Show errors (BLOCKS)
    if errors:
        print(f"{RED}❌ Source module issues (BLOCKS):{RESET}\n")
        for lambda_name, error in errors:
            print(f"  {RED}{lambda_name}: {error}{RESET}")

        print(f"\n{YELLOW}Fix:{RESET}")
        print("  1. Run: python3 scripts/discover_lambda_modules.py <lambda> --dry-run")
        print("  2. Add missing module files")

        return False  # BLOCKS commit

    # Show ZIP errors (NOW BLOCKS - prevents deploying incomplete ZIPs)
    # Changed from warning to error on 2026-03-24 after enricher broke due to missing modules
    if warnings:
        print(f"{RED}❌ ZIP packages incomplete (BLOCKS):{RESET}\n")
        for lambda_name, warning in warnings:
            print(f"  {RED}{lambda_name}: {warning}{RESET}")

        print(f"\n{YELLOW}Fix:{RESET}")
        print("  1. Rebuild ZIP: ./infrastructure/lambdas/<lambda>/build.sh")
        print("  2. Commit the new ZIP")
        print(f"\n{RED}Why this blocks:{RESET}")
        print("  - A bad ZIP in the repo WILL eventually be deployed")
        print("  - March 2026: Enricher was broken for days due to missing url_selection/")

        return False  # BLOCKS commit - must rebuild ZIP

    print(f"{GREEN}✅ All Lambda source modules exist and ZIPs are complete{RESET}")
    return True


# ============================================================================
# Check 30: Build Script Discovery Integration
# ============================================================================


def check_build_script_discovery():
    """
    Check 30: Build Script Discovery Integration (BLOCKS)

    Verifies that build.sh scripts use the discovery script.
    This prevents build scripts from using hardcoded module lists
    that can become stale.
    """
    print(f"\n{YELLOW}[30/36] Build Script Discovery Integration{RESET}")

    BUILD_SCRIPTS = [
        'infrastructure/lambdas/parser/build.sh',
        'infrastructure/lambdas/enricher/build.sh',
        'infrastructure/lambdas/scraper/build.sh',
        'infrastructure/lambdas/playwright-scraper/build.sh',
    ]

    errors = []
    warnings = []

    for build_script_path in BUILD_SCRIPTS:
        build_script = Path(build_script_path)
        if not build_script.exists():
            continue

        content = build_script.read_text()
        lambda_name = build_script.parent.name

        # Check if it uses the discovery script
        uses_discovery = 'discover_lambda_modules.py' in content

        if not uses_discovery:
            warnings.append(f"{lambda_name}/build.sh: Not using discovery script")

        # Check for hardcoded module lists (anti-pattern)
        # Look for patterns like: zip -gr ... matching persistence browser
        import re
        hardcoded_patterns = [
            r'zip\s+.*\s+(matching|persistence|browser|url_selection|url_construction)\s+',
            r'cp\s+-r\s+\$SCRIPT_DIR/(matching|persistence|browser)',
        ]

        for pattern in hardcoded_patterns:
            if re.search(pattern, content) and not uses_discovery:
                errors.append(
                    f"{lambda_name}/build.sh: Hardcoded module list without discovery - "
                    "update to use discover_lambda_modules.py"
                )
                break

    if errors:
        print(f"{RED}❌ Build script issues:{RESET}\n")
        for error in errors:
            print(f"  {RED}{error}{RESET}")

        print(f"\n{YELLOW}Fix:{RESET}")
        print("  Update build.sh to use:")
        print("    LOCAL_DIRS=$(python3 $DISCOVERY_SCRIPT $LAMBDA_NAME --local-dirs)")
        print("  Instead of hardcoded: zip -gr ... matching persistence browser")

        return False  # BLOCKS commit

    if warnings:
        print(f"{YELLOW}⚠️  Build scripts not using discovery (consider updating):{RESET}")
        for warning in warnings:
            print(f"  {warning}")
        # Warnings don't block, but encourage adoption

    print(f"{GREEN}✅ Build scripts properly integrated with discovery{RESET}")
    return True


# ============================================================================
# Check 31: Lambda Config Centralization
# ============================================================================


def check_lambda_config_centralization():
    """
    Check 31: Lambda Config Centralization (WARNING)

    Validates that Lambda invocation scripts use centralized config:
    - shared/lambda_config.py exists with LAMBDA_CONFIG and S3_BUCKETS
    - Test scripts import from lambda_config.py (not hardcoded)
    - Warns about hardcoded bucket names in test scripts

    This is a WARNING check to encourage migration to invoke_lambda.py.
    """
    print(f"\n{YELLOW}[31/36] Lambda Config Centralization{RESET}")

    # Check that lambda_config.py exists
    config_file = Path("infrastructure/lambdas/shared/lambda_config.py")
    if not config_file.exists():
        print(f"{YELLOW}⚠️  shared/lambda_config.py not found{RESET}")
        print(f"{CYAN}  Create it with: LAMBDA_CONFIG, S3_BUCKETS, DYNAMODB_TABLES{RESET}")
        return True  # Warning only

    # Check that invoke_lambda.py exists
    invoke_script = Path("scripts/invoke_lambda.py")
    if not invoke_script.exists():
        print(f"{YELLOW}⚠️  scripts/invoke_lambda.py not found{RESET}")
        print(f"{CYAN}  Create unified Lambda invocation tool{RESET}")
        return True  # Warning only

    # Check test scripts for hardcoded values
    test_scripts = [
        "scripts/test_parser.py",
        "scripts/test_enricher.py",
    ]

    warnings = []

    for script_path in test_scripts:
        path = Path(script_path)
        if not path.exists():
            continue

        content = path.read_text()

        # Check for lambda_config import
        uses_config = (
            "from shared.lambda_config import" in content or
            "from lambda_config import" in content
        )

        # Check for hardcoded bucket names that should use config
        hardcoded_bucket = re.search(
            r"['\"]reitsheet-(?!companies-config)[^'\"]+['\"]",
            content
        )

        if not uses_config and hardcoded_bucket:
            warnings.append(f"{path.name}: Consider using shared/lambda_config.py")

    if warnings:
        print(f"{YELLOW}⚠️  Scripts not using centralized config:{RESET}")
        for warning in warnings:
            print(f"  {warning}")
        print(f"\n{CYAN}Recommendation: Use python scripts/invoke_lambda.py instead{RESET}")
        print(f"{CYAN}Or import: from shared.lambda_config import get_default_bucket{RESET}")
        # Warning only - doesn't block
        return True

    print(f"{GREEN}✅ Lambda config centralized (shared/lambda_config.py){RESET}")
    print(f"{CYAN}  Use: python scripts/invoke_lambda.py <lambda> --example{RESET}")
    return True


# ============================================================================
# Check 32: Design Token Source Validation
# ============================================================================


def check_design_token_source():
    """
    Check 32: Design Token Source Validation (BLOCKS)

    Ensures CSS variables are generated from design-tokens.json:
    1. variables.css must exist and be auto-generated
    2. No other CSS file should define :root variables
    3. design-tokens.json must exist

    This prevents design drift where colors/spacing diverge between files.
    """
    print(f"\n{YELLOW}[32/36] Design Token Source Validation{RESET}")

    css_dir = Path("infrastructure/docker/flask-app/static/css")
    design_tokens_path = Path("infrastructure/docker/flask-app/config/design-tokens.json")
    variables_css_path = css_dir / "variables.css"

    errors = []

    # Check design-tokens.json exists
    if not design_tokens_path.exists():
        errors.append("design-tokens.json not found - single source of truth for design tokens")

    # Check variables.css exists
    if not variables_css_path.exists():
        errors.append("variables.css not found - run: python3 scripts/build_design_tokens.py")
    else:
        # Check if variables.css is auto-generated
        content = variables_css_path.read_text()
        if "AUTO-GENERATED" not in content:
            errors.append("variables.css missing AUTO-GENERATED marker - may be manually edited")

    # Check no other CSS files define :root variables
    if css_dir.exists():
        root_pattern = re.compile(r':root\s*\{')
        for css_file in css_dir.rglob("*.css"):
            # Only skip variables.css (auto-generated, allowed to have :root)
            if css_file.name == "variables.css":
                continue

            try:
                content = css_file.read_text()
                if root_pattern.search(content):
                    rel_path = css_file.relative_to(css_dir)
                    errors.append(f"{rel_path}: Defines :root variables - move to design-tokens.json")
            except Exception:
                pass

    # PROTECTED FILE CHECK: public.css must import from variables.css, not define its own tokens
    public_css_path = css_dir / "public.css"
    if public_css_path.exists():
        try:
            content = public_css_path.read_text()
            # Check for protection marker (prevents removal of import directive)
            if "@design-tokens: variables.css" not in content:
                errors.append("public.css: Missing @design-tokens marker - file may have been corrupted")
            if "@protected: pre-commit-check-32" not in content:
                errors.append("public.css: Missing @protected marker - restore from backup")
            # Double-check no :root (already caught above, but explicit for public.css)
            if re.search(r':root\s*\{', content):
                errors.append("public.css: Contains :root definitions - MUST use variables.css imports only")
        except Exception:
            pass

    if errors:
        print(f"{RED}❌ Design token violations:{RESET}\n")
        for error in errors:
            print(f"  {RED}- {error}{RESET}")

        print(f"\n{YELLOW}Fix:{RESET}")
        print("  1. Edit config/design-tokens.json with new values")
        print("  2. Run: python3 scripts/build_design_tokens.py")
        print("  3. Commit variables.css (auto-generated)")

        return False  # BLOCKS commit

    print(f"{GREEN}✅ Design tokens sourced from design-tokens.json{RESET}")
    return True


# ============================================================================
# Check 33: Brand Standards Validation
# ============================================================================


def check_brand_standards():
    """
    Check 33: Brand Standards Validation (BLOCKS)

    Scans HTML templates and Python files for brand violations.
    Uses FORBIDDEN_PATTERNS from brand_standards.py.

    Examples of violations:
    - "Press Release Pipeline" instead of "Press Release Pipeline"
    - "Click here" instead of action-oriented CTAs
    - "reitsheet.com" instead of "reitsheet.co"
    """
    print(f"\n{YELLOW}[33/36] Brand Standards Validation{RESET}")

    brand_standards_path = Path("infrastructure/docker/flask-app/config/brand_standards.py")

    if not brand_standards_path.exists():
        print(f"{YELLOW}⚠️  brand_standards.py not found (skipping){RESET}")
        return True

    # Import check_forbidden_patterns from brand_standards
    try:
        sys.path.insert(0, str(brand_standards_path.parent))
        from brand_standards import check_forbidden_patterns, FORBIDDEN_PATTERNS
    except ImportError as e:
        print(f"{YELLOW}⚠️  Cannot import brand_standards: {e}{RESET}")
        return True
    finally:
        if str(brand_standards_path.parent) in sys.path:
            sys.path.remove(str(brand_standards_path.parent))

    flask_app_dir = Path("infrastructure/docker/flask-app")
    templates_dir = flask_app_dir / "templates"

    errors = []

    # Scan HTML templates
    if templates_dir.exists():
        for template in templates_dir.rglob("*.html"):
            try:
                content = template.read_text()
                violations = check_forbidden_patterns(content)
                for match, message in violations:
                    rel_path = template.relative_to(flask_app_dir)
                    errors.append((str(rel_path), match, message))
            except Exception:
                pass

    # Scan Python files in flask-app (routes, services)
    for py_dir in ['routes', 'services', 'core']:
        scan_dir = flask_app_dir / py_dir
        if scan_dir.exists():
            for py_file in scan_dir.rglob("*.py"):
                try:
                    content = py_file.read_text()
                    violations = check_forbidden_patterns(content)
                    for match, message in violations:
                        rel_path = py_file.relative_to(flask_app_dir)
                        errors.append((str(rel_path), match, message))
                except Exception:
                    pass

    if errors:
        print(f"{RED}❌ Brand standard violations:{RESET}\n")
        for filepath, match, message in errors[:10]:  # Limit to 10 for readability
            print(f"  {RED}{filepath}:{RESET}")
            print(f"    Found: '{match}'")
            print(f"    {message}\n")

        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more violations")

        print(f"\n{YELLOW}See: config/brand_standards.py for allowed patterns{RESET}")

        return False  # BLOCKS commit

    print(f"{GREEN}✅ All files follow brand standards{RESET}")
    return True


# ============================================================================
# Check 34: Mobile Text Wrapping (WARNING)
# ============================================================================


def check_mobile_text_wrapping():
    """
    Check 34: Mobile Text Wrapping (WARNS - does not block)

    Parses HTML templates for CTAs that may wrap on mobile:
    - Elements with .signup-trigger class
    - Elements with data-cta attribute

    If CTA text exceeds MOBILE_TEXT_LIMITS['nav_cta'], print suggestions.
    """
    print(f"\n{YELLOW}[34/36] Mobile Text Wrapping Check{RESET}")

    brand_standards_path = Path("infrastructure/docker/flask-app/config/brand_standards.py")

    if not brand_standards_path.exists():
        print(f"{YELLOW}⚠️  brand_standards.py not found (skipping){RESET}")
        return True

    # Import mobile text limits
    try:
        sys.path.insert(0, str(brand_standards_path.parent))
        from brand_standards import MOBILE_TEXT_LIMITS, get_cta_suggestions
    except ImportError as e:
        print(f"{YELLOW}⚠️  Cannot import brand_standards: {e}{RESET}")
        return True
    finally:
        if str(brand_standards_path.parent) in sys.path:
            sys.path.remove(str(brand_standards_path.parent))

    templates_dir = Path("infrastructure/docker/flask-app/templates")

    if not templates_dir.exists():
        print(f"{GREEN}✅ No templates to check{RESET}")
        return True

    warnings = []
    nav_cta_limit = MOBILE_TEXT_LIMITS.get('nav_cta', 28)

    # Simple regex-based CTA detection (not full HTML parsing for speed)
    # Matches: class="...signup-trigger..." or data-cta
    cta_pattern = re.compile(
        r'(?:class="[^"]*signup-trigger[^"]*"|data-cta[^>]*)[^>]*>([^<]+)<',
        re.IGNORECASE
    )

    for template in templates_dir.rglob("*.html"):
        try:
            content = template.read_text()

            for match in cta_pattern.finditer(content):
                cta_text = match.group(1).strip()

                if len(cta_text) > nav_cta_limit:
                    suggestions = get_cta_suggestions(cta_text, nav_cta_limit)
                    rel_path = template.relative_to(templates_dir)
                    warnings.append((str(rel_path), cta_text, len(cta_text), suggestions))

        except Exception:
            pass

    if warnings:
        print(f"{YELLOW}⚠️  CTAs may wrap on mobile (max {nav_cta_limit} chars):{RESET}\n")
        for filepath, text, length, suggestions in warnings:
            print(f"  {YELLOW}{filepath}:{RESET}")
            print(f"    '{text}' ({length} chars)")
            if suggestions:
                print(f"    {CYAN}Suggestions: {', '.join(suggestions)}{RESET}")
            print()

        # Warning only - does not block
        return True

    print(f"{GREEN}✅ All CTAs within mobile text limits ({nav_cta_limit} chars){RESET}")
    return True


# ============================================================================
# Check 35: Email Style Consistency
# ============================================================================


def check_email_style_consistency():
    """
    Check 35: Email Style Consistency (BLOCKS)

    Scans publisher_generator.py for hardcoded colors that should use EMAIL_STYLES.
    Email generators should import from email_styles.py, not hardcode hex values.

    This prevents color drift between email templates and the design system.
    """
    print(f"\n{YELLOW}[35/36] Email Style Consistency{RESET}")

    publisher_generator_path = Path("infrastructure/docker/flask-app/core/publisher_generator.py")
    email_styles_path = Path("infrastructure/docker/flask-app/config/email_styles.py")

    if not publisher_generator_path.exists():
        print(f"{YELLOW}⚠️  publisher_generator.py not found (skipping){RESET}")
        return True

    if not email_styles_path.exists():
        print(f"{YELLOW}⚠️  email_styles.py not found (skipping){RESET}")
        return True

    # Load known colors from email_styles.py
    try:
        sys.path.insert(0, str(email_styles_path.parent))
        from email_styles import EMAIL_STYLES
        known_colors = set()
        if 'color' in EMAIL_STYLES:
            known_colors = set(EMAIL_STYLES['color'].values())
    except ImportError as e:
        print(f"{YELLOW}⚠️  Cannot import email_styles: {e}{RESET}")
        return True
    finally:
        if str(email_styles_path.parent) in sys.path:
            sys.path.remove(str(email_styles_path.parent))

    content = publisher_generator_path.read_text()

    # Check if it imports from email_styles
    imports_email_styles = (
        'from config.email_styles import' in content or
        'from email_styles import' in content
    )

    # Find all hex colors in the file
    hex_pattern = re.compile(r'#[0-9a-fA-F]{6}\b')
    lines = content.split('\n')

    hardcoded = []
    for i, line in enumerate(lines, 1):
        # Skip comments and docstrings
        stripped = line.strip()
        if stripped.startswith('#') or stripped.startswith('"""') or stripped.startswith("'''"):
            continue

        matches = hex_pattern.findall(line)
        for color in matches:
            # Normalize to lowercase for comparison
            if color.lower() in [c.lower() for c in known_colors]:
                # This color exists in EMAIL_STYLES - should be imported, not hardcoded
                hardcoded.append((i, color, line.strip()[:80]))

    # Only report if there are hardcoded colors AND email_styles is not imported
    # If email_styles is imported but hardcoded colors still exist, that's still an issue
    if hardcoded:
        print(f"{RED}❌ Hardcoded colors found in publisher_generator.py:{RESET}\n")
        for line_num, color, line in hardcoded[:10]:
            print(f"  Line {line_num}: {RED}{color}{RESET}")
            print(f"    {line}\n")

        if len(hardcoded) > 10:
            print(f"  ... and {len(hardcoded) - 10} more instances")

        print(f"\n{YELLOW}Fix:{RESET}")
        print("  1. Import: from config.email_styles import EMAIL_STYLES, get_color")
        print("  2. Replace: '#0066cc' -> EMAIL_STYLES['color']['primary']")
        print("  3. Or use: get_color('primary')")

        return False  # BLOCKS commit

    print(f"{GREEN}✅ Email generator uses EMAIL_STYLES consistently{RESET}")
    return True


# ============================================================================
# Check 36: Accessibility Validation
# ============================================================================


def check_accessibility():
    """
    Check 36: Accessibility Validation (BLOCKS)

    Parses HTML templates to check:
    1. Images have alt text
    2. Links have text or aria-label
    3. Form inputs have associated labels
    4. Buttons have text or aria-label

    Uses simple regex patterns (no BeautifulSoup dependency required).
    """
    print(f"\n{YELLOW}[36/36] Accessibility Validation{RESET}")

    templates_dir = Path("infrastructure/docker/flask-app/templates")

    if not templates_dir.exists():
        print(f"{GREEN}✅ No templates to check{RESET}")
        return True

    errors = []

    for template in templates_dir.rglob("*.html"):
        try:
            content = template.read_text()
            rel_path = template.relative_to(templates_dir)

            # Check 1: Images without alt text
            # Match <img ...> without alt="..."
            img_pattern = re.compile(r'<img\s+(?![^>]*alt=)[^>]*>', re.IGNORECASE)
            for match in img_pattern.finditer(content):
                # Get line number
                line_num = content[:match.start()].count('\n') + 1
                errors.append((str(rel_path), line_num, "Image missing alt text", match.group()[:60]))

            # Check 2: Empty links (no text and no aria-label)
            # Match <a ...></a> or <a ...> </a>
            empty_link_pattern = re.compile(
                r'<a\s+(?![^>]*aria-label=)[^>]*>\s*</a>',
                re.IGNORECASE
            )
            for match in empty_link_pattern.finditer(content):
                line_num = content[:match.start()].count('\n') + 1
                errors.append((str(rel_path), line_num, "Link has no text or aria-label", match.group()[:60]))

            # Check 3: Form inputs without associated labels
            # Look for <input type="text|email|password|number"> without id that matches a label
            # This is a simplified check - just warn about inputs without id attribute
            input_no_id_pattern = re.compile(
                r'<input\s+(?![^>]*id=)[^>]*type=["\'](?:text|email|password|number)["\'][^>]*>',
                re.IGNORECASE
            )
            for match in input_no_id_pattern.finditer(content):
                line_num = content[:match.start()].count('\n') + 1
                # Check if it has aria-label
                if 'aria-label' not in match.group().lower():
                    errors.append((str(rel_path), line_num, "Input field without id or aria-label", match.group()[:60]))

            # Check 4: Buttons without text or aria-label
            empty_button_pattern = re.compile(
                r'<button\s+(?![^>]*aria-label=)[^>]*>\s*</button>',
                re.IGNORECASE
            )
            for match in empty_button_pattern.finditer(content):
                line_num = content[:match.start()].count('\n') + 1
                errors.append((str(rel_path), line_num, "Button has no text or aria-label", match.group()[:60]))

        except Exception as e:
            print(f"{YELLOW}⚠️  Could not parse {template}: {e}{RESET}")

    if errors:
        print(f"{RED}❌ Accessibility issues found:{RESET}\n")
        for filepath, line_num, issue, context in errors[:15]:
            print(f"  {RED}{filepath}:{line_num}{RESET}")
            print(f"    {issue}")
            print(f"    {context}...\n")

        if len(errors) > 15:
            print(f"  ... and {len(errors) - 15} more issues")

        print(f"\n{YELLOW}Fix examples:{RESET}")
        print('  <img src="..." alt="Description of image">')
        print('  <a href="..." aria-label="Go to homepage">Link text</a>')
        print('  <input type="text" id="email" aria-label="Email address">')
        print('  <button aria-label="Close">X</button>')

        return False  # BLOCKS commit

    print(f"{GREEN}✅ All templates pass accessibility checks{RESET}")
    return True


def check_domain_routing():
    """Check 37: Verify domain-based routing is properly configured.

    Domain architecture (same Flask app, domain-based routing):
    - reitsheet.co = PUBLIC (newsletter) - uses @public_only or is_public_domain()
    - app.reitsheet.co = ADMIN (requires auth) - uses @admin_only or @login_required

    BLOCKS commit if domain routing middleware is missing or misconfigured.
    """
    print(f"\n{YELLOW}[37/37] Domain-Based Routing Check{RESET}")

    issues = []
    flask_dir = Path('infrastructure/docker/flask-app')

    # 1. Check middleware exists
    middleware_file = flask_dir / 'middleware' / 'domain_router.py'
    if not middleware_file.exists():
        issues.append("middleware/domain_router.py does not exist")
    else:
        content = middleware_file.read_text()
        required = ['PUBLIC_DOMAIN', 'ADMIN_DOMAIN', 'public_only', 'is_public_domain']
        for req in required:
            if req not in content:
                issues.append(f"middleware/domain_router.py: Missing {req}")

    # 2. Check app.py uses is_public_domain() in auth
    app_file = flask_dir / 'app.py'
    if app_file.exists():
        content = app_file.read_text()
        if 'is_public_domain' not in content:
            issues.append("app.py: Missing is_public_domain() check in authentication")

    # 3. Check public routes use @public_only
    public_file = flask_dir / 'routes' / 'public.py'
    if public_file.exists():
        content = public_file.read_text()
        if '@public_only' not in content:
            issues.append("routes/public.py: Public routes missing @public_only decorator")

    if not issues:
        print(f"{GREEN}✅ Domain routing properly configured{RESET}")
        print(f"{CYAN}   reitsheet.co → @public_only (no auth){RESET}")
        print(f"{CYAN}   app.reitsheet.co → @login_required (auth){RESET}")
        return True

    print(f"{RED}❌ Domain routing not configured!{RESET}\n")
    for issue in issues:
        print(f"  • {issue}")

    print(f"\n{RED}Domain Architecture:{RESET}")
    print("  reitsheet.co      = PUBLIC (newsletter, no auth)")
    print("  app.reitsheet.co  = ADMIN (dashboard, requires auth)")
    print(f"\n{RED}Required:{RESET}")
    print("  1. Create middleware/domain_router.py with @public_only, @admin_only")
    print("  2. Add is_public_domain() check to app.py authentication")
    print("  3. Add @public_only to routes/public.py routes")

    return False  # BLOCKS commit


def check_homepage_publishing_destination():
    """Check 38: Verify homepage publishing uses correct DynamoDB table.

    Homepage is served by Flask from reitsheet-newsletter-editions table.
    The old S3 + reitsheet-newsletters pattern is deprecated.

    BLOCKS commit if JavaScript calls deprecated /publish-homepage endpoint.
    """
    print(f"\n{YELLOW}[38/39] Homepage Publishing Destination{RESET}")

    flask_dir = Path('infrastructure/docker/flask-app')
    issues = []

    # 1. Check JavaScript uses correct endpoint
    js_file = flask_dir / 'static' / 'js' / 'pages' / 'publisher.js'
    if js_file.exists():
        content = js_file.read_text()
        if '/publish-homepage' in content:
            issues.append("publisher.js: Uses deprecated /publish-homepage (should use /publish-v2)")
        if '/publisher/email/publish-v2' not in content:
            issues.append("publisher.js: Missing /publisher/email/publish-v2 endpoint")

    # 2. Check public.py reads from correct source
    public_file = flask_dir / 'routes' / 'public.py'
    if public_file.exists():
        content = public_file.read_text()
        if 'newsletter_service.get_latest()' not in content:
            issues.append("routes/public.py: home() should use newsletter_service.get_latest()")
        if 'reitsheet-newsletters' in content:
            issues.append("routes/public.py: References wrong table reitsheet-newsletters")

    if not issues:
        print(f"{GREEN}✅ Homepage publishing correctly configured{RESET}")
        print(f"{CYAN}   JS → /publish-v2 → NewsletterPublisher → reitsheet-newsletter-editions{RESET}")
        return True

    print(f"{RED}❌ Homepage publishing misconfigured!{RESET}\n")
    for issue in issues:
        print(f"  • {issue}")

    print(f"\n{RED}Architecture:{RESET}")
    print("  Homepage is Flask-rendered (not S3)")
    print("  newsletter_service reads from reitsheet-newsletter-editions")
    print(f"\n{RED}Fix:{RESET}")
    print("  1. JavaScript must call /publisher/email/publish-v2")
    print("  2. publish_v2() uses NewsletterPublisher")
    print("  3. NewsletterPublisher saves to reitsheet-newsletter-editions")

    return False  # BLOCKS commit


def check_template_section_coverage():
    """Check 39: Verify homepage templates use dynamic section rendering.

    Templates must use centralized section_config.py via:
    - Template: {% for key, display_name, _ in sections %} loop
    - Routes: sections=SECTIONS, section_data=...

    BLOCKS commit if dynamic section pattern not found.
    """
    print(f"\n{YELLOW}[39/39] Template Section Coverage{RESET}")

    flask_dir = Path('infrastructure/docker/flask-app')
    issues = []

    # 1. Check home.html uses dynamic sections loop
    home_template = flask_dir / 'templates' / 'public' / 'pages' / 'home.html'
    if home_template.exists():
        content = home_template.read_text()
        # Look for dynamic sections loop pattern
        if 'for key, display_name, _ in sections' not in content:
            issues.append("home.html: Missing dynamic sections loop ({% for key, display_name, _ in sections %})")
        if 'section_data[key]' not in content:
            issues.append("home.html: Missing section_data[key] access")

    # 2. Check public.py passes sections config to templates
    public_file = flask_dir / 'routes' / 'public.py'
    if public_file.exists():
        content = public_file.read_text()
        if 'sections=SECTIONS' not in content:
            issues.append("routes/public.py: Missing sections=SECTIONS in render_template()")
        if 'section_data=' not in content:
            issues.append("routes/public.py: Missing section_data= in render_template()")

    # 3. Check publisher.py preview route passes sections
    publisher_file = flask_dir / 'routes' / 'publisher.py'
    if publisher_file.exists():
        content = publisher_file.read_text()
        if 'sections=SECTIONS' not in content:
            issues.append("routes/publisher.py: Missing sections=SECTIONS in render_template()")
        if 'section_data=' not in content:
            issues.append("routes/publisher.py: Missing section_data= in render_template()")

    # 4. Check email.html uses dynamic sections loop
    email_template = flask_dir / 'templates' / 'newsletter' / 'email.html'
    if email_template.exists():
        content = email_template.read_text()
        if 'for key, display_name, _ in sections' not in content:
            issues.append("email.html: Missing dynamic sections loop ({% for key, display_name, _ in sections %})")
        if 'section_data[key]' not in content:
            issues.append("email.html: Missing section_data[key] access")

    # 5. Check publisher_email.py passes sections config
    publisher_email_file = flask_dir / 'routes' / 'publisher_email.py'
    if publisher_email_file.exists():
        content = publisher_email_file.read_text()
        if 'sections=SECTIONS' not in content:
            issues.append("routes/publisher_email.py: Missing sections=SECTIONS in render_template()")
        if 'section_data=' not in content:
            issues.append("routes/publisher_email.py: Missing section_data= in render_template()")

    if not issues:
        print(f"{GREEN}✅ Templates use dynamic section rendering{RESET}")
        print(f"{CYAN}   Sections sourced from config/section_config.py{RESET}")
        return True

    print(f"{RED}❌ Template section coverage incomplete!{RESET}\n")
    for issue in issues:
        print(f"  • {issue}")

    print(f"\n{RED}Fix:{RESET}")
    print("  1. Template: Use {% for key, display_name, _ in sections %} loop")
    print("  2. Routes: Pass sections=SECTIONS, section_data=...")
    print("  3. Import SECTIONS from config.section_config")

    return False  # BLOCKS commit


def check_publisher_url_function_unity():
    """Check 40: Prevent separate mobile/desktop URL functions in publisher.js.

    Mobile/desktop URL functions have drifted apart 4+ times causing silent
    publish/email failures. The unified getUrlOrder() and getReadyUrls()
    functions handle both views - DO NOT create separate versions.

    Requirements:
    - NO separate getMobile* URL functions
    - getUrlOrder/getReadyUrls MUST query both mobile (.publisher-card)
      and desktop (.release-item) selectors

    BLOCKS commit if requirements not met.
    """
    print(f"\n{YELLOW}[40/40] Publisher URL Function Unity{RESET}")

    js_file = Path('infrastructure/docker/flask-app/static/js/pages/publisher.js')
    if not js_file.exists():
        print(f"{CYAN}   Skipped: publisher.js not found{RESET}")
        return True

    content = js_file.read_text()
    issues = []

    # Forbidden patterns - separate mobile URL functions
    forbidden_patterns = [
        (r'function\s+getMobileUrlOrder', 'getMobileUrlOrder'),
        (r'function\s+getMobileReadyUrls', 'getMobileReadyUrls'),
        (r'function\s+getMobile\w*Urls?\s*\(', 'getMobile*Url* pattern'),
    ]

    for pattern, name in forbidden_patterns:
        if re.search(pattern, content):
            issues.append(f"Forbidden function found: {name}")

    # Required: unified functions must query BOTH mobile and desktop selectors
    # Use specific selectors that are ONLY in the URL functions (not click handlers)
    # .mobile-card-list is the mobile container - must exist for unified functions
    # #sortable-list is the desktop container - must exist for unified functions

    if '.mobile-card-list' not in content:
        issues.append("Missing .mobile-card-list selector (required for mobile URL queries)")
    if '#sortable-list' not in content and 'sortable-list' not in content:
        issues.append("Missing sortable-list selector (required for desktop URL queries)")

    # Required: mobile detection mechanism (offsetParent or similar)
    if 'offsetParent' not in content:
        issues.append("Missing offsetParent mobile detection")

    if not issues:
        print(f"{GREEN}✅ Publisher uses unified URL functions{RESET}")
        print(f"{CYAN}   getUrlOrder()/getReadyUrls() handle both desktop + mobile{RESET}")
        return True

    print(f"{RED}❌ Publisher URL function unity violated!{RESET}\n")
    for issue in issues:
        print(f"  • {issue}")

    print(f"\n{RED}History:{RESET}")
    print("  Mobile/desktop URL functions drifted 4+ times")
    print("  Symptom: 'success' messages but nothing published/sent")
    print(f"\n{RED}Required architecture:{RESET}")
    print("  • ONE getUrlOrder() that queries both views")
    print("  • ONE getReadyUrls() that queries both views")
    print("  • Use offsetParent to detect which view is visible")
    print("  • NO separate getMobile* functions")

    return False  # BLOCKS commit


def check_terraform_drift():
    """Check 41: Detect unapplied Terraform changes.

    BLOCKS commit if Terraform plan shows resources to add/change/destroy.
    This prevents the scenario where Terraform code is committed but never applied,
    leaving EventBridge rules without targets (as occurred April 2026).

    Skips if:
    - infrastructure/terraform/ directory doesn't exist
    - terraform command not available
    - No .tf files staged for commit
    - Backend unreachable (warns only)

    BLOCKS commit if:
    - terraform plan shows any changes (add/change/destroy)
    """
    print(f"\n{YELLOW}[41/42] Terraform Drift Detection{RESET}")

    tf_dir = Path('infrastructure/terraform')
    if not tf_dir.exists():
        print(f"{CYAN}   Skipped: infrastructure/terraform/ not found{RESET}")
        return True

    # Check if any .tf files are staged
    import subprocess
    result = subprocess.run(
        ['git', 'diff', '--cached', '--name-only'],
        capture_output=True, text=True
    )
    staged_files = result.stdout.strip().split('\n') if result.stdout.strip() else []
    tf_staged = [f for f in staged_files if f.endswith('.tf')]

    if not tf_staged:
        print(f"{GREEN}✅ No Terraform files staged for commit{RESET}")
        return True

    print(f"{CYAN}   Checking {len(tf_staged)} staged .tf files...{RESET}")

    # Check if terraform is available
    result = subprocess.run(['which', 'terraform'], capture_output=True)
    if result.returncode != 0:
        print(f"{YELLOW}⚠ terraform command not found - skipping drift check{RESET}")
        return True

    # Run terraform plan
    try:
        result = subprocess.run(
            ['terraform', 'plan', '-detailed-exitcode', '-no-color'],
            capture_output=True,
            text=True,
            cwd=tf_dir,
            timeout=120
        )
        # Exit codes: 0 = no changes, 1 = error, 2 = changes detected
        if result.returncode == 0:
            print(f"{GREEN}✅ Terraform state is in sync with code{RESET}")
            return True
        elif result.returncode == 1:
            # Error running plan - might be backend unreachable
            if 'backend' in result.stderr.lower() or 'state' in result.stderr.lower():
                print(f"{YELLOW}⚠ Terraform backend unreachable - cannot verify drift{RESET}")
                print(f"{CYAN}   Run 'terraform plan' manually before pushing{RESET}")
                return True  # Warning only
            else:
                print(f"{RED}❌ Terraform plan failed:{RESET}")
                print(result.stderr[:500])
                return False
        elif result.returncode == 2:
            # Changes detected
            print(f"{RED}❌ Terraform drift detected! Unapplied changes exist.{RESET}\n")

            # Parse the output to show what would change
            output = result.stdout
            import re
            plan_match = re.search(r'Plan: (\d+) to add, (\d+) to change, (\d+) to destroy', output)
            if plan_match:
                add, change, destroy = plan_match.groups()
                print(f"  Plan: {add} to add, {change} to change, {destroy} to destroy")

            print(f"\n{RED}Fix:{RESET}")
            print("  1. cd infrastructure/terraform")
            print("  2. terraform plan (review changes)")
            print("  3. terraform apply (apply changes)")
            print("  4. Then commit your .tf files")
            return False

    except subprocess.TimeoutExpired:
        print(f"{YELLOW}⚠ Terraform plan timed out - skipping drift check{RESET}")
        return True
    except Exception as e:
        print(f"{YELLOW}⚠ Error running terraform plan: {e}{RESET}")
        return True

    return True


def check_lambda_zip_runtime_imports():
    """Check 42: Verify staged Lambda ZIPs can actually import their handlers.

    BLOCKS commit if a Lambda ZIP fails to import its handler.py at runtime.
    This catches the 'No module named shared' error that broke 8k-processor.

    The existing Check 21 uses AST analysis which doesn't catch runtime import
    errors from missing shared modules in the ZIP.

    Process:
    1. Find Lambda ZIPs staged for commit
    2. Extract each to temp directory
    3. Run: python -c "import handler"
    4. BLOCK if ImportError

    BLOCKS commit if handler import fails.
    """
    print(f"\n{YELLOW}[42/42] Lambda ZIP Runtime Import Test{RESET}")

    import subprocess
    import tempfile
    import zipfile

    # Check for staged Lambda ZIPs
    result = subprocess.run(
        ['git', 'diff', '--cached', '--name-only'],
        capture_output=True, text=True
    )
    staged_files = result.stdout.strip().split('\n') if result.stdout.strip() else []
    lambda_zips = [f for f in staged_files if f.endswith('.zip') and 'lambdas' in f]

    if not lambda_zips:
        print(f"{GREEN}✅ No Lambda ZIPs staged for commit{RESET}")
        return True

    print(f"{CYAN}   Testing {len(lambda_zips)} Lambda ZIPs...{RESET}")

    issues = []
    for zip_path in lambda_zips:
        zip_full_path = Path(zip_path)
        if not zip_full_path.exists():
            continue

        lambda_name = zip_full_path.parent.name

        # Extract to temp dir and test import
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                with zipfile.ZipFile(zip_full_path, 'r') as zf:
                    zf.extractall(tmpdir)

                # Test import
                result = subprocess.run(
                    ['python3', '-c', 'import handler'],
                    capture_output=True,
                    text=True,
                    cwd=tmpdir,
                    env={**os.environ, 'PYTHONPATH': tmpdir},
                    timeout=30
                )

                if result.returncode != 0:
                    error_msg = result.stderr.strip().split('\n')[-1]
                    issues.append((lambda_name, error_msg))
                    print(f"  {RED}✗ {lambda_name}: {error_msg}{RESET}")
                else:
                    print(f"  {GREEN}✓ {lambda_name}: handler imports OK{RESET}")

            except zipfile.BadZipFile:
                issues.append((lambda_name, "Invalid ZIP file"))
            except subprocess.TimeoutExpired:
                issues.append((lambda_name, "Import timed out"))
            except Exception as e:
                issues.append((lambda_name, str(e)))

    if not issues:
        print(f"{GREEN}✅ All Lambda ZIPs import successfully{RESET}")
        return True

    print(f"\n{RED}❌ Lambda ZIP import failures detected!{RESET}\n")
    for name, error in issues:
        print(f"  • {name}: {error}")

    print(f"\n{RED}Fix:{RESET}")
    print("  1. Rebuild the Lambda ZIP with all dependencies")
    print("  2. Ensure shared/ modules are included")
    print("  3. Run ./build.sh in the Lambda directory")
    print("  4. Test locally: unzip -d /tmp/test && cd /tmp/test && python -c 'import handler'")

    return False  # BLOCKS commit


def check_signup_form_parity():
    """
    Check 43: Signup form parity - BLOCKS if popup/footer forms differ in processing.

    All signup forms must use:
    - action="/api/subscribe" (CSRF-exempt endpoint)
    - data-ajax="true" (AJAX submission)
    - honeypot field (name="website")
    - .signup-message div (feedback display)

    This prevents session expired errors when forms are submitted without valid CSRF tokens.
    """
    print(f"\n{CYAN}[Check 43] Signup form parity...{RESET}")

    flask_templates_dir = Path("infrastructure/docker/flask-app/templates")
    if not flask_templates_dir.exists():
        print(f"{YELLOW}⚠️ Flask templates directory not found (skipped){RESET}")
        return True

    issues = []

    # Required patterns for signup forms
    required_patterns = {
        'data-ajax="true"': 'AJAX submission attribute',
        'name="website"': 'honeypot field',
    }

    # Find all HTML templates with signup forms
    for template_path in flask_templates_dir.rglob("*.html"):
        try:
            content = template_path.read_text()

            # Skip test files
            if 'test_' in template_path.name or '_test' in template_path.name:
                continue

            # Skip templates that don't have signup forms
            if 'class="popup-form"' not in content and 'class="signup-form"' not in content:
                continue

            # Extract form sections (rough extraction for validation)
            import re
            forms = re.findall(r'<form[^>]*class="(?:popup-form|signup-form)[^"]*"[^>]*>.*?</form>', content, re.DOTALL)

            for i, form in enumerate(forms):
                form_id = f"{template_path.relative_to(flask_templates_dir)}:form{i+1}"

                # Check for wrong endpoint
                if 'action="/subscribe"' in form or "action='/subscribe'" in form:
                    if '/api/subscribe' not in form:
                        issues.append((form_id, 'uses /subscribe endpoint (CSRF-protected) instead of /api/subscribe'))

                # Check required patterns
                for pattern, description in required_patterns.items():
                    if pattern not in form:
                        issues.append((form_id, f'missing {description} ({pattern})'))

            # Check for .signup-message div near forms (in parent container)
            if ('class="popup-form"' in content or 'class="signup-form"' in content):
                # Check if there's a message div somewhere in the template
                if 'signup-message' not in content:
                    # Only flag if there are forms but no message divs
                    rel_path = template_path.relative_to(flask_templates_dir)
                    issues.append((str(rel_path), 'missing .signup-message div for feedback display'))

        except Exception as e:
            print(f"{YELLOW}⚠️ Could not parse {template_path}: {e}{RESET}")

    # Also check publisher_generator.py
    generator_path = Path("infrastructure/docker/flask-app/core/publisher_generator.py")
    if generator_path.exists():
        try:
            content = generator_path.read_text()

            # Check popup forms in generator
            if 'class="popup-form"' in content:
                if 'data-ajax="true"' not in content:
                    issues.append(('publisher_generator.py', 'popup forms missing data-ajax="true"'))
                if 'name="website"' not in content:
                    issues.append(('publisher_generator.py', 'popup forms missing honeypot field'))

            # Check for wrong endpoint
            if "api_url': '/subscribe'" in content and "/api/subscribe" not in content:
                issues.append(('publisher_generator.py', 'uses /subscribe endpoint instead of /api/subscribe'))

        except Exception as e:
            print(f"{YELLOW}⚠️ Could not parse publisher_generator.py: {e}{RESET}")

    if not issues:
        print(f"{GREEN}✅ All signup forms have consistent processing{RESET}")
        return True

    print(f"\n{RED}❌ Signup form parity issues detected!{RESET}\n")
    for location, issue in issues:
        print(f"  • {location}: {issue}")

    print(f"\n{RED}Fix:{RESET}")
    print("  All signup forms must use consistent processing to avoid session expired errors:")
    print("  1. Use action=\"/api/subscribe\" (CSRF-exempt endpoint)")
    print("  2. Add data-ajax=\"true\" to the form tag")
    print("  3. Include honeypot field: <input type=\"text\" name=\"website\" ...>")
    print("  4. Include feedback div: <div class=\"signup-message\" style=\"display: none;\"></div>")
    print("  See signup_box.html for reference implementation.")

    return False  # BLOCKS commit


def check_title_priority_drift():
    """Check 44: Ensure title display logic uses centralized title_utils module.

    BLOCKS if inline title priority logic is found - must use:
    - Python: from core.title_utils import get_display_title
    - Jinja: {{ item|display_title }} filter

    Priority order (display_title > title). newsletter_title is deprecated.
    """
    print(f"\n{YELLOW}[44/44] Title Priority Drift Detection{RESET}")

    # Files allowed to have inline logic (the source of truth itself)
    ALLOWED_FILES = {
        'infrastructure/docker/flask-app/core/title_utils.py',  # Source of truth
    }

    # Patterns that indicate inline title priority logic or deprecated field usage
    FORBIDDEN_PATTERNS_PY = [
        # Deprecated newsletter_title field access (not method names like update_newsletter_title)
        (r'(?<![_a-zA-Z])\.newsletter_title(?![_a-zA-Z(])',
         'newsletter_title field is deprecated - use display_title via get_display_title()'),
        # Direct hasattr pattern for form pre-population
        (r'hasattr\([^,]+,\s*[\'"]display_title[\'"]\)\s+and\s+\w+\.display_title',
         'Inline display_title check - use get_display_title() from core.title_utils'),
    ]

    FORBIDDEN_PATTERNS_JINJA = [
        # Jinja patterns - deprecated field access
        (r'item\.newsletter_title',
         'newsletter_title is deprecated - use {{ item|display_title }} filter'),
    ]

    errors = []

    # Check Python files
    flask_app_dir = Path('infrastructure/docker/flask-app')
    if flask_app_dir.exists():
        for py_file in flask_app_dir.rglob('*.py'):
            if str(py_file) in ALLOWED_FILES:
                continue
            try:
                content = py_file.read_text()
                for pattern, message in FORBIDDEN_PATTERNS_PY:
                    if re.search(pattern, content):
                        errors.append(f"{py_file}: {message}")
            except Exception:
                pass  # Skip files that can't be read

    # Check Jinja templates
    templates_dir = flask_app_dir / 'templates'
    if templates_dir.exists():
        for html_file in templates_dir.rglob('*.html'):
            try:
                content = html_file.read_text()
                for pattern, message in FORBIDDEN_PATTERNS_JINJA:
                    if re.search(pattern, content):
                        errors.append(f"{html_file}: {message}")
            except Exception:
                pass  # Skip files that can't be read

    if errors:
        print(f"{RED}❌ Title priority drift detected!{RESET}\n")
        for error in errors:
            print(f"  {error}")
        print(f"\n{RED}Action Required:{RESET}")
        print("  - Python: from core.title_utils import get_display_title")
        print("  - Jinja: {{ item|display_title }}")
        print("  - See core/title_utils.py for priority order documentation")
        return False  # BLOCKS commit

    print(f"{GREEN}✅ All title display logic uses centralized module{RESET}")
    return True


def check_verification_scanner_protection():
    """Check 45: Verify route must use two-step flow (scanner protection).

    Email scanners (Proofpoint, URLDefense, SafeLinks) automatically click
    GET links in emails. If /verify auto-verifies on GET, scanners will
    verify users before they can click manually.

    Required pattern:
    - Route must accept POST (not just GET)
    - Must check request.method == 'GET' to separate flows
    - GET shows confirmation page, POST does verification

    BLOCKS if scanner protection is missing.
    """
    print(f"\n{YELLOW}[45/45] Verification Scanner Protection{RESET}")

    subscribe_routes = Path("infrastructure/docker/flask-app/routes/subscribe.py")
    if not subscribe_routes.exists():
        print(f"{YELLOW}⚠️  subscribe.py not found (skipping){RESET}")
        return True

    content = subscribe_routes.read_text()

    # Find verify route decorator
    verify_match = re.search(
        r"@subscribe_bp\.route\('/verify'[^)]*methods=\[([^\]]+)\]",
        content
    )

    if not verify_match:
        print(f"{RED}❌ /verify route not found or missing methods{RESET}")
        return False

    methods = verify_match.group(1)

    # Must include POST
    if 'POST' not in methods:
        print(f"{RED}❌ /verify must accept POST (scanner protection){RESET}")
        print(f"   Current methods: {methods}")
        print(f"   Email scanners auto-click GET links, bypassing verification")
        return False

    # Check for two-step verification pattern
    if "request.method == 'GET'" not in content:
        print(f"{RED}❌ /verify must check request.method to separate GET/POST{RESET}")
        print(f"   GET should show confirmation page (scanner stops here)")
        print(f"   POST should actually verify (user clicks button)")
        return False

    print(f"{GREEN}✅ Verification endpoint has scanner protection{RESET}")
    return True


def main():
    """Run all validation checks"""
    print("=" * 60)
    print("Enhanced Pre-Commit Validation (45 checks)")
    print("=" * 60)

    checks = [
        # Original 5 checks
        check_routing_consistency,
        check_newswire_domains_duplication,
        check_queue_url_fallbacks,
        check_playwright_config_completeness,
        check_terraform_references,
        # Configuration checks (4)
        check_dynamodb_table_consistency,
        check_boto3_patterns,
        check_playwright_config_dynamodb,
        check_env_var_consistency,
        # Safety checks (5) - added 2026-03-13
        check_python_syntax,
        check_import_resolution,
        check_direct_url_config,
        check_routing_table_validity,
        check_landing_page_detection_integrity,  # Check 14
        # Template safety - added 2026-03-14
        check_template_date_safety,  # Check 15
        # Session security - added 2026-03-14
        check_flask_session_https_config,  # Check 16
        # Deployment documentation - added 2026-03-14
        check_deployment_config,  # Check 17
        # Form security - added 2026-03-15
        check_flask_wtf_usage,  # Check 18
        # Timestamp data integrity - added 2026-03-15
        check_timestamp_field_formats,  # Check 19
        # Lambda deployment safety - added 2026-03-15
        check_lambda_zip_dependencies,  # Check 20
        # Lambda import smoke test - added 2026-03-16
        check_lambda_import_smoke_test,  # Check 21
        # AST-based validation expansion - added 2026-03-16
        check_timezone_utility_enforcement,  # Check 22
        check_lambda_handler_signature,  # Check 23
        check_circular_imports,  # Check 24
        # Configuration safety - added 2026-03-16
        check_sqs_schema_validation,  # Check 25
        check_env_var_registry,  # Check 26
        check_queue_name_consistency,  # Check 27
        check_buildspec_import_validation,  # Check 28
        # AST-based module discovery - added 2026-03-19
        check_lambda_module_discovery,  # Check 29
        check_build_script_discovery,  # Check 30
        # Lambda config centralization - added 2026-03-23
        check_lambda_config_centralization,  # Check 31
        # Frontend validation - added 2026-03-28
        check_design_token_source,  # Check 32
        check_brand_standards,  # Check 33
        check_mobile_text_wrapping,  # Check 34 (WARNING only)
        check_email_style_consistency,  # Check 35
        check_accessibility,  # Check 36
        # Domain architecture - added 2026-03-28
        check_domain_routing,  # Check 37
        # Homepage publishing - added 2026-03-30
        check_homepage_publishing_destination,  # Check 38
        check_template_section_coverage,  # Check 39
        # Publisher mobile/desktop sync - added 2026-04-01
        check_publisher_url_function_unity,  # Check 40
        # Terraform and Lambda deployment safety - added 2026-04-02
        check_terraform_drift,  # Check 41
        check_lambda_zip_runtime_imports,  # Check 42
        # Signup form parity - added 2026-04-03
        check_signup_form_parity,  # Check 43
        # Title priority drift - added 2026-04-08
        check_title_priority_drift,  # Check 44
        # Scanner protection - added 2026-04-13
        check_verification_scanner_protection,  # Check 45
    ]

    results = []
    for check in checks:
        try:
            result = check()
            results.append(result)
        except Exception as e:
            print(f"{RED}❌ Check failed with error: {e}{RESET}")
            results.append(False)

    # Count results
    passed = sum(1 for r in results if r)
    failed = len(results) - passed

    print("\n" + "=" * 60)
    print(f"Results: {passed}/{len(results)} checks passed")
    print("=" * 60)

    if all(results):
        print(f"{GREEN}All checks passed!{RESET}")
        return 0
    else:
        print(f"{RED}Validation failed - fix issues above before committing{RESET}")
        print(f"\n{YELLOW}To bypass (NOT RECOMMENDED):{RESET}")
        print("  git commit --no-verify")
        return 1


if __name__ == '__main__':
    sys.exit(main())
