#!/usr/bin/env python3
"""
Design Token Build Script

Generates CSS variables and Python email styles from a single JSON source.
Run this whenever design-tokens.json changes.

Usage:
    python3 scripts/build_design_tokens.py

Outputs:
    - infrastructure/docker/flask-app/static/css/variables.css
    - infrastructure/docker/flask-app/config/email_styles.py
"""

import json
import os
from datetime import datetime
from pathlib import Path


# Paths relative to project root
PROJECT_ROOT = Path(__file__).parent.parent
FLASK_APP = PROJECT_ROOT / "infrastructure" / "docker" / "flask-app"
TOKENS_JSON = FLASK_APP / "config" / "design-tokens.json"
CSS_OUTPUT = FLASK_APP / "static" / "css" / "variables.css"
EMAIL_STYLES_OUTPUT = FLASK_APP / "config" / "email_styles.py"


def load_tokens() -> dict:
    """Load design tokens from JSON file."""
    with open(TOKENS_JSON, 'r') as f:
        return json.load(f)


def generate_css_variables(tokens: dict) -> str:
    """Generate CSS :root variables from design tokens."""
    lines = [
        '/**',
        ' * Design Tokens - CSS Variables',
        ' *',
        ' * AUTO-GENERATED - DO NOT EDIT DIRECTLY',
        f' * Generated from: config/design-tokens.json',
        f' * Generated at: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
        ' *',
        ' * To modify these values, edit config/design-tokens.json',
        ' * then run: python3 scripts/build_design_tokens.py',
        ' */',
        '',
        ':root {'
    ]

    # Category to CSS prefix mapping
    category_prefixes = {
        'color': 'color',
        'spacing': 'spacing',
        'spacing-mobile': 'spacing-mobile',
        'spacing-touch': 'touch',
        'typography': 'font',
        'typography-mobile': 'font-size-mobile',
        'sizing': '',  # sizing values already have width-/height- prefixes
        'border': 'border',
        'shadow': 'shadow',
        'z-index': 'z',
        'transition': 'transition',
        'opacity': 'opacity',
        'breakpoint': 'breakpoint',
    }

    # Category comments
    category_comments = {
        'color': 'COLORS - Brand & UI',
        'spacing': 'SPACING - Consistent rhythm',
        'spacing-mobile': 'SPACING - Mobile (tighter for smaller screens)',
        'spacing-touch': 'SPACING - Touch targets',
        'typography': 'TYPOGRAPHY - Font sizing',
        'typography-mobile': 'TYPOGRAPHY - Mobile (optimized for smaller screens)',
        'sizing': 'SIZING - Dimensions',
        'border': 'BORDERS - Radius and widths',
        'shadow': 'SHADOWS - Depth',
        'z-index': 'Z-INDEX - Layering',
        'transition': 'TRANSITIONS - Animation timing',
        'opacity': 'OPACITY - Transparency levels',
        'breakpoint': 'RESPONSIVE BREAKPOINTS',
    }

    for category, category_tokens in tokens.items():
        prefix = category_prefixes.get(category, category)
        comment = category_comments.get(category, category.upper())

        lines.append('')
        lines.append(f'    /* {"=" * 72}')
        lines.append(f'       {comment}')
        lines.append(f'       {"=" * 72} */')
        lines.append('')

        for token_name, token_data in category_tokens.items():
            value = token_data['value']
            description = token_data.get('description', '')

            # Build CSS variable name
            if prefix and not token_name.startswith(prefix.split('-')[0]):
                css_var_name = f"--{prefix}-{token_name}"
            elif prefix:
                css_var_name = f"--{token_name}"
            else:
                css_var_name = f"--{token_name}"

            # Handle special cases
            if category == 'sizing':
                css_var_name = f"--{token_name}"
            elif category == 'typography':
                if token_name.startswith('font-'):
                    css_var_name = f"--{token_name.replace('font-', 'font-family-')}"
                elif token_name.startswith('size-'):
                    css_var_name = f"--font-{token_name}"
                elif token_name.startswith('weight-'):
                    css_var_name = f"--font-{token_name}"
                elif token_name.startswith('line-'):
                    css_var_name = f"--{token_name}"
            elif category == 'typography-mobile':
                css_var_name = f"--font-size-mobile-{token_name.replace('size-', '')}"
            elif category == 'spacing-touch':
                if token_name.startswith('target-'):
                    css_var_name = f"--touch-{token_name}"
                else:
                    css_var_name = f"--spacing-touch-{token_name}"

            # Add comment for description
            if description:
                lines.append(f"    {css_var_name}: {value};  /* {description} */")
            else:
                lines.append(f"    {css_var_name}: {value};")

    # Add radius aliases for compatibility
    lines.append('')
    lines.append('    /* ========================================================================')
    lines.append('       ALIASES - Short names for convenience')
    lines.append('       ======================================================================== */')
    lines.append('')
    lines.append('    --radius-sm: var(--border-radius-sm);')
    lines.append('    --radius-md: var(--border-radius-md);')
    lines.append('    --radius-lg: var(--border-radius-lg);')
    lines.append('    --radius-xl: var(--border-radius-xl);')

    lines.append('}')
    lines.append('')

    return '\n'.join(lines)


