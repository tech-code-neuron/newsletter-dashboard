"""
Analyze Email URLs to Build Comprehensive Exclude Filters
==========================================================

Analyzes all EML files in data/test-emails/ to extract URL patterns
and identify non-press-release URLs (signup, unsubscribe, social, etc.)

Outputs:
- All unique URL patterns found
- Recommended EXCLUDE_PATTERNS for parser Lambda
"""

import re
import email
from pathlib import Path
from email import policy
from email.parser import BytesParser
from collections import Counter
from urllib.parse import urlparse

# URL extraction regex
URL_PATTERN = re.compile(r'https?://[^\s<>"]+')

def extract_urls_from_eml(eml_path):
    """Extract all URLs from an EML file."""
    with open(eml_path, 'rb') as f:
        msg = BytesParser(policy=policy.default).parse(f)

    urls = set()

    # Extract from body
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type in ['text/plain', 'text/html']:
                try:
                    body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    urls.update(URL_PATTERN.findall(body))
                except:
                    pass
    else:
        try:
            body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
            urls.update(URL_PATTERN.findall(body))
        except:
            pass

    # Clean URLs
    cleaned = []
    for url in urls:
        url = url.rstrip('.,;:!?)')
        url = re.sub(r'[?&](utm_|ref=|source=).*$', '', url)
        cleaned.append(url)

    return cleaned


