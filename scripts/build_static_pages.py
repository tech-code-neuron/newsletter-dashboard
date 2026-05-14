#!/usr/bin/env python3
"""
Build Static Pages for S3 Homepage

Generates static HTML pages from Flask/Jinja2 templates, ensuring consistency
between app.your-domain.com and your-domain.com.

Usage:
    python scripts/build_static_pages.py                    # Build all pages
    python scripts/build_static_pages.py --page privacy     # Build specific page
    python scripts/build_static_pages.py --dry-run          # Preview without writing
    python scripts/build_static_pages.py --css              # Also copy CSS

SOLID Principle: Single source of truth - templates + config generate both
Flask dynamic pages and S3 static pages.
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add Flask app to path
PROJECT_ROOT = Path(__file__).parent.parent
FLASK_APP_PATH = PROJECT_ROOT / 'infrastructure' / 'docker' / 'flask-app'
sys.path.insert(0, str(FLASK_APP_PATH))
sys.path.insert(0, str(PROJECT_ROOT))

from jinja2 import Environment, FileSystemLoader, select_autoescape

# Try to import Python config modules (preferred)
# Fall back to JSON config if Python modules not available
USE_PYTHON_CONFIG = False
try:
    from config.design_tokens import COLORS, TYPOGRAPHY, SPACING, BORDERS
    from config.site_config import get_public_config
    USE_PYTHON_CONFIG = True
except ImportError:
    pass


# =============================================================================
# CONFIGURATION
# =============================================================================

OUTPUT_DIR = PROJECT_ROOT / 'infrastructure' / 's3-homepage'
TEMPLATE_DIR = FLASK_APP_PATH / 'templates' / 'public'
JSON_CONFIG_PATH = FLASK_APP_PATH / 'config' / 'site_config.json'

# Pages to build (template name -> output filename)
PAGES = {
    "check-email": {
        "template": "pages/check-email.html",
        "output": "check-email.html",
        "title": "Check Your Email - Press Release Pipeline",
    },
    "signup-error": {
        "template": "pages/signup-error.html",
        "output": "signup-error.html",
        "title": "Error - Press Release Pipeline",
    },
    "subscribed": {
        "template": "pages/subscribed.html",
        "output": "subscribed.html",
        "title": "Subscribed - Press Release Pipeline",
    },
    "unsubscribed": {
        "template": "pages/unsubscribed.html",
        "output": "unsubscribed.html",
        "title": "Unsubscribed - Press Release Pipeline",
    },
    "privacy": {
        "template": "pages/privacy.html",
        "output": "privacy.html",
        "title": "Privacy Policy - Press Release Pipeline",
    },
}


# =============================================================================
# CONFIG LOADING
# =============================================================================

def load_config() -> dict:
    """Load site configuration from Python module or JSON file."""
    if USE_PYTHON_CONFIG:
        config = get_public_config()
        # Add design tokens
        config['colors'] = COLORS
        config['typography'] = TYPOGRAPHY
        config['spacing'] = SPACING
        config['borders'] = BORDERS
        return config
    else:
        # Fall back to JSON config
        with open(JSON_CONFIG_PATH) as f:
            return json.load(f)


# =============================================================================
# TEMPLATE SETUP
# =============================================================================

def create_jinja_env() -> Environment:
    """Create Jinja2 environment with Flask-like configuration."""
    env = Environment(
        loader=FileSystemLoader([
            str(TEMPLATE_DIR),
            str(FLASK_APP_PATH / 'templates'),
        ]),
        autoescape=select_autoescape(['html', 'xml']),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    # Add template filters
    env.filters['format_date'] = lambda d, fmt: d.strftime(fmt) if d else ''

    return env


def get_base_context() -> dict:
    """Get base context for all pages."""
    today = datetime.now()
    yesterday = today - timedelta(days=1)

    config = load_config()

    return {
        'config': config,
        'today': today,
        'yesterday': yesterday,
        'current_date': today.strftime('%A, %B %d, %Y'),
        'static_build': True,  # Flag for template to use static CSS paths
    }


# =============================================================================
# BUILD FUNCTIONS
# =============================================================================

def build_page(env: Environment, page_key: str, dry_run: bool = False) -> bool:
    """
    Build a single static page.

    Args:
        env: Jinja2 environment
        page_key: Key from PAGES dict
        dry_run: If True, don't write files

    Returns:
        True if successful, False otherwise
    """
    if page_key not in PAGES:
        print(f"Error: Unknown page '{page_key}'")
        return False

    page_config = PAGES[page_key]
    template_path = page_config['template']
    output_path = OUTPUT_DIR / page_config['output']

    print(f"Building {page_key}...")
    print(f"  Template: {template_path}")
    print(f"  Output: {output_path}")

    try:
        template = env.get_template(template_path)
    except Exception as e:
        print(f"  Error loading template: {e}")
        return False

    # Get context
    context = get_base_context()
    context['page_title'] = page_config.get('title', 'Press Release Pipeline')

    try:
        html = template.render(**context)
    except Exception as e:
        print(f"  Error rendering template: {e}")
        return False

    if dry_run:
        print(f"  [DRY RUN] Would write {len(html)} bytes")
        return True

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding='utf-8')
        print(f"  Wrote {len(html)} bytes")
        return True
    except Exception as e:
        print(f"  Error writing file: {e}")
        return False


def build_all_pages(dry_run: bool = False) -> int:
    """
    Build all static pages.

    Returns:
        Number of pages that failed to build
    """
    env = create_jinja_env()
    failures = 0

    print(f"Building {len(PAGES)} pages...")
    print(f"Output directory: {OUTPUT_DIR}")
    if USE_PYTHON_CONFIG:
        print("Using Python config modules (design_tokens.py, site_config.py)")
    else:
        print(f"Using JSON config: {JSON_CONFIG_PATH}")
    print()

    for page_key in PAGES:
        if not build_page(env, page_key, dry_run):
            failures += 1
        print()

    return failures


# =============================================================================
# CSS BUILD
# =============================================================================

def build_css(dry_run: bool = False) -> bool:
    """
    Build combined CSS for S3 homepage.

    Combines variables.css + public.css into public-styles.css
    """
    variables_css = FLASK_APP_PATH / 'static' / 'css' / 'variables.css'
    public_css = FLASK_APP_PATH / 'static' / 'css' / 'pages' / 'public.css'
    dest = OUTPUT_DIR / 'public-styles.css'

    print("Building CSS...")

    if not variables_css.exists():
        print(f"  Warning: variables.css not found: {variables_css}")
        return False

    if not public_css.exists():
        print(f"  Warning: public.css not found: {public_css}")
        return False

    print(f"  Combining: variables.css + public.css")
    print(f"  Output: {dest}")

    if dry_run:
        print("  [DRY RUN] Would combine CSS")
        return True

    try:
        # Read and combine CSS files
        variables_content = variables_css.read_text(encoding='utf-8')
        public_content = public_css.read_text(encoding='utf-8')

        combined = f"""/* Combined CSS for Press Release Pipeline Static Pages
   Generated by build_static_pages.py
   Contains: variables.css + public.css
*/

