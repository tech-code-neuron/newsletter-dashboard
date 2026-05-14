#!/usr/bin/env python3
"""
Backfill archive pages with missing components.

Injects into existing S3 archive HTML:
- Popup CSS (in head)
- Navigation bar with signup popup
- Signup section (before footer)
- Updated footer with Privacy/Contact links

Usage:
    python3 scripts/backfill_archive_components.py
    python3 scripts/backfill_archive_components.py --dry-run  # Preview without uploading
"""

import argparse
import json
import re
import time
from pathlib import Path

import boto3


def load_site_config():
    """Load site configuration."""
    config_path = Path('infrastructure/docker/flask-app/config/site_config.json')
    with open(config_path) as f:
        return json.load(f)


def get_popup_css(config):
    """Generate popup CSS."""
    colors = config['colors']
    # Use simple font stack to avoid quote issues
    body_font = "Georgia, serif"

    return f'''    <style>
    /* Signup popup - click/tap to toggle (works on mobile) */
    .signup-wrapper {{ position: relative; display: inline-block; }}
    .signup-toggle {{ display: none; }}
    .signup-trigger {{ color: {colors['primary']}; cursor: pointer; border-bottom: 1px dashed {colors['primary']}; }}
    .signup-popup {{
        position: absolute; top: 100%; left: 50%; transform: translateX(-50%);
        margin-top: 10px; background: #fff; border: 1px solid {colors['border']};
        border-radius: 6px; box-shadow: 0 4px 16px rgba(0,0,0,0.15);
        padding: 16px 20px; width: 280px; display: none; z-index: 100;
    }}
    .signup-popup::before {{
        content: ''; position: absolute; top: -8px; left: 50%; transform: translateX(-50%);
        border-left: 8px solid transparent; border-right: 8px solid transparent;
        border-bottom: 8px solid {colors['border']};
    }}
    .signup-popup::after {{
        content: ''; position: absolute; top: -7px; left: 50%; transform: translateX(-50%);
        border-left: 7px solid transparent; border-right: 7px solid transparent;
        border-bottom: 7px solid #fff;
    }}
    .signup-toggle:checked ~ .signup-popup {{ display: block; }}
    .signup-close-btn {{ position: absolute; top: 6px; right: 8px; font-size: 20px; color: {colors['text_muted']}; cursor: pointer; line-height: 1; }}
    .signup-close-btn:hover {{ color: {colors['text']}; }}
    .popup-form input[type="email"] {{
        width: 100%; padding: 10px 12px; font-size: 14px;
        font-family: {body_font}; border: 1px solid {colors['border']};
        box-sizing: border-box; margin-bottom: 8px; border-radius: 4px;
    }}
    .popup-form button {{
        width: 100%; padding: 10px 16px; background: {colors['primary']};
        color: white; border: none; font-size: 14px;
        font-family: {body_font}; cursor: pointer; border-radius: 4px;
    }}
    .popup-form button:hover {{ background: {colors['primary_hover']}; }}
    </style>
'''


def get_navigation_html(config):
    """Generate navigation bar with popup signup."""
    colors = config['colors']
    signup = config['signup']
    site = config['site']
    # Use simple font stacks to avoid quote issues
    body_font = "Georgia, serif"
    ui_font = "Arial, Helvetica, sans-serif"

    return f'''        <div style="text-align: center; padding: 12px 0; font-family: {ui_font}; font-size: 13px;">
            <span class="signup-wrapper">
                <input type="checkbox" id="nav-signup-toggle" class="signup-toggle">
                <label for="nav-signup-toggle" class="signup-trigger">Get This Brief Before the Open</label>
                <div class="signup-popup">
                    <label for="nav-signup-toggle" class="signup-close-btn">&times;</label>
                    <div style="font-family: {body_font}; font-size: 14px; color: {colors['text']}; margin-bottom: 12px; padding-right: 16px;">Subscribe to {site['name']}</div>
                    <form action="{signup['api_url']}" method="POST" class="popup-form">
                        <input type="email" name="email" placeholder="you@example.com" required>
                        <button type="submit">Subscribe</button>
                    </form>
                    <div style="margin-top: 10px; font-family: {body_font}; font-size: 11px; color: {colors['text_secondary']}; text-align: center;">
                        {signup['footer']}
                    </div>
                </div>
            </span>
        </div>
'''


def get_signup_section(config):
    """Generate signup box section."""
    colors = config['colors']
    signup = config['signup']
    # Use simple font stack to avoid quote issues in inline styles
    body_font = "Georgia, serif"

    return f'''
        <!-- Signup Section -->
        <div id="signup" style="border: 1px solid {colors['border']}; border-radius: 6px; margin-top: 32px; padding: 20px 24px; text-align: center; background: {colors['card_bg']};">
            <div style="font-family: {body_font}; font-size: 17px; color: {colors['text']}; margin-bottom: 6px;">
                {signup['headline']}
            </div>
            <div style="font-family: {body_font}; font-size: 13px; color: {colors['text_secondary']}; margin-bottom: 16px; line-height: 1.5;">
                {signup['description']}
            </div>
            <form action="{signup['api_url']}" method="POST" style="display: flex; gap: 8px; justify-content: center; flex-wrap: wrap; max-width: 400px; margin: 0 auto;">
                <input type="email" name="email" placeholder="you@example.com" required
                    style="flex: 1; min-width: 200px; padding: 10px 14px; font-size: 14px; font-family: {body_font}; border: 1px solid {colors['border']}; border-radius: 4px;">
                <button type="submit"
                    style="padding: 10px 20px; background: {colors['primary']}; color: white; border: none; font-size: 14px; font-family: {body_font}; cursor: pointer; border-radius: 4px;">
                    Subscribe
                </button>
            </form>
            <div style="font-family: {body_font}; font-size: 11px; color: {colors['text_muted']}; margin-top: 12px;">
                {signup['footer']}
            </div>
        </div>
'''


