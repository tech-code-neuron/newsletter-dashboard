#!/usr/bin/env python3
"""
Circular Import Detection - AST-Based Analysis
===============================================
Detects circular imports in Lambda code that would cause ImportError at runtime.

Uses DFS to find cycles in the import dependency graph.

Usage:
    python3 scripts/detect_circular_imports.py              # Check all Lambdas
    python3 scripts/detect_circular_imports.py parser       # Check specific Lambda
    python3 scripts/detect_circular_imports.py --verbose    # Show import graph

Example cycle detection:
    a.py -> b.py -> c.py -> a.py

Last Created: 2026-03-16
"""

import ast
import argparse
import sys
from pathlib import Path
from collections import defaultdict

# ANSI colors
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
CYAN = '\033[96m'
RESET = '\033[0m'

# Lambda directories to check
LAMBDA_DIRS = {
    'parser': 'infrastructure/lambdas/parser',
    'enricher': 'infrastructure/lambdas/enricher',
    'playwright-scraper': 'infrastructure/lambdas/playwright-scraper',
    'scraper': 'infrastructure/lambdas/scraper',
    'email-forwarder': 'infrastructure/lambdas/email-forwarder',
    'daily-summary': 'infrastructure/lambdas/daily-summary',
}


def build_import_graph(lambda_dir: Path, verbose: bool = False) -> dict:
    """
    Build directed graph of imports within a Lambda directory.

    Returns:
        dict: Maps module name -> set of imported module names
    """
    graph = defaultdict(set)
    modules = {}

    # Third-party packages to ignore (installed dependencies)
    THIRD_PARTY_PACKAGES = {
        'bs4', 'requests', 'urllib3', 'feedparser', 'dateutil', 'boto3', 'botocore',
        'playwright', 'cloudscraper', 'curl_cffi', 'lxml', 'soupsieve', 'certifi',
        'charset_normalizer', 'idna', 'sgmllib', 'chardet', 'html5lib', 'jmespath',
        's3transfer', 'pyee', 'greenlet', 'async_generator', 'cffi', 'pycparser',
    }

    # Find all Python files that are Lambda code (not installed packages)
    for py_file in lambda_dir.rglob('*.py'):
        # Skip __pycache__, dist-info, and package directory (pip installs)
        if '__pycache__' in str(py_file) or '.dist-info' in str(py_file):
            continue

        # Skip third-party packages (check if first directory is a known package)
        rel_path = py_file.relative_to(lambda_dir)
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

    if verbose:
        print(f"\n{CYAN}Modules found:{RESET}")
        for mod in sorted(modules.keys()):
            print(f"  - {mod}")

    # Parse each file for imports
    for module_name, py_file in modules.items():
        try:
            content = py_file.read_text()
            tree = ast.parse(content)

            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    if node.module:
                        imported_base = node.module.split('.')[0]
                        # Check if this is a local import (relative to this Lambda)
                        if imported_base in modules or any(imported_base == m.split('.')[0] for m in modules):
                            graph[module_name].add(node.module)

                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        imported_base = alias.name.split('.')[0]
                        if imported_base in modules or any(imported_base == m.split('.')[0] for m in modules):
                            graph[module_name].add(alias.name)

        except SyntaxError as e:
            print(f"{YELLOW}  Warning: Syntax error in {py_file}: {e}{RESET}")
        except Exception as e:
            print(f"{YELLOW}  Warning: Error parsing {py_file}: {e}{RESET}")

    if verbose:
        print(f"\n{CYAN}Import graph:{RESET}")
        for mod, imports in sorted(graph.items()):
            if imports:
                print(f"  {mod} -> {', '.join(sorted(imports))}")

    return graph


