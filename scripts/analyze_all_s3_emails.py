"""
Comprehensive Email Analysis - ALL S3 Emails (157 emails)
==========================================================

Analyzes all emails from S3 bucket to build comprehensive exclude filters
Much better than 5 test emails!
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

def extract_urls_from_raw_email(email_path):
    """Extract all URLs from a raw email file (no .eml extension)."""
    with open(email_path, 'rb') as f:
        try:
            msg = BytesParser(policy=policy.default).parse(f)
        except:
            return [], None, None

    urls = set()
    from_field = msg.get('From', '')
    subject = msg.get('Subject', '')

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

    return cleaned, from_field, subject


def categorize_url(url):
    """Categorize URL by type."""
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
    email_mgmt_patterns = [
        '/unsubscribe', '/preferences', '/subscribe', '/subpref',
        '/manage', '/optout', '/email-pref', '/manage-subscription',
        '/email-alert-activation', '/emailnotification', '/email-activation',
        '/email-verification', '/confirm-subscription', '/verify-email',
        '/contact-ir/emailnotification', 'token='
    ]
    if any(pattern in url_lower for pattern in email_mgmt_patterns):
        return 'email_management'

    # Tracking/analytics
    tracking_patterns = ['/wf/open', '/wf/click', '/track', '/pixel', '/beacon']
    if any(pattern in path for pattern in tracking_patterns):
        return 'tracking'

    # CDN/assets
    if 'cloudfront.net' in parsed.netloc or any(p in path for p in ['/logo', '/icon', '/image', '/alerts_logos/', '/files/design/', '/files/theme/']):
        return 'cdn_assets'

    # Press release keywords
    pr_patterns = [
        '/news/', '/press-release/', '/press_release/', '/pressrelease/',
        '/investor', '/detail/', '/release/', '/releases/', '/press/',
        '/newsroom/', '/media/', '/news-release'
    ]
    if any(pattern in path for pattern in pr_patterns):
        return 'press_release'

    # IR pages (investor relations landing pages, not PRs)
    if '/investor-relations' in path and '/news' not in path:
        return 'ir_landing'

    # Calendar/events
    if any(pattern in path for pattern in ['/calendar', '/event', '/webcast', '/conference']):
        return 'events'

    # Notification/tracking domains
    if 'notification' in parsed.netloc or 'click' in parsed.netloc or 'track' in parsed.netloc:
        return 'notification_redirect'

    return 'unknown'


def main():
    """Analyze all S3 emails."""
    print("=" * 90)
    print("COMPREHENSIVE EMAIL ANALYSIS - ALL 157 S3 EMAILS")
    print("=" * 90)
    print()

    s3_emails_dir = Path('data/s3-emails')
    if not s3_emails_dir.exists():
        print(f"❌ Directory not found: {s3_emails_dir}")
        return

    # Get all email files (no .eml extension, just raw files)
    email_files = [f for f in s3_emails_dir.iterdir() if f.is_file()]
    print(f"📧 Found {len(email_files)} email files in S3 bucket")
    print()

    # Extract all URLs
    all_urls = []
    email_senders = Counter()
    email_subjects_with_activation = []
    parse_errors = 0

    for i, email_file in enumerate(email_files, 1):
        if i % 20 == 0:
            print(f"  Processing: {i}/{len(email_files)}...")

        urls, from_field, subject = extract_urls_from_raw_email(email_file)

        if urls is None:
            parse_errors += 1
            continue

        all_urls.extend(urls)

        # Track senders
        if from_field:
            email_senders[from_field] += 1

        # Flag activation/signup emails
        if subject and any(pattern in subject.lower() for pattern in ['activation', 'confirm', 'verify', 'welcome']):
            email_subjects_with_activation.append((email_file.name, subject, len(urls)))

    print()
    print(f"✅ Processed {len(email_files) - parse_errors}/{len(email_files)} emails successfully")
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
    print("=" * 90)
    print("URL CATEGORIES")
    print("=" * 90)
    for category, count in sorted(categories.items(), key=lambda x: -x[1]):
        pct = (count / len(set(all_urls))) * 100
        print(f"{category:25s}: {count:4d} URLs ({pct:5.1f}%)")
    print()

    # Show activation/signup emails
    if email_subjects_with_activation:
        print("=" * 90)
        print(f"ACTIVATION/SIGNUP EMAILS FOUND ({len(email_subjects_with_activation)} emails)")
        print("=" * 90)
        for filename, subject, url_count in email_subjects_with_activation[:10]:
            print(f"Subject: {subject[:70]}")
            print(f"  File: {filename}")
            print(f"  URLs: {url_count}")
            print()

    # Sample URLs from key categories
    key_categories = ['email_management', 'tracking', 'notification_redirect', 'events', 'cdn_assets']
    print("=" * 90)
    print("SAMPLE URLS TO EXCLUDE")
    print("=" * 90)
    print()

    for category in key_categories:
        if category in categorized_urls:
            print(f"\n{category.upper().replace('_', ' ')}:")
            print("-" * 90)
            for url in categorized_urls[category][:10]:
                print(f"  {url[:120]}")
            if len(categorized_urls[category]) > 10:
                print(f"  ... and {len(categorized_urls[category]) - 10} more")

    # Extract unique path components to find patterns
    print()
    print("=" * 90)
    print("PATH PATTERNS TO EXCLUDE (frequency >= 3)")
    print("=" * 90)
    print()

    path_segments = Counter()
    for category in ['email_management', 'tracking', 'cdn_assets', 'events']:
        if category in categorized_urls:
            for url in categorized_urls[category]:
                try:
                    parsed = urlparse(url)
                    parts = [p for p in parsed.path.lower().split('/') if p and len(p) > 2]
                    for part in parts:
                        path_segments[f'/{part}/'] += 1
                except:
                    pass

    for segment, count in path_segments.most_common(50):
        if count >= 3:
            print(f"{segment:50s}: {count:3d} occurrences")

    # Generate comprehensive EXCLUDE_PATTERNS
    print()
    print("=" * 90)
    print("RECOMMENDED COMPREHENSIVE EXCLUDE_PATTERNS")
    print("=" * 90)
    print()
    print("# Generated from analysis of 157 real emails from S3 bucket")
    print()
    print("EXCLUDE_PATTERNS = [")

    # Build pattern list from analysis
    patterns_by_category = {
        "Image/media files": ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.pdf'],
        "Email management": [
            '/unsubscribe', '/preferences', '/subscribe',
            '/subpref', '/manage', '/optout',
            '/email-pref', '/manage-subscription',
        ],
        "Email activation/verification (CRITICAL)": [
            '/email-alert-activation/',
            '/emailnotification/',
            '/email-activation/',
            '/email-verification/',
            '/email-confirm/',
            '/activate-alert',
            '/confirm-subscription',
            '/verify-email',
            'token=',
            '/contact-ir/emailnotification',
        ],
        "Tracking/analytics": [
            '/wf/open', '/wf/click', '/track', '/pixel', '/beacon',
        ],
        "CDN/assets": [
            '/logo', '/icon', '/image',
            'cloudfront.net',
            '/alerts_logos/',
            '/files/design/',
            '/files/theme/',
            '/sites/g/files/',
        ],
        "Social media": [
            'facebook.com', 'twitter.com', 'linkedin.com',
            'instagram.com', 'youtube.com',
        ],
        "Events/calendar": [
            '/calendar/', '/event/', '/webcast/', '/conference/',
        ],
    }

    for category, patterns in patterns_by_category.items():
        print(f"    # {category}")
        for pattern in patterns:
            print(f"    '{pattern}',")
        print()

    # Add discovered patterns
    print("    # High-frequency patterns from email analysis")
    added = set()
    for segment, count in path_segments.most_common(30):
        if count >= 5:
            # Skip if already in patterns or looks like PR path
            if any(segment in str(p) for category_patterns in patterns_by_category.values() for p in category_patterns):
                continue
            if any(pr in segment for pr in ['/news/', '/press/', '/release/', '/investor/', '/media/']):
                continue
            if segment not in added:
                print(f"    '{segment}',  # {count} occurrences")
                added.add(segment)

    print("]")
    print()

    # Summary statistics
    print("=" * 90)
    print("SUMMARY")
    print("=" * 90)
    print(f"Total emails analyzed: {len(email_files) - parse_errors}")
    print(f"Total URLs found: {len(all_urls)}")
    print(f"Unique URLs: {len(set(all_urls))}")
    print(f"URLs to exclude: {sum(count for cat, count in categories.items() if cat != 'press_release' and cat != 'unknown')}")
    print(f"Press release URLs: {categories.get('press_release', 0)}")
    print(f"Activation/signup emails detected: {len(email_subjects_with_activation)}")
    print()


if __name__ == '__main__':
    main()