def generate_email_styles(tokens: dict) -> str:
    """Generate Python email styles dictionary from design tokens."""
    lines = [
        '"""',
        'Email Styles - Inline CSS for HTML Emails',
        '',
        'AUTO-GENERATED - DO NOT EDIT DIRECTLY',
        f'Generated from: config/design-tokens.json',
        f'Generated at: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
        '',
        'To modify these values, edit config/design-tokens.json',
        'then run: python3 scripts/build_design_tokens.py',
        '',
        'Usage:',
        '    from config.email_styles import EMAIL_STYLES',
        '    style = EMAIL_STYLES["colors"]["primary"]',
        '"""',
        '',
        '# Raw token values for use in inline styles',
        'EMAIL_STYLES = {',
    ]

    for category, category_tokens in tokens.items():
        # Convert category name to Python-friendly key
        py_category = category.replace('-', '_')
        lines.append(f"    '{py_category}': {{")

        for token_name, token_data in category_tokens.items():
            value = token_data['value']
            # Convert token name to Python-friendly key
            py_name = token_name.replace('-', '_')
            # Escape single quotes in values (e.g., font families)
            escaped_value = value.replace("'", "\\'")
            lines.append(f"        '{py_name}': '{escaped_value}',")

        lines.append('    },')

    lines.append('}')
    lines.append('')
    lines.append('')
    lines.append('# Convenience accessors')
    lines.append('def get_color(name: str) -> str:')
    lines.append('    """Get a color value by name (use underscores, e.g., \'primary_hover\')."""')
    lines.append("    return EMAIL_STYLES['color'].get(name, EMAIL_STYLES['color']['text'])")
    lines.append('')
    lines.append('')
    lines.append('def get_spacing(name: str) -> str:')
    lines.append('    """Get a spacing value by name."""')
    lines.append("    return EMAIL_STYLES['spacing'].get(name, EMAIL_STYLES['spacing']['md'])")
    lines.append('')
    lines.append('')
    lines.append('def get_font(name: str) -> str:')
    lines.append('    """Get a typography value by name."""')
    lines.append("    return EMAIL_STYLES['typography'].get(name, '')")
    lines.append('')
    lines.append('')
    lines.append('# Pre-built inline style strings for common email elements')
    lines.append('INLINE_STYLES = {')
    lines.append("    'body': f\"font-family: {EMAIL_STYLES['typography']['font_ui']}; color: {EMAIL_STYLES['color']['text']}; background-color: {EMAIL_STYLES['color']['bg']}; line-height: {EMAIL_STYLES['typography']['line_height_base']};\",")
    lines.append("    'heading': f\"font-family: {EMAIL_STYLES['typography']['font_ui']}; color: {EMAIL_STYLES['color']['text_dark']}; font-weight: {EMAIL_STYLES['typography']['weight_bold']};\",")
    lines.append("    'link': f\"color: {EMAIL_STYLES['color']['primary']}; text-decoration: none;\",")
    lines.append("    'muted': f\"color: {EMAIL_STYLES['color']['text_muted']}; font-size: {EMAIL_STYLES['typography']['size_sm']};\",")
    lines.append("    'card': f\"background-color: {EMAIL_STYLES['color']['bg_card']}; border: 1px solid {EMAIL_STYLES['color']['border']}; border-radius: {EMAIL_STYLES['border']['radius_md']}; padding: {EMAIL_STYLES['spacing']['md']};\",")
    lines.append("    'button_primary': f\"background-color: {EMAIL_STYLES['color']['primary']}; color: #ffffff; padding: {EMAIL_STYLES['spacing']['sm']} {EMAIL_STYLES['spacing']['md']}; border-radius: {EMAIL_STYLES['border']['radius_md']}; text-decoration: none; display: inline-block;\",")
    lines.append("    'button_success': f\"background-color: {EMAIL_STYLES['color']['success']}; color: #ffffff; padding: {EMAIL_STYLES['spacing']['sm']} {EMAIL_STYLES['spacing']['md']}; border-radius: {EMAIL_STYLES['border']['radius_md']}; text-decoration: none; display: inline-block;\",")
    lines.append("    'alert_success': f\"background-color: {EMAIL_STYLES['color']['success_bg']}; border: 1px solid {EMAIL_STYLES['color']['success_border']}; color: {EMAIL_STYLES['color']['success_text']}; padding: {EMAIL_STYLES['spacing']['md']}; border-radius: {EMAIL_STYLES['border']['radius_md']};\",")
    lines.append("    'alert_warning': f\"background-color: {EMAIL_STYLES['color']['warning_bg']}; border: 1px solid {EMAIL_STYLES['color']['warning_border']}; color: {EMAIL_STYLES['color']['warning_text']}; padding: {EMAIL_STYLES['spacing']['md']}; border-radius: {EMAIL_STYLES['border']['radius_md']};\",")
    lines.append("    'alert_danger': f\"background-color: {EMAIL_STYLES['color']['danger_bg']}; border: 1px solid {EMAIL_STYLES['color']['danger_border']}; color: {EMAIL_STYLES['color']['danger_text']}; padding: {EMAIL_STYLES['spacing']['md']}; border-radius: {EMAIL_STYLES['border']['radius_md']};\",")
    lines.append('}')
    lines.append('')

    return '\n'.join(lines)


def main():
    """Build design tokens into CSS and Python files."""
    print(f"Loading tokens from: {TOKENS_JSON}")

    if not TOKENS_JSON.exists():
        print(f"ERROR: Token file not found: {TOKENS_JSON}")
        return 1

    tokens = load_tokens()
    print(f"Loaded {sum(len(v) for v in tokens.values())} tokens in {len(tokens)} categories")

    # Generate CSS
    css_content = generate_css_variables(tokens)
    CSS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(CSS_OUTPUT, 'w') as f:
        f.write(css_content)
    print(f"Generated CSS: {CSS_OUTPUT}")

    # Generate Python email styles
    email_styles_content = generate_email_styles(tokens)
    EMAIL_STYLES_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(EMAIL_STYLES_OUTPUT, 'w') as f:
        f.write(email_styles_content)
    print(f"Generated email styles: {EMAIL_STYLES_OUTPUT}")

    print("\nDone! Remember to commit both generated files.")
    return 0


if __name__ == '__main__':
    exit(main())
