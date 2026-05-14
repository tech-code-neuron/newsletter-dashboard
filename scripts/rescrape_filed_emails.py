"""
Re-scrape press releases from already-filed Gmail emails

Use this to scrape emails that were filed but not ingested due to database issues.
"""
import sys
import os
from datetime import datetime
import email
import base64

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from integrations.gmail.auth import authenticate_gmail, get_message_header
from integrations.email_parsers.pr_email_parser_v2 import extract_pr_url_from_email, decode_email_subject
from core.models import get_session, Company, PressRelease
from core.scraper import PressReleaseScraper
from core.categorizer import PressReleaseCategorizer
from playwright.sync_api import sync_playwright
from urllib.parse import urlparse


def find_company_from_url(db, pr_url):
    """Find company by matching PR URL domain"""
    url_domain = urlparse(pr_url).netloc.lower()

    companies = db.query(Company).filter(Company.active == True).all()

    for company in companies:
        if company.ir_url:
            company_domain = urlparse(company.ir_url).netloc.lower()
            if company_domain in url_domain or url_domain in company_domain:
                return company

        if company.press_release_url:
            pr_domain = urlparse(company.press_release_url).netloc.lower()
            if pr_domain in url_domain or url_domain in pr_domain:
                return company

    return None


def main():
    print("Re-scraping filed press release emails...")
    print("="*80)

    # Authenticate
    service = authenticate_gmail()
    db = get_session()
    scraper = PressReleaseScraper()
    categorizer = PressReleaseCategorizer()

    # Get emails from 2026/03-Mar label
    results = service.users().messages().list(
        userId='me',
        q='label:"2026/03-Mar"',
        maxResults=10
    ).execute()

    messages = results.get('messages', [])
    print(f"Found {len(messages)} emails in 2026/03-Mar label\n")

    scraped_count = 0
    skipped_count = 0
    error_count = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()

        for i, msg_ref in enumerate(messages, 1):
            try:
                # Get email
                gmail_msg = service.users().messages().get(
                    userId='me',
                    id=msg_ref['id'],
                    format='raw'
                ).execute()

                gmail_msg_metadata = service.users().messages().get(
                    userId='me',
                    id=msg_ref['id'],
                    format='metadata'
                ).execute()

                subject = get_message_header(gmail_msg_metadata, 'subject')
                from_header = get_message_header(gmail_msg_metadata, 'from')

                from email.utils import parsedate_to_datetime
                date_header = get_message_header(gmail_msg_metadata, 'date')
                email_date = parsedate_to_datetime(date_header)

                print(f"[{i}/{len(messages)}] {subject[:60]}")

                # Extract PR URL
                msg_str = base64.urlsafe_b64decode(gmail_msg['raw'].encode('ASCII'))
                email_obj = email.message_from_bytes(msg_str)

                pr_result = extract_pr_url_from_email(email_obj, context, subject)

                if not pr_result or not pr_result.pr_url:
                    print("  ❌ Could not extract PR URL")
                    error_count += 1
                    continue

                # Check if already exists
                existing = db.query(PressRelease).filter_by(url=pr_result.pr_url).first()
                if existing:
                    print(f"  ⏭️  Already in database: {existing.company.ticker}")
                    skipped_count += 1
                    continue

                # Find company
                company = find_company_from_url(db, pr_result.pr_url)

                if not company:
                    print(f"  ⚠️  Could not identify company for: {pr_result.pr_url}")
                    error_count += 1
                    continue

                print(f"  🔍 Scraping: {company.ticker}")

                # Fetch content
                full_text = scraper.fetch_press_release_content(pr_result.pr_url)

                if full_text:
                    # Create press release
                    press_release = PressRelease(
                        company_id=company.id,
                        title=subject,
                        url=pr_result.pr_url,
                        published_date=email_date,
                        content="",  # Summary - can add later
                        full_text=full_text[:4000] if full_text else "",  # First 4000 chars
                        scraped_date=datetime.utcnow()
                    )

                    # Generate slug and unique ID
                    press_release.slug = press_release.generate_slug()
                    press_release.unique_id = press_release.generate_unique_id(db)

                    # Categorize
                    category_result = categorizer.categorize_press_release(press_release)
                    press_release.category = category_result['category']
                    press_release.is_breaking = category_result.get('is_breaking', False)

                    # Save
                    db.add(press_release)
                    db.commit()

                    print(f"  ✅ Scraped & saved: {press_release.category}")
                    scraped_count += 1
                else:
                    print(f"  ❌ Scraping failed - no content")
                    error_count += 1

            except Exception as e:
                print(f"  ❌ Error: {e}")
                error_count += 1
                continue

        browser.close()

    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    print(f"Total emails: {len(messages)}")
    print(f"  ✅ Scraped & saved: {scraped_count}")
    print(f"  ⏭️  Already existed: {skipped_count}")
    print(f"  ❌ Errors: {error_count}")

    scraper.close()
    db.close()


if __name__ == '__main__':
    main()
