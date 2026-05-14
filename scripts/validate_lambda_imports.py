#!/usr/bin/env python3
"""
Lambda Import Validation - Pre-Deployment Check (AST-Based)
============================================================
Uses AST analysis to detect import issues WITHOUT requiring dependencies:
- Duplicate function definitions that shadow imports
- Names used but never imported or defined
- Missing imports for standard library modules

Works without installing Lambda dependencies locally.

Usage:
    python3 scripts/validate_lambda_imports.py              # Validate all Lambdas
    python3 scripts/validate_lambda_imports.py playwright   # Validate specific Lambda
    python3 scripts/validate_lambda_imports.py --verbose    # Show detailed output

Last Created: 2026-03-16
"""

import ast
import argparse
import sys
from pathlib import Path

# ANSI colors
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
CYAN = '\033[96m'
RESET = '\033[0m'

# Python builtins that don't need imports
BUILTINS = {
    'True', 'False', 'None', 'Exception', 'BaseException',
    'print', 'len', 'str', 'int', 'float', 'list', 'dict', 'set', 'tuple',
    'range', 'enumerate', 'zip', 'map', 'filter', 'sorted', 'reversed',
    'open', 'isinstance', 'issubclass', 'hasattr', 'getattr', 'setattr',
    'type', 'super', 'property', 'staticmethod', 'classmethod',
    'any', 'all', 'sum', 'min', 'max', 'abs', 'round', 'repr', 'id',
    'KeyError', 'ValueError', 'TypeError', 'AttributeError', 'IndexError',
    'RuntimeError', 'StopIteration', 'FileNotFoundError', 'OSError',
    'ImportError', 'ModuleNotFoundError', 'NameError', 'ZeroDivisionError',
    'NotImplementedError', 'AssertionError', 'ConnectionError', 'TimeoutError',
    'object', 'bytes', 'bytearray', 'memoryview', 'bool', 'complex',
    'frozenset', 'slice', 'format', 'vars', 'dir', 'globals', 'locals',
    'callable', 'iter', 'next', 'input', 'hash', 'hex', 'oct', 'bin',
    'chr', 'ord', 'pow', 'divmod', 'eval', 'exec', 'compile',
}

# Known third-party/local modules (don't flag these as undefined)
KNOWN_MODULES = {
    # Third-party packages
    'boto3', 'botocore', 'requests', 'bs4', 'feedparser', 'dateutil',
    'playwright', 'cloudscraper', 'curl_cffi', 'lxml', 'urllib3',
    # Local modules
    'browser', 'matching', 'persistence', 'routing', 'shared', 'url',
    'landing_page_detector', 'timestamp_utils', 'constants',
    'redirect_circuit_breaker', 'timezone_utils', 'aws_clients',
    'context_manager', 'page_navigator', 'fuzzy_matcher', 'dynamodb_ops',
}

# Lambda configurations
LAMBDA_CONFIGS = {
    'parser': 'infrastructure/lambdas/parser/handler.py',
    'enricher': 'infrastructure/lambdas/enricher/handler.py',
    'playwright-scraper': 'infrastructure/lambdas/playwright-scraper/handler.py',
    'scraper': 'infrastructure/lambdas/scraper/handler.py',
}


