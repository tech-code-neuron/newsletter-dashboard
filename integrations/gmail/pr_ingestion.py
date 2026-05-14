#!/usr/bin/env python3
"""
Gmail Press Release Ingestion
Full workflow: Gmail → Filter → Extract URLs → Display results
"""
import os
import sys
import email
from io import BytesIO
import base64

# Import our filters and parser
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from integrations.gmail.filters import classify_email
from integrations.email_parsers.pr_email_parser_v2 import extract_pr_url_from_email, decode_email_subject
from playwright.sync_api import sync_playwright
from integrations.gmail.auth import authenticate_gmail, get_message_header

# Constants
DEFAULT_MAX_RESULTS = 20

def gmail_message_to_email_object(gmail_msg):
    """
    Convert Gmail API message to Python email.message object

    Args:
        gmail_msg: Gmail API message (with format='raw')

    Returns:
        email.message.EmailMessage object
    """
    msg_str = base64.urlsafe_b64decode(gmail_msg['raw'].encode('ASCII'))
    return email.message_from_bytes(msg_str)

def process_emails(service, max_results=DEFAULT_MAX_RESULTS):
    """
    Process recent emails from Gmail inbox

    Args:
        service: Gmail API service
        max_results: Number of emails to process

    Returns:
        dict: Statistics and results
    """
    print(f"\n{'='*80}")
    print(f"GMAIL PRESS RELEASE INGESTION TEST")
    print(f"{'='*80}\n")

    print(f"Fetching {max_results} most recent emails...")

    # Get message IDs
    results = service.users().messages().list(
        userId='me',
        labelIds=['INBOX'],
        maxResults=max_results
    ).execute()

    messages = results.get('messages', [])
    print(f"Found {len(messages)} messages\n")

    # Statistics
    stats = {
        'total': len(messages),
        'subscription': 0,
        'press_release': 0,
        'review': 0,
        'extracted_urls': 0,
        'failed_extraction': 0
    }

    subscription_emails = []
    press_release_emails = []
    review_emails = []

    # Create Playwright browser for URL extraction
    print("Initializing browser for URL extraction...\n")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        )

        # Process each email
        for i, msg_ref in enumerate(messages, 1):
            # Get full message with raw format
            gmail_msg = service.users().messages().get(
                userId='me',
                id=msg_ref['id'],
                format='raw'
            ).execute()

            # Get full message with metadata for headers
            gmail_msg_metadata = service.users().messages().get(
                userId='me',
                id=msg_ref['id'],
                format='full'
            ).execute()

            # Extract headers
            subject = get_message_header(gmail_msg_metadata, 'subject')
            from_header = get_message_header(gmail_msg_metadata, 'from')

            print(f"{i}. {subject[:70]}")
            print(f"   From: {from_header[:60]}")

            # Classify email using our filters
            classification = classify_email(subject, from_header)

            print(f"   Classification: {classification['action'].upper()} ({classification['confidence']} confidence)")
            print(f"   Reason: {classification['reason']}")

            if classification['action'] == 'skip':
                stats['subscription'] += 1
                subscription_emails.append({
                    'subject': subject,
                    'from': from_header,
                    'reason': classification['reason']
                })
                print(f"   → Skipping (subscription email)")

            elif classification['action'] == 'review':
                stats['review'] += 1
                review_emails.append({
                    'subject': subject,
                    'from': from_header,
                    'reason': classification['reason']
                })
                print(f"   → Flagged for review")

            elif classification['action'] == 'process':
                stats['press_release'] += 1

                # Convert to email object and extract PR URL
                email_obj = gmail_message_to_email_object(gmail_msg)
                decoded_subject = decode_email_subject(subject)

                print(f"   → Extracting PR URL...")
                pr_result = extract_pr_url_from_email(email_obj, context, decoded_subject)

                if pr_result:
                    stats['extracted_urls'] += 1
                    press_release_emails.append({
                        'subject': subject,
                        'from': from_header,
                        'pr_url': pr_result.pr_url,
                        'extraction_method': pr_result.extraction_method
                    })
                    print(f"   ✅ {pr_result.pr_url[:60]}...")
                    print(f"      Method: {pr_result.extraction_method}")
                else:
                    stats['failed_extraction'] += 1
                    press_release_emails.append({
                        'subject': subject,
                        'from': from_header,
                        'pr_url': None,
                        'extraction_method': None
                    })
                    print(f"   ❌ Failed to extract URL")

            print()

        browser.close()

    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}\n")

    print(f"Total emails processed: {stats['total']}")
    print(f"  ✅ Press releases: {stats['press_release']}")
    print(f"  🚫 Subscriptions (skipped): {stats['subscription']}")
    print(f"  ⚠️  Flagged for review: {stats['review']}")
    print(f"\nURL Extraction:")
    print(f"  ✅ Successfully extracted: {stats['extracted_urls']}/{stats['press_release']}")
    print(f"  ❌ Failed: {stats['failed_extraction']}/{stats['press_release']}")

    # Details
    if press_release_emails:
        print(f"\n{'─'*80}")
        print(f"PRESS RELEASES FOUND ({len(press_release_emails)})")
        print(f"{'─'*80}\n")
        for pr in press_release_emails:
            print(f"• {pr['subject'][:65]}")
            print(f"  From: {pr['from'][:55]}")
            if pr['pr_url']:
                print(f"  URL: {pr['pr_url']}")
                print(f"  Method: {pr['extraction_method']}")
            else:
                print(f"  ❌ URL extraction failed")
            print()

    if review_emails:
        print(f"\n{'─'*80}")
        print(f"FLAGGED FOR REVIEW ({len(review_emails)})")
        print(f"{'─'*80}\n")
        for rev in review_emails:
            print(f"• {rev['subject'][:65]}")
            print(f"  From: {rev['from'][:55]}")
            print(f"  Reason: {rev['reason']}")
            print()

    return stats

def main():
    """Main execution"""

    # Authenticate
    print("Authenticating with Gmail API...")
    service = authenticate_gmail()
    print("✅ Authenticated!\n")

    # Process emails
    stats = process_emails(service, max_results=DEFAULT_MAX_RESULTS)

    print(f"\n{'='*80}")
    print("NEXT STEPS")
    print(f"{'='*80}\n")
    print("1. Review the extracted PR URLs above")
    print("2. Verify subscription emails were correctly filtered")
    print("3. Check any emails flagged for review")
    print("4. Ready to integrate with database for automatic ingestion")

if __name__ == '__main__':
    main()
