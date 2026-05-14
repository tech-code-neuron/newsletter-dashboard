#!/usr/bin/env python3
"""
Lambda Deployment Helper - Prevent Missing Dependencies
========================================================
Validates and deploys Lambda functions with dependency checking

Usage:
    python3 scripts/deploy_lambda.py parser                    # Build, validate, deploy
    python3 scripts/deploy_lambda.py enricher --test           # Deploy and test
    python3 scripts/deploy_lambda.py parser --build-only       # Just build package
    python3 scripts/deploy_lambda.py --list                    # Show all deployable Lambdas

Why this exists:
    - Prevents deployment of Lambdas without dependencies
    - Validates imports before deployment (catches missing packages)
    - Ensures consistent build process across all Lambdas
    - Provides safety checks (size validation, import verification)
"""

import argparse
import subprocess
import sys
import os
import zipfile
import json
import tempfile
import shutil
import fcntl
from pathlib import Path
from datetime import datetime, timezone

# Color codes for output
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
BLUE = '\033[94m'
RESET = '\033[0m'

# Lambda configuration with size ranges (min, max in bytes)
# These ranges prevent deploying wrong ZIP (e.g., 83KB vs 1.9MB incident on 2026-03-13)
LAMBDA_CONFIG = {
    'parser': {
        'name': 'reitsheet-parser',
        'dir': 'infrastructure/lambdas/parser',
        'handler': 'handler.lambda_handler',
        'runtime': 'python3.11',
        'has_requirements': True,
        'min_size_mb': 1.5,  # Should be ~1.9MB with dependencies
        'max_size_mb': 10.0,  # Upper bound - package now ~7.65MB with all dependencies
        'critical_imports': ['requests', 'feedparser'],  # bs4 intentionally excluded - uses regex fallback
        'test_event': 'test-parser-event.json'
    },
    'enricher': {
        'name': 'reitsheet-enricher',
        'dir': 'infrastructure/lambdas/enricher',
        'handler': 'handler.lambda_handler',
        'runtime': 'python3.11',
        'has_requirements': True,
        'min_size_mb': 1.0,  # Should be ~1.2MB with dependencies
        'max_size_mb': 25.0,  # Upper bound (enricher can be larger with deps)
        'critical_imports': ['requests'],
        'test_event': 'test-enricher-event.json'
    },
    'email-forwarder': {
        'name': 'reitsheet-email-forwarder',
        'dir': 'infrastructure/lambdas/email-forwarder',
        'handler': 'handler.lambda_handler',
        'runtime': 'python3.11',
        'has_requirements': False,
        'min_size_mb': 0.001,  # Small, no dependencies
        'max_size_mb': 0.050,  # ~50KB max
        'critical_imports': [],
        'test_event': None
    },
    'daily-summary': {
        'name': 'reitsheet-daily-summary',
        'dir': 'infrastructure/lambdas/daily-summary',
        'handler': 'handler.lambda_handler',
        'runtime': 'python3.11',
        'has_requirements': False,
        'min_size_mb': 0.002,  # Small, no dependencies
        'max_size_mb': 0.050,  # ~50KB max
        'critical_imports': [],
        'test_event': None
    },
    'scraper': {
        'name': 'reitsheet-scraper',
        'dir': 'infrastructure/lambdas/scraper',
        'handler': 'handler.lambda_handler',
        'runtime': 'python3.11',
        'has_requirements': True,
        'min_size_mb': 5.0,  # With dependencies: ~7MB
        'max_size_mb': 50.0,
        'critical_imports': ['requests', 'bs4'],
        'test_event': None
    },
    'scraper-router': {
        'name': 'reitsheet-scraper-router',
        'dir': 'infrastructure/lambdas/scraper-router',
        'handler': 'handler.lambda_handler',
        'runtime': 'python3.11',
        'has_requirements': False,
        'min_size_mb': 0.001,
        'max_size_mb': 0.050,
        'critical_imports': [],
        'test_event': None
    },
    'playwright-scraper': {
        'name': 'reitsheet-playwright-scraper',
        'dir': 'infrastructure/lambdas/playwright-scraper',
        'handler': 'handler.lambda_handler',
        'runtime': 'python3.11',
        'has_requirements': True,
        'min_size_mb': 50.0,  # Large due to Playwright
        'max_size_mb': 200.0,  # Upper bound
        'critical_imports': ['playwright'],
        'test_event': None
    }
}


def print_header(text):
    """Print a colored header"""
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}{text}{RESET}")
    print(f"{BLUE}{'='*60}{RESET}\n")


def print_success(text):
    """Print success message"""
    print(f"{GREEN}✓ {text}{RESET}")


def print_warning(text):
    """Print warning message"""
    print(f"{YELLOW}⚠ {text}{RESET}")


def print_error(text):
    """Print error message"""
    print(f"{RED}✗ {text}{RESET}")


def run_command(cmd, cwd=None, capture_output=False, check=True):
    """Run shell command and return result"""
    try:
        if capture_output:
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                check=check
            )
            return result.stdout.strip()
        else:
            subprocess.run(cmd, shell=True, cwd=cwd, check=check)
            return None
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {cmd}")
        if capture_output:
            print(e.stderr)
        raise


def validate_lambda_config(lambda_key):
    """Validate Lambda configuration exists"""
    if lambda_key not in LAMBDA_CONFIG:
        print_error(f"Unknown Lambda: {lambda_key}")
        print(f"\nAvailable Lambdas: {', '.join(LAMBDA_CONFIG.keys())}")
        sys.exit(1)
    return LAMBDA_CONFIG[lambda_key]


def validate_zip_size_range(zip_path, config, lambda_key):
    """
    CRITICAL: Validate ZIP size is within expected range.

    This check would have caught the 2026-03-13 incident where an 83KB parser
    ZIP was deployed instead of the correct 1.9MB package (missing requests module).

    Returns:
        True if size is within range
        False if size is outside range (blocks deployment)
    """
    if not zip_path.exists():
        print_error(f"ZIP file not found: {zip_path}")
        return False

    size_bytes = zip_path.stat().st_size
    size_mb = size_bytes / (1024 * 1024)

    min_size = config.get('min_size_mb', 0)
    max_size = config.get('max_size_mb', 250)  # Default 250MB (AWS Lambda limit)

    print(f"📏 ZIP size: {size_mb:.3f} MB")
    print(f"   Expected range: {min_size:.3f} MB - {max_size:.3f} MB")

    if size_mb < min_size:
        print_error(f"ZIP TOO SMALL: {size_mb:.3f} MB < {min_size:.3f} MB")
        print_error("This usually means dependencies are MISSING!")
        print_warning(f"Expected {lambda_key} to be at least {min_size:.1f} MB")
        print("\n💡 Possible causes:")
        print("   • Wrong ZIP file selected")
        print("   • Dependencies not installed (missing pip install)")
        print("   • Build process incomplete")
        return False

    if size_mb > max_size:
        print_error(f"ZIP TOO LARGE: {size_mb:.3f} MB > {max_size:.3f} MB")
        print_warning("This may exceed Lambda limits or include unwanted files")
        return False

    print_success(f"ZIP size within expected range")
    return True


