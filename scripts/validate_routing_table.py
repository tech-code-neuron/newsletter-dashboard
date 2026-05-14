#!/usr/bin/env python3
"""
Routing Table Validation Script
=================================
Purpose: Ensure CLAUDE.md routing table stays in sync with actual routing code

Validates:
1. Routing table exists in CLAUDE.md
2. Referenced files exist
3. Referenced line numbers are approximately correct (±10 lines)
4. Queue names in table match queue names in code

Usage:
    python3 scripts/validate_routing_table.py

Exit codes:
    0 - Validation passed
    1 - Validation failed
    2 - Error during validation

Last Updated: 2026-03-13
"""

import re
import sys
from pathlib import Path


# ============================================================================
# Configuration
# ============================================================================

PROJECT_ROOT = Path(__file__).parent.parent
CLAUDE_MD_PATH = PROJECT_ROOT / "CLAUDE.md"

# Files that contain routing logic (map table references to actual files)
ROUTING_FILES = {
    'parser/routing.py': PROJECT_ROOT / 'infrastructure/lambdas/parser/routing.py',
    'enricher/handler.py': PROJECT_ROOT / 'infrastructure/lambdas/enricher/handler.py',
    'enricher/persistence/dynamodb_ops.py': PROJECT_ROOT / 'infrastructure/lambdas/enricher/persistence/dynamodb_ops.py',
    'redirect_circuit_breaker.py': PROJECT_ROOT / 'infrastructure/lambdas/enricher/persistence/redirect_circuit_breaker.py',
    'scraper/handler.py': PROJECT_ROOT / 'infrastructure/lambdas/scraper/handler.py',
    'scraper/scraper_persistence.py': PROJECT_ROOT / 'infrastructure/lambdas/scraper/scraper_persistence.py',
    'playwright-scraper/handler.py': PROJECT_ROOT / 'infrastructure/lambdas/playwright-scraper/handler.py'
}

# Expected queue names that should appear in routing code (case-insensitive)
EXPECTED_QUEUES = [
    'PLAYWRIGHT_QUEUE',
    'ENRICH_QUEUE',
    'SCRAPE_QUEUE',
    'DynamoDB'
]

# Queue name variations (uppercase constant or lowercase variable)
QUEUE_VARIATIONS = {
    'PLAYWRIGHT_QUEUE': ['PLAYWRIGHT_QUEUE', 'playwright_queue'],
    'ENRICH_QUEUE': ['ENRICH_QUEUE', 'enrich_queue', 'enrichment'],
    'SCRAPE_QUEUE': ['SCRAPE_QUEUE', 'scrape_queue'],
    'DynamoDB': ['DynamoDB', 'dynamodb', 'reit_news_table']
}

# Line number tolerance (routing code can shift ±N lines)
LINE_TOLERANCE = 20  # Allow ±20 lines of drift before warning


# ============================================================================
# Validation Functions
# ============================================================================

def extract_routing_table_from_claude_md():
    """
    Extract routing table section from CLAUDE.md

    Returns:
        list: List of routing table rows (dicts with condition, queue, location)
        None if table not found
    """
    if not CLAUDE_MD_PATH.exists():
        print(f"❌ CLAUDE.md not found at {CLAUDE_MD_PATH}")
        return None

    content = CLAUDE_MD_PATH.read_text()

    # Find routing table section
    table_match = re.search(
        r'## Email Routing Decision Table.*?\n\n\| Condition \| Queue/Output \| Code Location \|.*?\n\|.*?\n((?:\|.*?\n)+)',
        content,
        re.DOTALL
    )

    if not table_match:
        print("❌ Routing table not found in CLAUDE.md")
        print("Expected: '## Email Routing Decision Table' section with table")
        return None

    table_text = table_match.group(1)

    # Parse table rows
    rows = []
    for line in table_text.strip().split('\n'):
        if not line.startswith('|'):
            continue

        # Split by | and clean
        parts = [p.strip() for p in line.split('|') if p.strip()]
        if len(parts) >= 3:
            condition = parts[0]
            queue = parts[1]
            location = parts[2]
            rows.append({
                'condition': condition,
                'queue': queue,
                'location': location
            })

    return rows


def validate_file_references(rows):
    """
    Validate that files referenced in routing table exist

    Args:
        rows: List of routing table rows

    Returns:
        tuple: (success: bool, errors: list)
    """
    errors = []

    for row in rows:
        location = row['location']

        # Extract file references (format: "file.py:123" or "file.py:123-456")
        # Include hyphens in filename pattern for cases like "playwright-scraper"
        file_refs = re.findall(r'([\w/-]+\.py):(\d+)(?:-(\d+))?', location)

        for file_ref in file_refs:
            file_path = file_ref[0]
            start_line = int(file_ref[1])

            # Map table file path to actual file path
            actual_file = ROUTING_FILES.get(file_path)

            if not actual_file:
                errors.append(f"Unknown file reference: {file_path} (not in ROUTING_FILES map)")
                continue

            if not actual_file.exists():
                errors.append(f"Referenced file does not exist: {actual_file}")
                continue

            # Check if line number is within file bounds
            file_lines = actual_file.read_text().split('\n')
            if start_line > len(file_lines):
                errors.append(
                    f"Line number out of bounds: {file_path}:{start_line} "
                    f"(file has {len(file_lines)} lines)"
                )

    return len(errors) == 0, errors