def find_cycles(graph: dict) -> list:
    """
    Find all cycles in import graph using DFS.

    Returns:
        list: List of cycle paths, each path is a list of module names
    """
    cycles = []
    visited = set()
    rec_stack = []
    rec_stack_set = set()

    def dfs(node, path=None):
        if path is None:
            path = []

        visited.add(node)
        rec_stack.append(node)
        rec_stack_set.add(node)

        for neighbor in graph.get(node, []):
            # Normalize to base module name for comparison
            neighbor_base = neighbor.split('.')[0]

            # Check against full module names in rec_stack
            for stack_item in rec_stack:
                if stack_item.split('.')[0] == neighbor_base and stack_item != node:
                    # Found potential cycle
                    cycle_start_idx = rec_stack.index(stack_item)
                    cycle = rec_stack[cycle_start_idx:] + [neighbor]
                    cycles.append(cycle)

            if neighbor not in visited:
                dfs(neighbor, path + [node])

        rec_stack.pop()
        rec_stack_set.remove(node)

    for node in graph:
        if node not in visited:
            dfs(node)

    # Deduplicate cycles (same cycle can be detected from different starting points)
    unique_cycles = []
    seen_cycle_sets = []

    for cycle in cycles:
        cycle_set = frozenset(cycle)
        if cycle_set not in seen_cycle_sets:
            seen_cycle_sets.append(cycle_set)
            unique_cycles.append(cycle)

    return unique_cycles


def check_lambda(lambda_name: str, verbose: bool = False) -> tuple[bool, list]:
    """
    Check a specific Lambda for circular imports.

    Returns:
        tuple: (success, list of cycle descriptions)
    """
    if lambda_name not in LAMBDA_DIRS:
        return False, [f"Unknown Lambda: {lambda_name}. Available: {', '.join(LAMBDA_DIRS.keys())}"]

    lambda_dir = Path(LAMBDA_DIRS[lambda_name])

    if not lambda_dir.exists():
        return True, []  # Skip non-existent directories

    print(f"\nChecking {lambda_name}...")

    graph = build_import_graph(lambda_dir, verbose)
    cycles = find_cycles(graph)

    if cycles:
        cycle_descriptions = []
        for cycle in cycles:
            cycle_str = ' -> '.join(cycle)
            cycle_descriptions.append(f"Circular import: {cycle_str}")
        return False, cycle_descriptions

    return True, []


def check_all(verbose: bool = False) -> bool:
    """Check all Lambda directories for circular imports."""
    print("=" * 60)
    print("Circular Import Detection (AST-Based)")
    print("=" * 60)

    all_passed = True
    results = []

    for lambda_name in LAMBDA_DIRS:
        success, cycles = check_lambda(lambda_name, verbose)
        results.append((lambda_name, success, cycles))

        if success:
            print(f"  {GREEN}✅ {lambda_name}: No circular imports{RESET}")
        else:
            print(f"  {RED}❌ {lambda_name}: Circular imports detected{RESET}")
            for cycle in cycles:
                print(f"     {RED}{cycle}{RESET}")
            all_passed = False

    # Summary
    print("\n" + "=" * 60)
    passed = sum(1 for _, s, _ in results if s)
    total = len(results)

    if all_passed:
        print(f"{GREEN}✅ PASSED: No circular imports in {total} Lambdas{RESET}")
    else:
        print(f"{RED}❌ FAILED: Circular imports detected{RESET}")

        print(f"\n{YELLOW}How to fix circular imports:{RESET}")
        print("  1. Move shared code to a common module (e.g., shared/)")
        print("  2. Use late imports (import inside function)")
        print("  3. Restructure module dependencies")
        print("  4. Use TYPE_CHECKING guard for type hints:")
        print("     from typing import TYPE_CHECKING")
        print("     if TYPE_CHECKING:")
        print("         from module import Type")

    print("=" * 60)
    return all_passed


def main():
    parser = argparse.ArgumentParser(
        description='Detect circular imports in Lambda code using AST analysis',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python3 scripts/detect_circular_imports.py              # Check all
    python3 scripts/detect_circular_imports.py parser       # Check one
    python3 scripts/detect_circular_imports.py -v           # Verbose mode
        """
    )
    parser.add_argument(
        'lambda_name',
        nargs='?',
        help='Specific Lambda to check (parser, enricher, playwright-scraper, scraper)'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Show import graph details'
    )

    args = parser.parse_args()

    if args.lambda_name:
        # Handle partial matches
        name = args.lambda_name.lower()
        if name == 'playwright':
            name = 'playwright-scraper'

        success, cycles = check_lambda(name, args.verbose)

        if success:
            print(f"{GREEN}✅ {name}: No circular imports{RESET}")
        else:
            print(f"{RED}❌ {name}: Circular imports detected{RESET}")
            for cycle in cycles:
                print(f"   {RED}{cycle}{RESET}")

        sys.exit(0 if success else 1)
    else:
        success = check_all(args.verbose)
        sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