{variables_content}

{public_content}
"""
        dest.write_text(combined, encoding='utf-8')
        print(f"  Wrote {len(combined)} bytes")
        return True
    except Exception as e:
        print(f"  Error: {e}")
        return False


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Build static pages for S3 homepage'
    )
    parser.add_argument(
        '--page',
        choices=list(PAGES.keys()),
        help='Build specific page only'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview without writing files'
    )
    parser.add_argument(
        '--css',
        action='store_true',
        help='Also build CSS'
    )
    parser.add_argument(
        '--list',
        action='store_true',
        help='List available pages'
    )

    args = parser.parse_args()

    if args.list:
        print("Available pages:")
        for key, config in PAGES.items():
            print(f"  {key}: {config['template']} -> {config['output']}")
        return 0

    print("=" * 60)
    print("S3 STATIC PAGE BUILDER")
    print("=" * 60)
    print()

    if args.dry_run:
        print("[DRY RUN MODE - No files will be written]")
        print()

    if args.page:
        env = create_jinja_env()
        success = build_page(env, args.page, args.dry_run)
        failures = 0 if success else 1
    else:
        failures = build_all_pages(args.dry_run)

    if args.css:
        print()
        if not build_css(args.dry_run):
            failures += 1

    print("=" * 60)
    if failures == 0:
        print("BUILD COMPLETE - All pages built successfully")
    else:
        print(f"BUILD COMPLETE - {failures} page(s) failed")
    print("=" * 60)

    print("\nTo deploy:")
    print("  aws s3 sync infrastructure/s3-homepage/ s3://reitsheet-homepage/ --exclude 'index.html'")
    print("  aws cloudfront create-invalidation --distribution-id E1OJKTRGT9KX3A --paths '/*'")

    return failures


if __name__ == "__main__":
    sys.exit(main())
