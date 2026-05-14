#!/usr/bin/env python3
"""
Gmail to Review Database
Fetches emails from Gmail, classifies them, and saves REVIEW emails to database
"""
import os
import sys
import email
import base64
from datetime import datetime
from playwright.sync_api import sync_playwright

# Import our filters and models
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from integrations.gmail.filters import classify_email
from core.models import get_session, init_db, ReviewEmail
from integrations.gmail.auth import authenticate_gmail, get_message_header
from config.paths import DB_PATH
from utils.file_utils import (
    ensure_screenshot_directory,
    get_screenshot_full_path,
    get_screenshot_web_path
)
from utils.review_constants import (
    MAX_EMAIL_SIZE_BYTES,
    SCREENSHOT_WIDTH,
    SCREENSHOT_HEIGHT,
    SCREENSHOT_QUALITY,
    SCREENSHOT_FORMAT,
    SCREENSHOT_RENDER_TIMEOUT_MS,
    SCAN_DEFAULT_MAX_RESULTS,
    ReviewEmailStatus,
    ReviewEmailErrors
)




def extract_html_from_email(msg_raw):
    """Extract HTML content from email message"""
    try:
        msg = email.message_from_bytes(base64.urlsafe_b64decode(msg_raw['raw']))

        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == 'text/html':
                    return part.get_payload(decode=True).decode('utf-8', errors='ignore')
        else:
            if msg.get_content_type() == 'text/html':
                return msg.get_payload(decode=True).decode('utf-8', errors='ignore')

        return None
    except Exception as e:
        print(f"   Error extracting HTML: {e}")
        return None


def capture_email_screenshot(html_content, screenshot_path, browser_context):
    """Capture low-resolution screenshot of email HTML for preview"""
    try:
        # Create a temporary HTML page
        page = browser_context.new_page()

        # Set viewport to configured screenshot dimensions
        page.set_viewport_size({
            "width": SCREENSHOT_WIDTH,
            "height": SCREENSHOT_HEIGHT
        })

        # Set HTML content (don't wait for network - fast)
        page.set_content(html_content, wait_until='domcontentloaded')

        # Scroll to top to ensure we capture from the beginning
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(SCREENSHOT_RENDER_TIMEOUT_MS)

        # Take screenshot with quality optimization
        page.screenshot(
            path=screenshot_path,
            full_page=True,
            type=SCREENSHOT_FORMAT,
            quality=SCREENSHOT_QUALITY
        )
        page.close()

        return True
    except Exception as e:
        print(f"   Error capturing screenshot: {e}")
        return False