def validate_queue_names(rows):
    """
    Validate that queue names in table match code

    Args:
        rows: List of routing table rows

    Returns:
        tuple: (success: bool, errors: list)
    """
    errors = []
    warnings = []

    # Extract queue names from table
    table_queues = set()
    for row in rows:
        queue = row['queue']
        # Extract queue names (UPPERCASE_WORDS)
        matches = re.findall(r'([A-Z_]+_QUEUE|DynamoDB)', queue)
        table_queues.update(matches)

    # Check that routing code contains these queue names (or variations)
    for queue_name in table_queues:
        if queue_name == 'DynamoDB':
            continue  # DynamoDB is not a queue constant

        found = False
        variations = QUEUE_VARIATIONS.get(queue_name, [queue_name])

        for file_path in ROUTING_FILES.values():
            if file_path.exists():
                content = file_path.read_text()
                # Check if any variation appears in code
                if any(var in content for var in variations):
                    found = True
                    break

        if not found:
            errors.append(
                f"Queue name '{queue_name}' in table not found in any routing file. "
                f"Queue may have been renamed or removed. Checked variations: {variations}"
            )

    # Check that expected queues are in table
    for expected_queue in EXPECTED_QUEUES:
        if expected_queue not in table_queues and expected_queue != 'DynamoDB':
            warnings.append(
                f"Expected queue '{expected_queue}' not found in routing table. "
                f"May be missing a routing condition."
            )

    return len(errors) == 0, errors, warnings


def validate_line_number_accuracy(rows):
    """
    Validate that line numbers in table are approximately correct

    Checks that referenced lines contain relevant routing keywords

    Args:
        rows: List of routing table rows

    Returns:
        tuple: (success: bool, warnings: list)
    """
    warnings = []

    # Keywords that should appear near routing decision points
    routing_keywords = [
        'PLAYWRIGHT_QUEUE', 'ENRICH_QUEUE', 'SCRAPE_QUEUE',
        'should_use_playwright', 'queue_for_playwright', 'queue_for_enrichment',
        'queue_for_scraping', 'save_to_dynamodb', 'should_attempt_redirect',
        'circuit_breaker', 'url_construction_method', 'direct_url'
    ]

    for row in rows:
        location = row['location']
        condition = row['condition']

        # Extract file references
        file_refs = re.findall(r'([\w/]+\.py):(\d+)(?:-(\d+))?', location)

        for file_ref in file_refs:
            file_path = file_ref[0]
            line_num = int(file_ref[1])

            actual_file = ROUTING_FILES.get(file_path)
            if not actual_file or not actual_file.exists():
                continue

            # Read lines around referenced line number
            file_lines = actual_file.read_text().split('\n')
            start = max(0, line_num - LINE_TOLERANCE)
            end = min(len(file_lines), line_num + LINE_TOLERANCE)
            context = '\n'.join(file_lines[start:end])

            # Check if any routing keywords appear in context
            has_routing_keyword = any(kw in context for kw in routing_keywords)

            if not has_routing_keyword:
                warnings.append(
                    f"Line {file_path}:{line_num} (condition: '{condition[:40]}...') "
                    f"may be stale - no routing keywords found within ±{LINE_TOLERANCE} lines"
                )

    # Warnings don't fail validation (code can shift), but should be reviewed
    return True, warnings


def validate_routing_table():
    """
    Main validation function

    Returns:
        int: Exit code (0 = success, 1 = failure, 2 = error)
    """
    print("🔍 Validating routing table in CLAUDE.md...\n")

    # Step 1: Extract routing table
    rows = extract_routing_table_from_claude_md()
    if rows is None:
        return 2  # Error

    print(f"✅ Found routing table with {len(rows)} rows\n")

    # Step 2: Validate file references
    print("📁 Validating file references...")
    files_ok, file_errors = validate_file_references(rows)

    if not files_ok:
        print("❌ File reference validation FAILED:\n")
        for error in file_errors:
            print(f"   - {error}")
        print()
        return 1  # Validation failed

    print("✅ All file references valid\n")

    # Step 3: Validate queue names
    print("🎯 Validating queue names...")
    queues_ok, queue_errors, queue_warnings = validate_queue_names(rows)

    if not queues_ok:
        print("❌ Queue name validation FAILED:\n")
        for error in queue_errors:
            print(f"   - {error}")
        print()
        return 1  # Validation failed

    if queue_warnings:
        print("⚠️  Queue name warnings:\n")
        for warning in queue_warnings:
            print(f"   - {warning}")
        print()
    else:
        print("✅ All queue names valid\n")

    # Step 4: Validate line number accuracy
    print("🔢 Validating line number accuracy...")
    lines_ok, line_warnings = validate_line_number_accuracy(rows)

    if line_warnings:
        print("⚠️  Line number warnings (may need review):\n")
        for warning in line_warnings:
            print(f"   - {warning}")
        print()
        print("💡 TIP: Line number drift is normal as code evolves.")
        print("   Review warnings and update CLAUDE.md if routing logic moved.\n")
    else:
        print("✅ All line numbers appear accurate\n")

    # Final result
    print("=" * 70)
    print("✅ ROUTING TABLE VALIDATION PASSED")
    print("=" * 70)
    print()
    print("CLAUDE.md routing table is in sync with routing code.")
    print()

    return 0  # Success


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == '__main__':
    try:
        exit_code = validate_routing_table()
        sys.exit(exit_code)
    except Exception as e:
        print(f"\n❌ VALIDATION ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(2)