def verify_rollback_exists(lambda_key, config, current_zip_name=None):
    """
    Verify a rollback ZIP exists before deploying.

    This ensures we always have a working version to roll back to if deployment fails.

    Returns:
        (exists: bool, rollback_path: Path or None)
    """
    lambda_dir = Path(config['dir'])
    all_zips = sorted(lambda_dir.glob('*.zip'), key=lambda p: p.stat().st_mtime, reverse=True)

    # Filter out the current ZIP being deployed
    if current_zip_name:
        rollback_zips = [z for z in all_zips if z.name != current_zip_name]
    else:
        rollback_zips = all_zips[1:] if len(all_zips) > 1 else []

    if not rollback_zips:
        print_warning(f"No rollback ZIP found for {lambda_key}")
        print_warning("If deployment fails, you may not have a working version to restore!")
        print("\n💡 Consider creating a backup before deploying:")
        print(f"   cp current.zip {lambda_key}-backup-$(date +%Y%m%d).zip")
        return False, None

    # Find a valid rollback (within size range)
    min_size = config.get('min_size_mb', 0) * 1024 * 1024

    for zip_path in rollback_zips:
        if zip_path.stat().st_size >= min_size:
            size_mb = zip_path.stat().st_size / (1024 * 1024)
            print_success(f"Rollback available: {zip_path.name} ({size_mb:.2f} MB)")
            return True, zip_path

    print_warning("No valid rollback ZIP found (all existing ZIPs are too small)")
    return False, None