def categorize_url(url):
    """
    Categorize URL by type.
    Returns: category string
    """
    url_lower = url.lower()
    parsed = urlparse(url)
    path = parsed.path.lower()

    # Image/media files
    if any(ext in url_lower for ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.pdf']):
        return 'image_media'

    # Social media
    if any(domain in parsed.netloc for domain in ['facebook.com', 'twitter.com', 'linkedin.com', 'instagram.com', 'youtube.com']):
        return 'social_media'

    # Email management
    if any(pattern in url_lower for pattern in [
        '/unsubscribe', '/preferences', '/subscribe', '/subpref',
        '/manage', '/optout', '/email-pref', '/manage-subscription',
        '/email-alert-activation', '/emailnotification', '/email-activation',
        '/email-verification', '/confirm-subscription', '/verify-email',
        '/contact-ir/emailnotification', 'token='
    ]):
        return 'email_management'

    # CDN/assets
    if 'cloudfront.net' in parsed.netloc or '/logo' in path or '/icon' in path:
        return 'cdn_assets'

    # Press release keywords
    if any(pattern in path for pattern in [
        '/news/', '/press-release/', '/press_release/', '/pressrelease/',
        '/investor', '/detail/', '/release/', '/releases/', '/press/',
        '/newsroom/', '/media/'
    ]):
        return 'press_release'

    # IR pages (investor relations landing pages, not PRs)
    if '/investor-relations' in path and '/news' not in path:
        return 'ir_landing'

    # Calendar/events
    if any(pattern in path for pattern in ['/calendar', '/event', '/webcast', '/conference']):
        return 'events'

    return 'unknown'


def extract_path_patterns(urls):
    """Extract common path patterns from URLs."""
    patterns = Counter()

    for url in urls:
        try:
            parsed = urlparse(url)
            path = parsed.path.lower()

            # Extract directory patterns (e.g., /news/, /investor/)
            parts = [p for p in path.split('/') if p]
            for i, part in enumerate(parts):
                # Capture directory patterns
                if i < len(parts) - 1:  # Not the last part (filename)
                    patterns[f'/{part}/'] += 1

        except:
            pass

    return patterns


def main():
    """Main analysis function."""
    print("=" * 80)
    print("Email URL Analysis - Building Comprehensive Exclude Filters")
    print("=" * 80)
    print()

    # Find all EML files
    test_emails_dir = Path('data/test-emails')
    if not test_emails_dir.exists():
        print(f"❌ Directory not found: {test_emails_dir}")
        return

    eml_files = list(test_emails_dir.glob('*.eml'))
    print(f"📧 Found {len(eml_files)} EML files")
    print()

    # Extract all URLs
    all_urls = []
    for eml_file in eml_files:
        print(f"Processing: {eml_file.name}")
        urls = extract_urls_from_eml(eml_file)
        all_urls.extend(urls)
        print(f"  Found {len(urls)} URLs")

    print()
    print(f"📊 Total URLs extracted: {len(all_urls)}")
    print(f"📊 Unique URLs: {len(set(all_urls))}")
    print()

    # Categorize URLs
    categories = Counter()
    categorized_urls = {}

    for url in set(all_urls):
        category = categorize_url(url)
        categories[category] += 1
        if category not in categorized_urls:
            categorized_urls[category] = []
        categorized_urls[category].append(url)

    # Print category breakdown
    print("=" * 80)
    print("URL Categories")
    print("=" * 80)
    for category, count in sorted(categories.items(), key=lambda x: -x[1]):
        print(f"{category:20s}: {count:3d} URLs")
    print()

    # Show samples from each category
    print("=" * 80)
    print("Sample URLs by Category")
    print("=" * 80)
    print()

    for category in sorted(categorized_urls.keys()):
        print(f"\n{category.upper()}:")
        print("-" * 80)
        for url in categorized_urls[category][:5]:  # Show first 5
            print(f"  {url[:100]}")
        if len(categorized_urls[category]) > 5:
            print(f"  ... and {len(categorized_urls[category]) - 5} more")

    # Extract path patterns
    print()
    print("=" * 80)
    print("Common Path Patterns (excluding press releases)")
    print("=" * 80)
    print()

    non_pr_urls = []
    for category, urls in categorized_urls.items():
        if category not in ['press_release', 'unknown']:
            non_pr_urls.extend(urls)

    patterns = extract_path_patterns(non_pr_urls)
    for pattern, count in patterns.most_common(30):
        print(f"{pattern:40s}: {count:3d} occurrences")

    # Generate recommended EXCLUDE_PATTERNS
    print()
    print("=" * 80)
    print("RECOMMENDED EXCLUDE_PATTERNS for parser Lambda")
    print("=" * 80)
    print()

    print("EXCLUDE_PATTERNS = [")
    print("    # Image/media files")
    print("    '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.pdf',")
    print()
    print("    # Email management")
    print("    '/unsubscribe', '/preferences', '/subscribe',")
    print("    '/subpref', '/manage', '/optout',")
    print("    '/email-pref', '/manage-subscription',")
    print()
    print("    # Email activation/verification (CRITICAL)")
    print("    '/email-alert-activation/',")
    print("    '/emailnotification/',")
    print("    '/email-activation/',")
    print("    '/email-verification/',")
    print("    '/email-confirm/',")
    print("    '/activate-alert',")
    print("    '/confirm-subscription',")
    print("    '/verify-email',")
    print("    'token=',  # Email verification tokens")
    print("    '/contact-ir/emailnotification',")
    print()
    print("    # CDN/assets")
    print("    '/logo', '/icon', '/image',")
    print("    'cloudfront.net',")
    print()
    print("    # Social media")
    print("    'facebook.com', 'twitter.com', 'linkedin.com',")
    print("    'instagram.com', 'youtube.com',")
    print()
    print("    # Events/calendar (not press releases)")
    print("    '/calendar/', '/event/', '/webcast/', '/conference/',")
    print()

    # Add discovered patterns
    exclude_worthy = []
    for pattern, count in patterns.most_common(50):
        if count >= 2 and pattern not in ['/news/', '/press/', '/investor/', '/releases/', '/media/']:
            exclude_worthy.append(pattern)

    if exclude_worthy:
        print("    # Additional patterns from email analysis")
        for pattern in exclude_worthy[:15]:  # Top 15
            print(f"    '{pattern}',")

    print("]")
    print()


if __name__ == '__main__':
    main()