def get_footer_html(config):
    """Generate footer with Privacy/Contact links."""
    colors = config['colors']
    footer = config['footer']
    # Use simple font stacks to avoid quote issues
    body_font = "Georgia, serif"
    ui_font = "Arial, Helvetica, sans-serif"

    return f'''        <div style="text-align: center; padding: 24px 0; margin-top: 16px;">
            <div style="font-family: {body_font}; font-size: 14px; font-style: italic; color: {colors['text_secondary']};">{footer['tagline']}</div>
            <div style="margin-top: 12px; font-family: {ui_font}; font-size: 12px;">
                <a href="{footer['privacy_url']}" style="color: {colors['text_muted']}; text-decoration: none;">Privacy Policy</a>
                <span style="color: #ccc; margin: 0 8px;">|</span>
                <a href="mailto:{footer['contact_email']}" style="color: {colors['text_muted']}; text-decoration: none;">Contact Us</a>
            </div>
        </div>
    </div>
</body>
</html>'''


def inject_components(html, config):
    """Inject all components into existing HTML."""

    # 1. Remove old popup CSS if present (may have broken fonts)
    if '<style>' in html and '.signup-wrapper' in html:
        # Find and remove old style block
        style_start = html.find('    <style>')
        style_end = html.find('</style>', style_start) + len('</style>')
        if style_start != -1 and style_end != -1:
            html = html[:style_start] + html[style_end:]

    # 2. Remove old signup section if present
    if '<div id="signup"' in html or '<!-- Signup Section -->' in html:
        signup_start = html.find('<!-- Signup Section -->')
        if signup_start == -1:
            # Try finding the div directly
            signup_start = html.find('<div id="signup"')
            # Go back to find newline/whitespace before it
            while signup_start > 0 and html[signup_start-1] in ' \t\n':
                signup_start -= 1

        if signup_start != -1:
            footer_marker = html.find('<!-- Footer -->', signup_start)
            if footer_marker != -1:
                html = html[:signup_start] + html[footer_marker:]

    # 3. Inject fresh popup CSS before </head>
    popup_css = get_popup_css(config)
    html = html.replace('</head>', f'{popup_css}</head>')

    # 2. Inject navigation after <!-- Navigation -->
    # 4. Replace navigation section (handles both empty and existing content)
    nav_html = get_navigation_html(config)
    nav_replace_pattern = r'<!-- Navigation -->.*?(?=<!-- Content -->)'
    html = re.sub(nav_replace_pattern, f'<!-- Navigation -->\n{nav_html}\n        ', html, flags=re.DOTALL)

    # 5. Find footer and replace everything from <!-- Footer --> to end
    footer_marker = '<!-- Footer -->'
    footer_pos = html.find(footer_marker)

    if footer_pos == -1:
        print("  Warning: No footer marker found")
        return html

    # Get signup section and new footer
    signup = get_signup_section(config)
    new_footer = get_footer_html(config)

    # Find the closing </div> before footer (end of content)
    # We need to insert signup BEFORE the footer
    html = html[:footer_pos] + signup + '\n\n        ' + footer_marker + '\n' + new_footer

    return html


def main():
    parser = argparse.ArgumentParser(description='Backfill archive pages with components')
    parser.add_argument('--dry-run', action='store_true', help='Preview without uploading')
    args = parser.parse_args()

    s3 = boto3.client('s3')
    config = load_site_config()
    bucket = 'reitsheet-homepage'

    print("Backfilling archive pages with components...")
    print(f"  Dry run: {args.dry_run}")
    print()

    # List all archives
    response = s3.list_objects_v2(Bucket=bucket, Prefix='news/archive/')

    updated_count = 0
    skipped_count = 0

    for obj in response.get('Contents', []):
        key = obj['Key']
        if not key.endswith('index.html'):
            continue

        # Extract date from path
        parts = key.split('/')
        if len(parts) < 3:
            continue
        archive_date = parts[2]  # news/archive/2026-03-26/index.html

        print(f"Processing {archive_date}...")

        # Download
        response = s3.get_object(Bucket=bucket, Key=key)
        html = response['Body'].read().decode('utf-8')

        # Inject components
        updated_html = inject_components(html, config)

        if updated_html is None:
            print(f"  Skipped (already has components)")
            skipped_count += 1
            continue

        if args.dry_run:
            print(f"  Would update (dry run)")
            # Show first 500 chars of changes for verification
            if '<!-- Navigation -->' in updated_html:
                nav_start = updated_html.find('<!-- Navigation -->')
                print(f"  Nav preview: {updated_html[nav_start:nav_start+200]}...")
        else:
            # Upload
            s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=updated_html,
                ContentType='text/html'
            )
            print(f"  Updated")

        updated_count += 1

    print()
    print(f"Summary: {updated_count} updated, {skipped_count} skipped")

    if not args.dry_run and updated_count > 0:
        # Invalidate CloudFront
        print()
        print("Creating CloudFront invalidation...")
        cloudfront = boto3.client('cloudfront')
        cloudfront.create_invalidation(
            DistributionId='E1OJKTRGT9KX3A',
            InvalidationBatch={
                'Paths': {'Quantity': 1, 'Items': ['/news/archive/*']},
                'CallerReference': str(int(time.time()))
            }
        )
        print("CloudFront invalidation created for /news/archive/*")


if __name__ == '__main__':
    main()