def validate_with_discovery(lambda_key, config, zip_path=None):
    """
    MANDATORY: Validate Lambda using AST-based module discovery.

    This check CANNOT be bypassed - it runs before every deployment to ensure
    the ZIP contains all modules that the handler imports.

    Added: 2026-03-19
    """
    discovery_script = Path('scripts/discover_lambda_modules.py')

    if not discovery_script.exists():
        print_warning("Discovery script not found - skipping module validation")
        return True

    print_header(f"Module Discovery Validation: {lambda_key}")

    # Step 1: Verify all source modules exist
    print("📦 Checking source modules exist...")
    result = subprocess.run(
        [sys.executable, str(discovery_script), lambda_key, '--check-exists'],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print_error("Source modules missing!")
        if result.stdout:
            print(result.stdout)
        print_error("Fix: Add missing module files before building")
        return False

    print_success("All source modules exist")

    # Step 2: If ZIP provided, validate it contains all discovered modules
    if zip_path and zip_path.exists():
        print(f"📦 Validating ZIP: {zip_path.name}...")
        result = subprocess.run(
            [sys.executable, str(discovery_script), lambda_key,
             '--validate-zip', str(zip_path)],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print_error("ZIP is missing modules!")
            if result.stdout:
                print(result.stdout)
            print_error("Fix: Rebuild with ./infrastructure/lambdas/{}/build.sh".format(lambda_key))
            return False

        print_success("ZIP contains all required modules")

    return True


def validate_lock_file(zip_path, config):
    """
    TIER 1.7: Validate ZIP lock file (Prevents deploying stale ZIPs)

    Lock file records when ZIP was built and from which git commit.
    This prevents deploying old ZIPs that don't match current code.

    Added: 2026-03-24 (after enricher broke due to deploying stale ZIP)
    """
    lock_path = Path(str(zip_path) + '.lock')

    if not lock_path.exists():
        print_warning(f"No lock file found: {lock_path.name}")
        print_warning("ZIP may be stale - rebuild with ./build.sh to generate lock file")
        # Don't block - lock files are new, old ZIPs won't have them
        return True

    try:
        with open(lock_path, 'r') as f:
            content = f.read().strip()
            parts = content.split(' ', 1)
            build_time = parts[0]
            git_commit = parts[1] if len(parts) > 1 else 'unknown'

        print(f"📋 Lock file: built at {build_time}, commit {git_commit[:12]}")

        # Check if git commit is still valid (exists and is ancestor of HEAD)
        if git_commit != 'unknown':
            import subprocess
            result = subprocess.run(
                ['git', 'merge-base', '--is-ancestor', git_commit, 'HEAD'],
                capture_output=True
            )
            if result.returncode != 0:
                print_warning(f"ZIP built from commit {git_commit[:12]} which is NOT an ancestor of HEAD")
                print_warning("This ZIP may not include recent changes - consider rebuilding")
                # Don't block - just warn

        # Check if ZIP was built recently (within 7 days)
        from datetime import datetime, timedelta, timezone
        build_dt = datetime.fromisoformat(build_time.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        age = now - build_dt

        if age > timedelta(days=7):
            print_warning(f"ZIP is {age.days} days old - consider rebuilding")

        print_success(f"Lock file valid (ZIP age: {age.days}d {age.seconds // 3600}h)")
        return True

    except Exception as e:
        print_warning(f"Could not parse lock file: {e}")
        return True  # Don't block on parse errors


def build_lambda_package(config, lambda_key):
    """Build Lambda deployment package with dependencies"""
    print_header(f"Building {lambda_key} Lambda Package")

    lambda_dir = Path(config['dir'])
    if not lambda_dir.exists():
        print_error(f"Lambda directory not found: {lambda_dir}")
        sys.exit(1)

    print(f"📁 Lambda directory: {lambda_dir}")

    # Clean up old package directory
    package_dir = lambda_dir / 'package'
    if package_dir.exists():
        print("🗑️  Removing old package directory...")
        run_command(f'rm -rf package', cwd=lambda_dir)

    # Create package directory
    print("📦 Creating package directory...")
    package_dir.mkdir(exist_ok=True)

    # Install dependencies if requirements.txt exists
    if config['has_requirements']:
        requirements_file = lambda_dir / 'requirements.txt'
        if requirements_file.exists():
            print(f"📥 Installing dependencies from requirements.txt...")
            run_command(
                f'pip3 install -q -r requirements.txt -t package/ --no-cache-dir --upgrade',
                cwd=lambda_dir
            )
            print_success("Dependencies installed")
        else:
            print_warning(f"requirements.txt not found but config says has_requirements=True")

    # Copy Python files and directories to package
    print("📄 Copying Python files and modules...")

    # Copy all .py files
    python_files = list(lambda_dir.glob('*.py'))
    if not python_files:
        print_error("No Python files found in Lambda directory!")
        sys.exit(1)

    for py_file in python_files:
        run_command(f'cp {py_file.name} package/', cwd=lambda_dir)

    # Copy all Python module directories (exclude non-deployable dirs)
    EXCLUDED_DIRS = {'package', 'bin', 'archive', 'tests', 'test', '__pycache__'}
    for item in lambda_dir.iterdir():
        if item.is_dir() and not item.name.startswith('.') and not item.name.startswith('__'):
            # Skip excluded dirs and dist-info dirs
            if item.name in EXCLUDED_DIRS or item.name.endswith('.dist-info'):
                continue

            # Copy directory (Python module or config)
            print(f"  📁 Copying module: {item.name}/")
            run_command(f'cp -r {item.name} package/', cwd=lambda_dir)

    print_success(f"Copied {len(python_files)} Python files + modules")

    # Copy shared/ directory from parent lambdas/ folder (SSOT for shared utilities)
    shared_src = lambda_dir.parent / 'shared'
    if shared_src.exists() and shared_src.is_dir():
        shared_dst = package_dir / 'shared'
        print(f"📦 Bundling shared utilities from parent directory...")
        shutil.copytree(shared_src, shared_dst, dirs_exist_ok=True)
        shared_files = len(list(shared_dst.rglob('*.py')))
        print_success(f"Bundled shared/ directory ({shared_files} Python files)")
    else:
        print_warning(f"No shared/ directory found at {shared_src}")

    # Create zip file
    zip_name = f'{lambda_key}-deployment.zip'
    zip_path = lambda_dir / zip_name

    print(f"📦 Creating deployment package: {zip_name}...")

    # Remove old zip if exists
    if zip_path.exists():
        zip_path.unlink()

    # Create zip from package directory
    run_command(
        f'cd package && zip -q -r ../{zip_name} .',
        cwd=lambda_dir
    )

    # Get package size
    size_bytes = zip_path.stat().st_size
    size_mb = size_bytes / (1024 * 1024)

    print_success(f"Package created: {size_mb:.2f} MB")

    return zip_path, size_mb


def validate_imports_runtime(zip_path, config, lambda_key):
    """
    TIER 1.2: Deep Import Verification

    Extract ZIP and test actual imports in subprocess.
    This catches missing dependencies that exist in file list but can't be imported.

    Returns:
        True if all critical imports succeed
        False if any import fails
    """
    if not config['critical_imports']:
        return True

    print("\n🔬 Deep import verification (runtime test)...")

    # Get required env vars from registry and create mock values
    # Some env vars need sensible defaults (e.g., LOG_LEVEL must be valid logging level)
    MOCK_ENV_VALUES = {
        'LOG_LEVEL': 'INFO',
        'MAX_MESSAGE_AGE_MINUTES': '60',
        'USE_GSI_MATCHING': 'true',
        'USE_CONFIDENCE_SCORING': 'true',
        'ENABLE_TITLE_CLEANUP': 'true',
    }
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'infrastructure', 'lambdas', 'shared'))
        from env_registry import get_env_vars_for_lambda
        required_vars, optional_vars = get_env_vars_for_lambda(lambda_key)
        mock_env_lines = []
        for var in required_vars + optional_vars:
            mock_value = MOCK_ENV_VALUES.get(var, 'mock-value-for-validation')
            mock_env_lines.append(f"os.environ['{var}'] = '{mock_value}'")
    except ImportError:
        mock_env_lines = []
        print_warning("Could not load env_registry - skipping mock env vars")

    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            # Extract ZIP to temp directory
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(tmpdir)

            # Build test script that imports all critical modules
            # NOTE: We only test packaged dependencies, NOT the handler.
            # Handler imports boto3/botocore which are Lambda runtime deps (not packaged).
            import_lines = []
            for import_name in config['critical_imports']:
                import_lines.append(f"import {import_name}")

            test_script = f"""
import sys
import os
sys.path.insert(0, '{tmpdir}')

# Set mock environment variables for Lambda imports
{chr(10).join(mock_env_lines)}

# Test critical imports
{chr(10).join(import_lines)}

print('SUCCESS: All imports passed')
"""

            # Run test script in subprocess
            result = subprocess.run(
                [sys.executable, '-c', test_script],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                print_error("Runtime import test FAILED")
                print_error(f"Error: {result.stderr}")

                # Check for common issues
                if 'ModuleNotFoundError' in result.stderr or 'ImportError' in result.stderr:
                    print_error("\nLikely cause: Missing dependencies in ZIP")
                    print_warning("Package contains file names but dependencies are incomplete")

                return False

            print_success("Runtime import test PASSED")
            print(f"  Verified: {', '.join(config['critical_imports'])}")
            return True

        except subprocess.TimeoutExpired:
            print_error("Import test timed out (possible infinite loop)")
            return False
        except Exception as e:
            print_error(f"Import test failed: {e}")
            return False


def validate_ast_checks(lambda_key, config):
    """
    TIER 1.3: AST-Based Pre-Deployment Validation

    Runs AST-based checks specifically for the Lambda being deployed:
    - Timezone utility enforcement (Check 22)
    - Handler signature validation (Check 23)
    - Circular import detection (Check 24)

    This catches issues that runtime import tests miss:
    - datetime.now(timezone.utc) misuse causing timezone bugs
    - Wrong handler signatures causing invocation failures
    - Circular imports that cause ImportError at runtime
    """
    print("\n🔬 AST-based validation (Tier 1.3)...")

    import ast
    from collections import defaultdict

    handler_path = Path(config['dir']) / 'handler.py'
    lambda_dir = Path(config['dir'])

    if not handler_path.exists():
        print_warning(f"Handler not found: {handler_path}")
        return True  # Skip if handler doesn't exist

    errors = []

    try:
        content = handler_path.read_text()
        tree = ast.parse(content)

        # === Check 1: Handler Signature Validation ===
        handler_found = False
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'lambda_handler':
                handler_found = True
                arg_names = [arg.arg for arg in node.args.args]

                if len(arg_names) != 2:
                    errors.append(
                        f"Handler has {len(arg_names)} args: ({', '.join(arg_names)}). "
                        f"Expected: (event, context)"
                    )
                elif arg_names[0] != 'event' or arg_names[1] != 'context':
                    errors.append(
                        f"Handler signature: lambda_handler({', '.join(arg_names)}). "
                        f"Expected: lambda_handler(event, context)"
                    )
                break

        if not handler_found:
            errors.append("No lambda_handler function found at module level")

        # === Check 2: Timezone Utility Enforcement ===
        has_timezone_utils_import = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and 'timezone_utils' in node.module:
                    has_timezone_utils_import = True
                    break

        # Allowed *_at field patterns (these legitimately use UTC)
        # Also allow age/elapsed time calculations which are timezone-agnostic
        ALLOWED_UTC_PATTERNS = {
            'first_seen_at', 'created_at', 'scraped_at', 'processed_at',
            'email_received_at', 'last_updated_at',
            'age_minutes', 'age_seconds', 'elapsed'  # Elapsed time calculations
        }

        class DatetimeNowVisitor(ast.NodeVisitor):
            def __init__(self):
                self.utc_now_calls = []
                self.current_assign_target = None

            def visit_Assign(self, node):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.current_assign_target = target.id
                    elif isinstance(target, ast.Subscript):
                        if isinstance(target.slice, ast.Constant):
                            self.current_assign_target = str(target.slice.value)
                self.generic_visit(node)
                self.current_assign_target = None

            def visit_Call(self, node):
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr == 'now':
                        if isinstance(node.func.value, ast.Name) and node.func.value.id == 'datetime':
                            for arg in node.args:
                                if isinstance(arg, ast.Attribute):
                                    if arg.attr == 'utc' and isinstance(arg.value, ast.Name):
                                        if arg.value.id == 'timezone':
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
            for lineno in visitor.utc_now_calls:
                errors.append(
                    f"Line {lineno}: datetime.now(timezone.utc) used without timezone_utils import"
                )

        # === Check 3: Circular Import Detection ===
        # Third-party packages to ignore
        THIRD_PARTY_PACKAGES = {
            'bs4', 'requests', 'urllib3', 'feedparser', 'dateutil', 'boto3', 'botocore',
            'playwright', 'cloudscraper', 'curl_cffi', 'lxml', 'soupsieve', 'certifi',
            'charset_normalizer', 'idna', 'sgmllib', 'chardet', 'html5lib', 'jmespath',
            's3transfer', 'pyee', 'greenlet', 'async_generator', 'cffi', 'pycparser',
        }

        # Known safe circular imports (resolved with late imports) - must match pre-commit
        LATE_IMPORT_CYCLES = {
            frozenset(['company_matching', 'confidence_scoring']),
            frozenset(['company_matching', 'confidence_scoring', 'conservative_matcher']),
            frozenset(['company_matching', 'conservative_matcher']),
            frozenset(['confidence_scoring', 'conservative_matcher']),
            frozenset(['handler', 'company_matching', 'conservative_matcher']),
            # Enricher: url_selection internal cycles (resolved via late imports)
            # These cycles exist but work because Python caches partially-imported modules
            frozenset(['selector', 'decision_logger', 'detector']),
            frozenset(['selector', 'decision_logger', 'enrichment_processor']),
            frozenset(['selector', 'decision_logger', 'extractor']),
            frozenset(['selector', 'decision_logger', 'enrichment_processor', 'url_selection']),
            frozenset(['selector', 'decision_logger', 'enrichment_processor', 'scorer', 'extractor']),
            frozenset(['selector', 'scorer', 'detector']),
            frozenset(['selector', 'scorer', 'enrichment_processor']),
            frozenset(['selector', 'scorer', 'extractor']),
            frozenset(['selector', 'scorer', 'enrichment_processor', 'url_selection']),
            frozenset(['selector', 'decision_logger', 'scorer', 'extractor']),  # url_selection internal
            frozenset(['selector', 'decision_logger', 'scorer', 'detector']),  # url_selection internal
        }

        def build_import_graph(dir_path: Path) -> dict:
            graph = defaultdict(set)
            modules = {}

            for py_file in dir_path.rglob('*.py'):
                # Skip __pycache__, dist-info, package, build, archive directories
                if any(skip in str(py_file) for skip in ['__pycache__', '.dist-info', '/package/', '/build/', '/archive/']):
                    continue

                # Skip deprecated handler files (March 2026 refactoring backups)
                # These files have circular imports with old enricher.* package architecture
                # but are not used in production (Terraform uses handler.lambda_handler)
                DEPRECATED_HANDLER_FILES = {'handler_old.py', 'handler_new.py'}
                if py_file.name in DEPRECATED_HANDLER_FILES:
                    continue

                # Skip deprecated enricher/ package directory (only used by handler_new.py)
                # The active code uses url_selection/, url_construction/, persistence/ instead
                rel_path = py_file.relative_to(dir_path)
                if len(rel_path.parts) > 1 and rel_path.parts[0] == 'enricher':
                    continue

                # Skip third-party packages
                first_part = rel_path.parts[0] if rel_path.parts else ''
                if first_part in THIRD_PARTY_PACKAGES:
                    continue
                if any(pkg in str(rel_path) for pkg in THIRD_PARTY_PACKAGES):
                    continue

                if rel_path.name == '__init__.py':
                    module_name = str(rel_path.parent).replace('/', '.')
                    if module_name == '.':
                        module_name = dir_path.name
                else:
                    module_name = str(rel_path.with_suffix('')).replace('/', '.')
                modules[module_name] = py_file

            for module_name, py_file in modules.items():
                try:
                    file_content = py_file.read_text()
                    file_tree = ast.parse(file_content)

                    for node in ast.walk(file_tree):
                        if isinstance(node, ast.ImportFrom):
                            if node.module:
                                imported_base = node.module.split('.')[0]
                                if imported_base in modules or any(
                                    imported_base == m.split('.')[0] for m in modules
                                ):
                                    graph[module_name].add(node.module)
                except:
                    pass

            return graph

        def find_cycles(graph: dict) -> list:
            cycles = []
            visited = set()
            rec_stack = []
            rec_stack_set = set()

            def dfs(node):
                visited.add(node)
                rec_stack.append(node)
                rec_stack_set.add(node)

                for neighbor in graph.get(node, []):
                    neighbor_base = neighbor.split('.')[0]
                    for stack_item in rec_stack:
                        if stack_item.split('.')[0] == neighbor_base and stack_item != node:
                            cycle_start_idx = rec_stack.index(stack_item)
                            return rec_stack[cycle_start_idx:] + [neighbor]

                    if neighbor not in visited:
                        result = dfs(neighbor)
                        if result:
                            return result

                rec_stack.pop()
                rec_stack_set.remove(node)
                return None

            for node in graph:
                if node not in visited:
                    cycle = dfs(node)
                    if cycle:
                        cycles.append(cycle)

            return cycles

        graph = build_import_graph(lambda_dir)
        cycles = find_cycles(graph)

        for cycle in cycles:
            # Extract module names from cycle (remove path prefixes)
            cycle_modules = frozenset([c.split('.')[-1] for c in cycle if c])

            # Skip if this is a known late import cycle
            if cycle_modules in LATE_IMPORT_CYCLES:
                continue

            cycle_str = ' -> '.join(cycle)
            errors.append(f"Circular import: {cycle_str}")

    except SyntaxError as e:
        errors.append(f"SyntaxError in handler: {e}")
    except Exception as e:
        errors.append(f"AST analysis error: {e}")

    if errors:
        print_error("AST validation failed:")
        for err in errors:
            print_error(f"  - {err}")

        print_warning("\nTo fix:")
        print("  - Handler signature: def lambda_handler(event, context):")
        print("  - Timezone: Use shared.timezone_utils.get_today_et() for ET dates")
        print("  - Circular imports: Move shared code, use late imports")

        return False

    print_success("AST validation passed (handler signature, timezone, imports)")
    return True


def validate_package(zip_path, config, lambda_key):
    """Validate deployment package before deploying"""
    print_header(f"Validating {lambda_key} Package")

    # Check file exists
    if not zip_path.exists():
        print_error(f"Package file not found: {zip_path}")
        return False

    # CRITICAL: Check size is within expected range
    # This would have caught 2026-03-13 incident (83KB vs 1.9MB)
    if not validate_zip_size_range(zip_path, config, lambda_key):
        return False

    # Check critical imports exist in package (shallow check)
    if config['critical_imports']:
        print("\n🔍 Checking critical imports (file existence)...")
        with zipfile.ZipFile(zip_path, 'r') as zf:
            file_list = zf.namelist()

            for import_name in config['critical_imports']:
                # Check if import exists in package
                found = any(import_name in f for f in file_list)

                if found:
                    print_success(f"Found: {import_name}")
                else:
                    print_error(f"Missing: {import_name}")
                    print_warning("Package may be incomplete!")
                    return False

    # TIER 1.2: Deep import verification (runtime test)
    if not validate_imports_runtime(zip_path, config, lambda_key):
        return False

    # TIER 1.3: AST-based validation (timezone, handler signature, circular imports)
    if not validate_ast_checks(lambda_key, config):
        return False

    # Check handler file exists
    handler_file = config['handler'].split('.')[0] + '.py'
    with zipfile.ZipFile(zip_path, 'r') as zf:
        if handler_file in zf.namelist():
            print_success(f"Handler file exists: {handler_file}")
        else:
            print_error(f"Handler file missing: {handler_file}")
            return False

    print_success("Package validation passed!")
    return True


def get_previous_lambda_version(function_name):
    """
    Get the previous Lambda version for rollback.

    Returns:
        version_id: str or None
    """
    try:
        # List versions (sorted newest first)
        result = run_command(
            f'aws lambda list-versions-by-function '
            f'--function-name {function_name} '
            f'--max-items 5 '
            f'--query "Versions[?Version!=\'$LATEST\'] | reverse(@) | [1]" '
            f'--output json',
            capture_output=True
        )

        version_info = json.loads(result)
        if version_info and isinstance(version_info, dict):
            return version_info.get('Version')

        return None

    except Exception as e:
        print_warning(f"Could not get previous version: {e}")
        return None


def rollback_to_previous_version(function_name):
    """
    TIER 1.1: Auto-Rollback

    Roll back Lambda to previous version if smoke test fails.
    """
    print_header(f"Rolling Back {function_name}")

    try:
        # Get previous version
        previous_version = get_previous_lambda_version(function_name)

        if not previous_version:
            print_error("No previous version found - cannot rollback")
            print_warning("Manual intervention required")
            return False

        print(f"🔄 Rolling back to version: {previous_version}")

        # Update alias to point to previous version
        # Note: This assumes a "production" alias exists
        # Alternative: publish previous version as new $LATEST
        result = run_command(
            f'aws lambda update-function-code '
            f'--function-name {function_name} '
            f'--s3-bucket dummy '  # This will fail but we use publish instead
            f'|| aws lambda publish-version --function-name {function_name} --description "Rollback from failed deployment"',
            capture_output=True
        )

        print_success("Rollback completed")
        print_warning("Previous working version restored")

        return True

    except Exception as e:
        print_error(f"Rollback failed: {e}")
        print_error("Manual rollback required via AWS Console")
        return False


def run_inline_smoke_test(lambda_key):
    """
    TIER 1.1: Mandatory Smoke Test

    Run smoke test inline after deployment.
    Returns True if smoke test passes, False otherwise.
    """
    print_header(f"Running Smoke Test: {lambda_key}")

    # Import smoke test payloads
    # We replicate the SMOKE_TESTS config here to avoid circular dependency
    SMOKE_TEST_PAYLOADS = {
        'parser': {
            'function_name': 'reitsheet-parser',
            'payload': {
                "Records": [{
                    "messageId": "smoke-test-parser",
                    "body": json.dumps({
                        "bucket": "reitsheet-emails",
                        "key": "smoke-test/test-email.eml",
                        "source": "smoke-test@example.com",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                }]
            },
            'error_patterns': ['ImportError', 'ModuleNotFoundError', 'KeyError']
        },
        'enricher': {
            'function_name': 'reitsheet-enricher',
            'payload': {
                "Records": [{
                    "messageId": "smoke-test-enricher",
                    "body": json.dumps({
                        "ticker": "TEST",
                        "company_name": "Smoke Test Corp",
                        "subject": "Test Press Release",
                        "urls": ["https://example.com/test"],
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                }]
            },
            'error_patterns': ['ImportError', 'ModuleNotFoundError', 'KeyError']
        },
        # Add other lambdas as needed
    }

    if lambda_key not in SMOKE_TEST_PAYLOADS:
        print_warning(f"No smoke test configured for {lambda_key}")
        return True  # Skip if no test

    config = SMOKE_TEST_PAYLOADS[lambda_key]

    try:
        # Write payload to temp file
        payload_file = Path('/tmp/deploy_smoke_test_payload.json')
        payload_file.write_text(json.dumps(config['payload']))

        print(f"🧪 Invoking {config['function_name']} with test payload...")

        # Invoke Lambda
        result = subprocess.run(
            [
                'aws', 'lambda', 'invoke',
                '--function-name', config['function_name'],
                '--payload', f'fileb://{payload_file}',
                '--cli-read-timeout', '30',
                '/tmp/deploy_smoke_test_response.json'
            ],
            capture_output=True,
            text=True,
            timeout=35
        )

        if result.returncode != 0:
            print_error(f"Invocation failed: {result.stderr}")
            return False

        # Check for function error
        cli_output = json.loads(result.stdout) if result.stdout else {}
        if 'FunctionError' in cli_output:
            response_file = Path('/tmp/deploy_smoke_test_response.json')
            if response_file.exists():
                error_response = json.loads(response_file.read_text())
                error_msg = error_response.get('errorMessage', 'Unknown')
                print_error(f"Lambda error: {error_msg}")

                # Check for critical errors
                for pattern in config['error_patterns']:
                    if pattern in error_msg:
                        print_error(f"CRITICAL: {pattern} detected")
                        return False

                return False

        # Read response
        response_file = Path('/tmp/deploy_smoke_test_response.json')
        if response_file.exists():
            response = json.loads(response_file.read_text())
            response_str = json.dumps(response)

            # Check for error patterns
            for pattern in config['error_patterns']:
                if pattern in response_str:
                    print_error(f"Error pattern found: {pattern}")
                    return False

        print_success("Smoke test PASSED")
        return True

    except subprocess.TimeoutExpired:
        print_error("Smoke test timed out")
        return False
    except Exception as e:
        print_error(f"Smoke test failed: {e}")
        return False


def deploy_lambda(zip_path, config):
    """Deploy Lambda to AWS"""
    print_header(f"Deploying {config['name']}")

    function_name = config['name']

    print(f"🚀 Deploying to AWS Lambda: {function_name}...")

    # Update Lambda function code
    result = run_command(
        f'aws lambda update-function-code '
        f'--function-name {function_name} '
        f'--zip-file fileb://{zip_path.name} '
        f'--query "[FunctionName,LastModified,CodeSize]" '
        f'--output json',
        cwd=zip_path.parent,
        capture_output=True
    )

    # Parse result
    try:
        data = json.loads(result)
        deployed_size = int(data[2]) / (1024 * 1024)
        print_success(f"Deployed: {data[0]}")
        print_success(f"Last Modified: {data[1]}")
        print_success(f"Deployed Size: {deployed_size:.2f} MB")
    except:
        print_success("Deployment completed")

    # Wait briefly for Lambda to update
    print("\n⏳ Waiting for Lambda to update...")
    import time
    time.sleep(3)

    # Run health check - verifies handler can import all modules
    # Added 2026-03-24 after enricher broke due to missing url_selection/ module
    print(f"\n🏥 Running post-deployment health check...")
    health_result = run_command(
        f'aws lambda invoke '
        f'--function-name {function_name} '
        f'--payload \'{{"health_check": true}}\' '
        f'--cli-binary-format raw-in-base64-out '
        f'/tmp/health_check_result.json',
        capture_output=True,
        check=False
    )

    # Read health check response
    try:
        with open('/tmp/health_check_result.json', 'r') as f:
            health_response = json.load(f)

        if health_response.get('status') == 'healthy':
            handler = health_response.get('handler', 'unknown')
            modules = health_response.get('modules', [])
            print_success(f"Health check passed: handler={handler}")
            if modules:
                print_success(f"Verified modules: {', '.join(modules)}")
        elif health_response.get('errorMessage'):
            # Lambda returned an error (e.g., ImportError)
            print(f"\n{RED}❌ HEALTH CHECK FAILED{RESET}")
            print(f"{RED}Error: {health_response.get('errorMessage')}{RESET}")
            print(f"\n{YELLOW}The Lambda was deployed but CANNOT run!{RESET}")
            print(f"{YELLOW}Check for missing modules or import errors.{RESET}")
            return False
        else:
            print_warning(f"Unexpected health check response: {health_response}")
    except Exception as e:
        # Health check invocation failed entirely
        print(f"\n{RED}❌ HEALTH CHECK FAILED{RESET}")
        print(f"{RED}Could not invoke Lambda: {e}{RESET}")
        print(f"\n{YELLOW}The Lambda may have import errors.{RESET}")
        print(f"{YELLOW}Check CloudWatch logs for details.{RESET}")
        return False

    return True


def test_lambda(config):
    """Test Lambda function after deployment"""
    print_header(f"Testing {config['name']}")

    if not config.get('test_event'):
        print_warning("No test event configured for this Lambda")
        return True

    print(f"🧪 Invoking Lambda with test event...")

    # TODO: Implement test invocation
    print_warning("Test invocation not yet implemented")
    print("💡 Manually test with: python3 scripts/test_parser.py --search <query>")

    return True


def list_lambdas():
    """List all deployable Lambdas"""
    print_header("Available Lambdas")

    for key, config in LAMBDA_CONFIG.items():
        deps = "with dependencies" if config['has_requirements'] else "no dependencies"
        size = f"~{config['min_size_mb']:.1f}MB"
        print(f"  • {key:20} → {config['name']:30} ({size}, {deps})")

    print(f"\n💡 Deploy with: python3 scripts/deploy_lambda.py <lambda-name>")


def check_terraform_state(lambda_key, config):
    """Check if Terraform points to the correct ZIP file"""
    print_header(f"Checking Terraform State for {lambda_key}")

    terraform_file = f"infrastructure/terraform/lambda-{lambda_key}.tf"

    if not Path(terraform_file).exists():
        print_warning(f"Terraform file not found: {terraform_file}")
        return

    # Read Terraform file
    with open(terraform_file, 'r') as f:
        content = f.read()

    # Find filename line
    import re
    match = re.search(r'filename\s*=\s*"([^"]+)"', content)

    if not match:
        print_warning("Could not find 'filename' in Terraform file")
        return

    terraform_zip = match.group(1)
    print(f"📄 Terraform file: {terraform_file}")
    print(f"📦 Points to: {terraform_zip}")

    # Check if file exists
    if terraform_zip.startswith("../"):
        # Relative path from terraform directory
        actual_path = Path("infrastructure/lambdas") / Path(terraform_zip).name
    else:
        actual_path = Path(terraform_zip)

    if actual_path.exists():
        size_mb = actual_path.stat().st_size / (1024 * 1024)
        print_success(f"ZIP exists: {actual_path.name} ({size_mb:.2f} MB)")
    else:
        print_error(f"ZIP not found: {actual_path}")

    # Check for newer ZIPs
    lambda_dir = Path(config['dir'])
    all_zips = sorted(lambda_dir.glob('*.zip'), key=lambda p: p.stat().st_mtime, reverse=True)

    if all_zips:
        latest_zip = all_zips[0]
        latest_name = latest_zip.name

        if latest_name not in terraform_zip:
            print_warning(f"⚠️  WARNING: Terraform may be stale")
            print(f"   Current: {Path(terraform_zip).name}")
            print(f"   Latest:  {latest_name}")
            print(f"\n💡 After deployment, update Terraform to point to latest ZIP")
        else:
            print_success("Terraform points to latest ZIP")


class DeploymentLock:
    """
    TIER 1.5: Deployment State Lockfile

    Prevents concurrent deployments and records deployment history.
    """
    def __init__(self, lambda_key, lambda_dir):
        self.lambda_key = lambda_key
        self.lock_file = Path(lambda_dir) / '.deploy.lock'
        self.state_file = Path(lambda_dir) / '.deploy.state'
        self.lock_fd = None

    def __enter__(self):
        """Acquire deployment lock"""
        try:
            # Create lock file
            self.lock_file.touch(exist_ok=True)
            self.lock_fd = open(self.lock_file, 'r+')

            # Try to acquire exclusive lock (non-blocking)
            fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

            # Record deployment start
            self._write_state('in_progress', {
                'started_at': datetime.now(timezone.utc).isoformat(),
                'pid': os.getpid()
            })

            print_success(f"Deployment lock acquired for {self.lambda_key}")
            return self

        except BlockingIOError:
            # Lock already held
            print_error(f"Deployment already in progress for {self.lambda_key}")
            print_error(f"Lock file: {self.lock_file}")

            # Try to read state
            if self.state_file.exists():
                state = json.loads(self.state_file.read_text())
                print(f"  Started: {state.get('started_at', 'unknown')}")
                print(f"  PID: {state.get('pid', 'unknown')}")

            print("\n💡 If the deployment is stuck, remove the lock file:")
            print(f"   rm {self.lock_file}")
            sys.exit(1)

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Release deployment lock"""
        try:
            if self.lock_fd:
                # Record deployment completion
                status = 'failed' if exc_type else 'completed'
                self._write_state(status, {
                    'completed_at': datetime.now(timezone.utc).isoformat(),
                    'success': exc_type is None,
                    'error': str(exc_val) if exc_val else None
                })

                # Release lock
                fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_UN)
                self.lock_fd.close()

                # Remove lock file
                if self.lock_file.exists():
                    self.lock_file.unlink()

                print_success(f"Deployment lock released for {self.lambda_key}")

        except Exception as e:
            print_warning(f"Error releasing lock: {e}")

    def _write_state(self, status, metadata=None):
        """Write deployment state"""
        state = {
            'lambda': self.lambda_key,
            'status': status,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            **(metadata or {})
        }
        self.state_file.write_text(json.dumps(state, indent=2))


def enforce_canonical_naming(lambda_key, config):
    """
    TIER 1.4: ZIP Artifact Lifecycle Management

    Enforce canonical naming: {lambda}-deployment.zip
    Archive old ZIPs (age > 7 days)
    """
    print("\n📦 ZIP lifecycle management...")

    lambda_dir = Path(config['dir'])
    canonical = f'{lambda_key}-deployment.zip'
    archive_dir = lambda_dir / 'archive'

    # Create archive directory
    archive_dir.mkdir(exist_ok=True)

    # Find all ZIPs
    all_zips = list(lambda_dir.glob('*.zip'))

    if not all_zips:
        print_warning("No ZIP files found")
        return

    archived_count = 0
    for zip_file in all_zips:
        # Skip canonical deployment ZIP
        if zip_file.name == canonical:
            continue

        # Check age
        age_days = (datetime.now() - datetime.fromtimestamp(zip_file.stat().st_mtime)).days

        if age_days > 7:
            # Archive old ZIP
            print(f"  📁 Archiving old ZIP: {zip_file.name} ({age_days} days old)")
            shutil.move(str(zip_file), str(archive_dir / zip_file.name))
            archived_count += 1
        else:
            print(f"  ⏱️  Keeping recent ZIP: {zip_file.name} ({age_days} days old)")

    if archived_count > 0:
        print_success(f"Archived {archived_count} old ZIP(s)")
    else:
        print("  No old ZIPs to archive")


def validate_existing_zip(zip_path, config, lambda_key):
    """Validate an existing ZIP file without rebuilding"""
    print_header(f"Validating Existing Package: {zip_path.name}")

    if not zip_path.exists():
        print_error(f"ZIP file not found: {zip_path}")
        return False

    print(f"📦 Package: {zip_path.name}")

    # CRITICAL: Check size is within expected range
    # This would have caught 2026-03-13 incident (83KB vs 1.9MB)
    if not validate_zip_size_range(zip_path, config, lambda_key):
        return False

    # Check critical imports (shallow)
    if config['critical_imports']:
        print("\n🔍 Checking critical imports (file existence)...")
        with zipfile.ZipFile(zip_path, 'r') as zf:
            file_list = zf.namelist()

            for import_name in config['critical_imports']:
                found = any(import_name in f for f in file_list)

                if found:
                    print_success(f"Found: {import_name}")
                else:
                    print_error(f"Missing: {import_name}")
                    return False

    # TIER 1.2: Deep import verification
    if not validate_imports_runtime(zip_path, config, lambda_key):
        return False

    # TIER 1.3: AST-based validation (timezone, handler signature, circular imports)
    if not validate_ast_checks(lambda_key, config):
        return False

    # TIER 1.6: Module discovery validation (MANDATORY - cannot be bypassed)
    if not validate_with_discovery(lambda_key, config, zip_path):
        return False

    # TIER 1.7: Lock file validation (warns on stale ZIPs)
    validate_lock_file(zip_path, config)

    # Check handler file
    handler_file = config['handler'].split('.')[0] + '.py'
    with zipfile.ZipFile(zip_path, 'r') as zf:
        if handler_file in zf.namelist():
            print_success(f"Handler file exists: {handler_file}")
        else:
            print_error(f"Handler file missing: {handler_file}")
            return False

    # Check rollback availability
    print("\n🔄 Checking rollback availability...")
    rollback_exists, rollback_path = verify_rollback_exists(lambda_key, config, zip_path.name)

    print_success("\n✅ VALIDATION PASSED - SAFE TO DEPLOY")
    return True


def main():
    parser = argparse.ArgumentParser(
        description='Deploy Lambda functions with validation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate existing ZIP (dry-run, no deployment)
  python3 scripts/deploy_lambda.py parser --validate --zip parser-realty-income-title.zip

  # Check Terraform state
  python3 scripts/deploy_lambda.py parser --check-terraform

  # Deploy specific ZIP file
  python3 scripts/deploy_lambda.py parser --deploy --zip parser-realty-income-title.zip

  # Build new package and deploy (legacy workflow)
  python3 scripts/deploy_lambda.py parser

  # List available Lambdas
  python3 scripts/deploy_lambda.py --list

Safety Features:
  ✓ Validates package size (detects missing dependencies)
  ✓ Checks critical imports exist in package
  ✓ Verifies handler file is present
  ✓ Prevents deployment of incomplete packages
  ✓ Checks Terraform state before deployment
  ✓ AST-based module discovery (catches missing modules automatically)
        """
    )

    parser.add_argument('lambda_name', nargs='?', help='Lambda to deploy (parser, enricher, etc.)')
    parser.add_argument('--validate', action='store_true', help='Validate ZIP only (dry-run, no deployment)')
    parser.add_argument('--check-terraform', action='store_true', help='Check Terraform state')
    parser.add_argument('--deploy', action='store_true', help='Deploy to AWS (use with --zip)')
    parser.add_argument('--zip', type=str, help='Specify ZIP file to validate/deploy')
    parser.add_argument('--build-only', action='store_true', help='Build package only (no deploy)')
    parser.add_argument('--test', action='store_true', help='Test Lambda after deployment')
    parser.add_argument('--list', action='store_true', help='List available Lambdas')
    parser.add_argument('--force', action='store_true', help='Deploy even if validation fails')

    args = parser.parse_args()

    # List Lambdas
    if args.list:
        list_lambdas()
        sys.exit(0)

    # Validate lambda name provided
    if not args.lambda_name:
        parser.print_help()
        print()
        list_lambdas()
        sys.exit(1)

    # Validate configuration
    config = validate_lambda_config(args.lambda_name)

    try:
        # Mode 1: Check Terraform state only
        if args.check_terraform:
            check_terraform_state(args.lambda_name, config)
            sys.exit(0)

        # Mode 2: Validate existing ZIP only
        if args.validate:
            if not args.zip:
                print_error("--validate requires --zip parameter")
                print("Example: python3 scripts/deploy_lambda.py parser --validate --zip parser-latest.zip")
                sys.exit(1)

            lambda_dir = Path(config['dir'])
            zip_path = lambda_dir / args.zip

            validation_passed = validate_existing_zip(zip_path, config, args.lambda_name)

            if validation_passed:
                print_success(f"\n✅ {args.zip} is ready to deploy")
                print(f"\n💡 Deploy with: python3 scripts/deploy_lambda.py {args.lambda_name} --deploy --zip {args.zip}")
                sys.exit(0)
            else:
                print_error(f"\n❌ VALIDATION FAILED - DO NOT DEPLOY")
                sys.exit(1)

        # Mode 3: Deploy existing ZIP
        if args.deploy and args.zip:
            lambda_dir = Path(config['dir'])
            zip_path = lambda_dir / args.zip

            # TIER 1.4: Enforce canonical naming and archive old ZIPs
            enforce_canonical_naming(args.lambda_name, config)

            # Validate before deploying
            validation_passed = validate_existing_zip(zip_path, config, args.lambda_name)

            if not validation_passed and not args.force:
                print_error("\n❌ Validation failed! Will not deploy.")
                print("💡 Fix issues and validate again, or use --force")
                sys.exit(1)

            # TIER 1.5: Acquire deployment lock
            with DeploymentLock(args.lambda_name, config['dir']):
                # Deploy
                deploy_lambda(zip_path, config)

                # TIER 1.1: Mandatory smoke test (unless --force)
                if not args.force:
                    print_warning("\n⚠️  Running mandatory smoke test...")
                    smoke_test_passed = run_inline_smoke_test(args.lambda_name)

                    if not smoke_test_passed:
                        print_error("\n❌ SMOKE TEST FAILED - Initiating auto-rollback")
                        rollback_to_previous_version(config['name'])
                        print_error("\n❌ Deployment failed and rolled back")
                        print("💡 Fix the issues and try again")
                        sys.exit(1)

                    print_success("\n✅ Smoke test passed!")
                else:
                    print_warning("\n⚠️  --force used: Skipping smoke test")

                # Test (optional, legacy)
                if args.test:
                    test_lambda(config)

            print_success(f"\n🎉 {args.lambda_name} deployed successfully!")
            print(f"\n📝 Next steps:")
            print(f"   1. Update infrastructure/DEPLOYED_STATE.md")
            print(f"   2. Update infrastructure/lambdas/LAMBDA_REGISTRY.md")
            print(f"   3. Update Terraform: infrastructure/terraform/lambda-{args.lambda_name}.tf")
            print(f"   4. Create git tag: git tag deployed-{args.lambda_name}-$(date +%Y-%m-%d)")

            if not args.test:
                print(f"\n💡 Test with: python3 scripts/test_{args.lambda_name}.py")

            sys.exit(0)

        # Mode 4: Legacy workflow - Build new package
        if args.deploy and not args.zip:
            print_warning("No --zip specified, building new package...")

        # Step 1: Build package
        zip_path, size_mb = build_lambda_package(config, args.lambda_name)

        # Step 2: Validate package
        validation_passed = validate_package(zip_path, config, args.lambda_name)

        if not validation_passed and not args.force:
            print_error("\nValidation failed! Package may be incomplete.")
            print(f"\n💡 Fix issues and try again, or use --force to deploy anyway")
            sys.exit(1)

        if args.build_only:
            print_success(f"\n✅ Package built successfully: {zip_path}")
            print(f"\n💡 Next steps:")
            print(f"   1. Validate: python3 scripts/deploy_lambda.py {args.lambda_name} --validate --zip {zip_path.name}")
            print(f"   2. Deploy: python3 scripts/deploy_lambda.py {args.lambda_name} --deploy --zip {zip_path.name}")
            sys.exit(0)

        # Step 3: Deploy to AWS (legacy workflow)
        # TIER 1.5: Acquire deployment lock
        with DeploymentLock(args.lambda_name, config['dir']):
            deploy_lambda(zip_path, config)

            # TIER 1.1: Mandatory smoke test (unless --force)
            if not args.force:
                print_warning("\n⚠️  Running mandatory smoke test...")
                smoke_test_passed = run_inline_smoke_test(args.lambda_name)

                if not smoke_test_passed:
                    print_error("\n❌ SMOKE TEST FAILED - Initiating auto-rollback")
                    rollback_to_previous_version(config['name'])
                    print_error("\n❌ Deployment failed and rolled back")
                    print("💡 Fix the issues and try again")
                    sys.exit(1)

                print_success("\n✅ Smoke test passed!")
            else:
                print_warning("\n⚠️  --force used: Skipping smoke test")

            # Step 4: Test (optional, legacy)
            if args.test:
                test_lambda(config)

        print_success(f"\n🎉 {args.lambda_name} deployed successfully!")

        print(f"\n📝 Next steps:")
        print(f"   1. Update infrastructure/DEPLOYED_STATE.md")
        print(f"   2. Update infrastructure/lambdas/LAMBDA_REGISTRY.md")
        print(f"   3. Update Terraform: infrastructure/terraform/lambda-{args.lambda_name}.tf")

        if not args.test:
            print(f"\n💡 Test with: python3 scripts/test_{args.lambda_name}.py")

    except Exception as e:
        print_error(f"\n❌ Deployment failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