class ImportAnalyzer(ast.NodeVisitor):
    """AST visitor that collects imported names, defined names, and used names."""

    def __init__(self):
        self.imported_names = set()
        self.import_sources = {}  # Maps name -> (module, original_name)
        self.defined_names = set()
        self.used_names = set()
        self.local_scope_names = set()
        self._in_function = False

    def visit_Import(self, node):
        for alias in node.names:
            name = alias.asname if alias.asname else alias.name.split('.')[0]
            self.imported_names.add(name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        module = node.module or ''
        for alias in node.names:
            name = alias.asname if alias.asname else alias.name
            self.imported_names.add(name)
            self.import_sources[name] = (module, alias.name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        # Track top-level function definitions
        if not self._in_function:
            self.defined_names.add(node.name)

        # Track function arguments as local scope
        for arg in node.args.args:
            self.local_scope_names.add(arg.arg)
        for arg in node.args.posonlyargs:
            self.local_scope_names.add(arg.arg)
        for arg in node.args.kwonlyargs:
            self.local_scope_names.add(arg.arg)
        if node.args.vararg:
            self.local_scope_names.add(node.args.vararg.arg)
        if node.args.kwarg:
            self.local_scope_names.add(node.args.kwarg.arg)

        # Visit function body
        old_in_function = self._in_function
        self._in_function = True
        self.generic_visit(node)
        self._in_function = old_in_function

    def visit_AsyncFunctionDef(self, node):
        self.visit_FunctionDef(node)

    def visit_ClassDef(self, node):
        if not self._in_function:
            self.defined_names.add(node.name)
        self.generic_visit(node)

    def visit_Assign(self, node):
        # Track top-level assignments
        if not self._in_function:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.defined_names.add(target.id)
        else:
            # Track local assignments
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.local_scope_names.add(target.id)
        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        if not self._in_function and isinstance(node.target, ast.Name):
            self.defined_names.add(node.target.id)
        self.generic_visit(node)

    def visit_For(self, node):
        if isinstance(node.target, ast.Name):
            self.local_scope_names.add(node.target.id)
        elif isinstance(node.target, ast.Tuple):
            for elt in node.target.elts:
                if isinstance(elt, ast.Name):
                    self.local_scope_names.add(elt.id)
        self.generic_visit(node)

    def visit_ExceptHandler(self, node):
        if node.name:
            self.local_scope_names.add(node.name)
        self.generic_visit(node)

    def visit_Lambda(self, node):
        # Track lambda parameters as local scope
        for arg in node.args.args:
            self.local_scope_names.add(arg.arg)
        if node.args.vararg:
            self.local_scope_names.add(node.args.vararg.arg)
        if node.args.kwarg:
            self.local_scope_names.add(node.args.kwarg.arg)
        self.generic_visit(node)

    def visit_comprehension(self, node):
        if isinstance(node.target, ast.Name):
            self.local_scope_names.add(node.target.id)
        self.generic_visit(node)

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load):
            self.used_names.add(node.id)
        elif isinstance(node.ctx, ast.Store):
            self.local_scope_names.add(node.id)
        self.generic_visit(node)


def validate_lambda(lambda_name: str, verbose: bool = False) -> tuple[bool, list, list]:
    """
    Validate a Lambda's handler using AST analysis.

    Returns:
        tuple: (success, errors, warnings)
    """
    if lambda_name not in LAMBDA_CONFIGS:
        return False, [f"Unknown Lambda: {lambda_name}"], []

    handler_path = Path(LAMBDA_CONFIGS[lambda_name])

    if not handler_path.exists():
        return False, [f"Handler not found: {handler_path}"], []

    errors = []
    warnings = []

    try:
        content = handler_path.read_text()
        tree = ast.parse(content)

        analyzer = ImportAnalyzer()
        analyzer.visit(tree)

        if verbose:
            print(f"\n  Imported: {sorted(analyzer.imported_names)[:10]}...")
            print(f"  Defined:  {sorted(analyzer.defined_names)[:10]}...")

        # Check for shadowed imports (function defined that shadows an import)
        shadowed = analyzer.imported_names & analyzer.defined_names
        for name in shadowed:
            if name in analyzer.import_sources:
                module, orig_name = analyzer.import_sources[name]
                warnings.append(
                    f"SHADOW: '{name}' imported from {module} but also defined locally"
                )

        # Check for undefined names
        all_defined = (
            analyzer.imported_names |
            analyzer.defined_names |
            analyzer.local_scope_names |
            BUILTINS |
            KNOWN_MODULES
        )

        undefined = analyzer.used_names - all_defined

        for name in sorted(undefined):
            # Skip common patterns
            if name.startswith('_'):  # Private names
                continue
            if name.isupper() and len(name) > 1:  # CONSTANTS
                continue
            if name in {'self', 'cls'}:  # Method arguments
                continue

            errors.append(f"NameError: '{name}' used but not imported or defined")

        return len(errors) == 0, errors, warnings

    except SyntaxError as e:
        return False, [f"SyntaxError: {e}"], []
    except Exception as e:
        return False, [f"Analysis error: {e}"], []


def validate_all(verbose: bool = False) -> bool:
    """Validate all Lambda handlers."""
    print("=" * 60)
    print("Lambda Import Validation (AST-Based)")
    print("=" * 60)
    print("No local dependencies required - uses static analysis\n")

    all_passed = True
    results = []

    for lambda_name in LAMBDA_CONFIGS:
        print(f"Validating {lambda_name}...")
        success, errors, warnings = validate_lambda(lambda_name, verbose)
        results.append((lambda_name, success, errors, warnings))

        if warnings:
            for warn in warnings:
                print(f"  {YELLOW}⚠️  {warn}{RESET}")

        if success:
            print(f"  {GREEN}✅ OK{RESET}")
        else:
            print(f"  {RED}❌ FAILED{RESET}")
            for err in errors:
                print(f"     {RED}{err}{RESET}")
            all_passed = False

    # Summary
    print("\n" + "=" * 60)
    passed = sum(1 for _, s, _, _ in results if s)
    total = len(results)

    if all_passed:
        print(f"{GREEN}✅ PASSED: All {total} Lambdas pass AST analysis{RESET}")
    else:
        print(f"{RED}❌ FAILED: {total - passed}/{total} Lambdas have issues{RESET}")

        print(f"\n{YELLOW}Common fixes:{RESET}")
        print("  - SHADOW: Delete the local function definition (use imported version)")
        print("  - NameError: Add missing import statement")

    print("=" * 60)
    return all_passed


def main():
    parser = argparse.ArgumentParser(
        description='Validate Lambda imports using AST analysis (no deps required)'
    )
    parser.add_argument(
        'lambda_name',
        nargs='?',
        help='Specific Lambda to validate (parser, enricher, playwright-scraper, scraper)'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Show detailed analysis output'
    )

    args = parser.parse_args()

    if args.lambda_name:
        # Handle partial matches
        name = args.lambda_name.lower()
        if name == 'playwright':
            name = 'playwright-scraper'

        success, errors, warnings = validate_lambda(name, args.verbose)

        if warnings:
            for warn in warnings:
                print(f"{YELLOW}⚠️  {warn}{RESET}")

        if success:
            print(f"{GREEN}✅ {name}: Passes AST analysis{RESET}")
        else:
            print(f"{RED}❌ {name}: Failed{RESET}")
            for err in errors:
                print(f"   {RED}{err}{RESET}")

        sys.exit(0 if success else 1)
    else:
        success = validate_all(args.verbose)
        sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
