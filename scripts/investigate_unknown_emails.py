#!/usr/bin/env python3
"""
Investigate Unknown Emails
===========================
Check what's in the "unknown" bucket to improve categorization
"""

import boto3
import re
from email.parser import BytesParser
from email import policy
from urllib.parse import urlparse

S3_BUCKET = 'reitsheet-email-ingest'
S3_PREFIX = 'incoming/'

s3 = boto3.client('s3', region_name='us-east-1')

EXCLUDE_PATTERNS = [
    '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.pdf',
    '/unsubscribe', '/preferences', '/subscribe', '/subpref', '/manage',
    '/optout', '/email-pref', '/manage-subscription',
    '/email-alert-activation/', '/emailnotification/', '/email-activation/',
    '/email-verification/', '/email-confirm/', '/activate-alert',
    '/confirm-subscription', '/verify-email', 'token=',
    '/wf/open', '/wf/click', '/track', '/pixel', '/beacon',
    '/logo', '/icon', '/image', 'cloudfront.net', '/alerts_logos/',
    'facebook.com', 'twitter.com', 'linkedin.com',
    '/calendar/', '/event/', '/webcast/', '/conference/',
    '/open/', '/default.aspx/', '/resources/', '/investor-email-alerts/',
]

ACTIVATION_KEYWORDS = [
    'activation', 'confirm', 'verify', 'welcome', 'signup',
    'subscription', 'email alert', 'please confirm'
]

PRESS_RELEASE_PATTERNS = [
    '/news/', '/press-release/', '/press_release/', '/pressrelease/',
    '/investor', '/detail/', '/release/', '/releases/', '/press/',
    '/newsroom/', '/media/', '/news-release', '/news-details',
]

def extract_email_metadata(email_content):
    try:
        msg = BytesParser(policy=policy.default).parsebytes(email_content)
    except:
        return None

    subject = msg.get('Subject', '')
    from_field = msg.get('From', '')

    urls = set()
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() in ['text/plain', 'text/html']:
                try:
                    body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    urls.update(re.findall(r'https?://[^\s<>"]+', body))
                except:
                    pass
    else:
        try:
            body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
            urls.update(re.findall(r'https?://[^\s<>"]+', body))
        except:
            pass

    # Clean URLs
    cleaned = []
    for url in urls:
        url = url.rstrip('.,;:!?)')
        url = re.sub(r'[?&](utm_|ref=|source=).*$', '', url)
        cleaned.append(url)

    return {
        'subject': subject,
        'from': from_field,
        'urls': list(set(cleaned))
    }


def is_excluded(url):
    return any(p in url.lower() for p in EXCLUDE_PATTERNS)


def is_press_url(url):
    path = urlparse(url).path.lower()
    return any(p in path for p in PRESS_RELEASE_PATTERNS)


def categorize(metadata):
    subject = metadata['subject'].lower()
    if any(k in subject for k in ACTIVATION_KEYWORDS):
        return 'ACTIVATION'

    press_urls = [u for u in metadata['urls'] if not is_excluded(u) and is_press_url(u)]
    if press_urls:
        return 'PRESS_RELEASE'

    non_excluded = [u for u in metadata['urls'] if not is_excluded(u)]
    if not non_excluded and metadata['urls']:
        return 'ACTIVATION'

    return 'UNKNOWN'


def main():
    print("🔍 Investigating UNKNOWN emails...\n")

    response = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=S3_PREFIX)
    email_keys = [obj['Key'] for obj in response.get('Contents', []) if not obj['Key'].endswith('/')]

    unknown_emails = []

    for key in email_keys:
        try:
            obj = s3.get_object(Bucket=S3_BUCKET, Key=key)
            content = obj['Body'].read()
            metadata = extract_email_metadata(content)

            if metadata and categorize(metadata) == 'UNKNOWN':
                # Extract non-excluded URLs
                non_excluded_urls = [u for u in metadata['urls'] if not is_excluded(u)]
                unknown_emails.append({
                    'subject': metadata['subject'],
                    'from': metadata['from'],
                    'urls': non_excluded_urls,
                    'total_urls': len(metadata['urls'])
                })
        except Exception as e:
            continue

    print(f"Found {len(unknown_emails)} UNKNOWN emails\n")
    print("=" * 100)
    print("SAMPLE UNKNOWN EMAILS (first 20)")
    print("=" * 100)

    for i, email in enumerate(unknown_emails[:20], 1):
        print(f"\n{i}. Subject: {email['subject'][:80]}")
        print(f"   From: {email['from'][:80]}")
        print(f"   Total URLs: {email['total_urls']} | Non-excluded: {len(email['urls'])}")

        if email['urls']:
            print(f"   Non-excluded URLs:")
            for url in email['urls'][:3]:
                print(f"     • {url[:90]}")
            if len(email['urls']) > 3:
                print(f"     ... and {len(email['urls']) - 3} more")
        else:
            print(f"   ⚠️  All URLs were excluded")

    # Analyze URL patterns
    print("\n" + "=" * 100)
    print("URL DOMAIN ANALYSIS")
    print("=" * 100)

    domains = {}
    for email in unknown_emails:
        for url in email['urls']:
            domain = urlparse(url).netloc
            if domain not in domains:
                domains[domain] = []
            domains[domain].append(url)

    print(f"\nFound {len(domains)} unique domains in unknown emails:\n")
    for domain, urls in sorted(domains.items(), key=lambda x: -len(x[1]))[:20]:
        print(f"  {domain:50s} ({len(urls)} URLs)")
        # Show sample URL
        sample = urls[0]
        print(f"    Sample: {sample[:90]}")
        print()


if __name__ == '__main__':
    main()