def process_emails_to_review(service, max_results=50):
    """
    Fetch recent emails from Gmail and save REVIEW emails to database

    Args:
        service: Gmail API service
        max_results: Number of emails to process

    Returns:
        dict: Statistics
    """
    print(f"\n{'='*80}")
    print(f"GMAIL TO REVIEW DATABASE")
    print(f"{'='*80}\n")

    # Initialize database
    init_db(DB_PATH)
    db = get_session()

    # Create screenshots directory
    ensure_screenshot_directory()

    print(f"Fetching {max_results} most recent emails...")

    # Get message IDs
    results = service.users().messages().list(
        userId='me',
        labelIds=['INBOX'],
        maxResults=max_results
    ).execute()

    messages = results.get('messages', [])
    print(f"Found {len(messages)} messages\n")

    # Initialize Playwright browser for screenshots
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=True)
    # SECURITY NOTE: Images load during screenshot capture (one-time, server-side only)
    # This is safer than viewing in email client (which loads pixels every view)
    # The screenshot itself is a static JPEG - completely safe to view
    browser_context = browser.new_context()

    # Statistics
    stats = {
        'total': len(messages),
        'skip': 0,
        'process': 0,
        'review': 0,
        'review_saved': 0,
        'review_existing': 0
    }

    # Process each email
    for i, msg_ref in enumerate(messages, 1):
        # Get full message with metadata for headers
        gmail_msg_metadata = service.users().messages().get(
            userId='me',
            id=msg_ref['id'],
            format='full'
        ).execute()

        # Get full message with raw format for saving
        gmail_msg_raw = service.users().messages().get(
            userId='me',
            id=msg_ref['id'],
            format='raw'
        ).execute()

        # Extract headers
        subject = get_message_header(gmail_msg_metadata, 'subject')
        from_header = get_message_header(gmail_msg_metadata, 'from')
        date_header = get_message_header(gmail_msg_metadata, 'date')

        # Parse date
        from email.utils import parsedate_to_datetime
        try:
            email_date = parsedate_to_datetime(date_header)
        except:
            email_date = datetime.utcnow()

        # Parse sender
        from email.utils import parseaddr
        name, email_addr = parseaddr(from_header)
        domain = email_addr.split('@')[1] if '@' in email_addr else 'unknown'

        print(f"{i}. {subject[:60]}")
        print(f"   From: {from_header[:55]}")

        # Classify email
        classification = classify_email(subject, from_header)

        if classification['action'] == 'skip':
            stats['skip'] += 1
            print(f"   → SKIP (subscription)\n")

        elif classification['action'] == 'process':
            stats['process'] += 1
            print(f"   → PROCESS (press release)\n")

        elif classification['action'] == 'review':
            stats['review'] += 1
            print(f"   → REVIEW: {classification['reason']}")

            # SECURITY: Check email size to prevent DoS
            raw_email_data = base64.urlsafe_b64decode(gmail_msg_raw['raw'])
            if len(raw_email_data) > MAX_EMAIL_SIZE_BYTES:
                size_mb = len(raw_email_data) / 1024 / 1024
                print(f"   ⚠️  {ReviewEmailErrors.EMAIL_TOO_LARGE.format(size_mb=size_mb)}\n")
                continue

            # Check if already in database
            existing = db.query(ReviewEmail).filter_by(
                gmail_message_id=msg_ref['id']
            ).first()

            if existing:
                stats['review_existing'] += 1
                print(f"   Already in database (ID: {existing.id})\n")
            else:
                # Extract HTML and capture screenshot
                html_content = extract_html_from_email(gmail_msg_raw)
                screenshot_path = None

                if html_content:
                    screenshot_full_path = get_screenshot_full_path(msg_ref['id'])

                    print(f"   📸 Capturing screenshot...")
                    if capture_email_screenshot(html_content, screenshot_full_path, browser_context):
                        screenshot_path = get_screenshot_web_path(msg_ref['id'])
                        print(f"   ✅ Screenshot saved")
                    else:
                        print(f"   ⚠️  Screenshot failed (will save without preview)")

                # Save to database
                review_email = ReviewEmail(
                    gmail_message_id=msg_ref['id'],
                    subject=subject,
                    from_header=from_header,
                    from_email=email_addr,
                    from_domain=domain,
                    date=email_date,
                    raw_email=raw_email_data.decode('utf-8', errors='ignore'),
                    screenshot_path=screenshot_path,
                    classification_reason=classification['reason'],
                    status=ReviewEmailStatus.PENDING
                )

                db.add(review_email)
                db.commit()
                stats['review_saved'] += 1
                print(f"   ✅ Saved to database (ID: {review_email.id})\n")

    # Cleanup
    browser.close()
    playwright.stop()
    db.close()

    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}\n")

    print(f"Total emails processed: {stats['total']}")
    print(f"  🚫 Subscriptions (skipped): {stats['skip']}")
    print(f"  ✅ Press releases: {stats['process']}")
    print(f"  ⚠️  Flagged for review: {stats['review']}")
    print(f"\nReview Database:")
    print(f"  💾 New emails saved: {stats['review_saved']}")
    print(f"  📋 Already in database: {stats['review_existing']}")

    print(f"\n{'='*80}")
    print("NEXT STEPS")
    print(f"{'='*80}\n")
    print("1. Open the web interface: https://app.reitsheet.co/review")
    print("2. Review the flagged emails")
    print("3. Click 'Add to Press Releases' or 'Delete' for each email")

    return stats


def main():
    """Main execution"""

    # Authenticate
    print("Authenticating with Gmail API...")
    service = authenticate_gmail()
    print("✅ Authenticated!\n")

    # Process emails
    stats = process_emails_to_review(service, max_results=SCAN_DEFAULT_MAX_RESULTS)


if __name__ == '__main__':
    main()
