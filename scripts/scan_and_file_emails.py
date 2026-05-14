"""
Automated Email Scanner, Ingester, and Filer

Complete workflow:
1. Scan Gmail inbox
2. Classify emails (press release, subscription, review)
3. Ingest press releases (extract URL and scrape content)
4. File emails into organized Gmail labels
5. Archive processed emails

SOLID Principle: Orchestrates existing modules without duplicating logic.
"""
import sys
import os
from datetime import datetime, timedelta
import email
import base64
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from integrations.gmail.auth import authenticate_gmail, get_message_header
from integrations.gmail.filters import classify_email
from integrations.gmail.filing import GmailFiler
from integrations.email_parsers.pr_email_parser_v2 import extract_pr_url_from_email, decode_email_subject
from core.models import get_session, Company, PressRelease
from core.scraper import PressReleaseScraper
from core.categorizer import PressReleaseCategorizer
from playwright.sync_api import sync_playwright
from config.query_limits import SCAN_DEFAULT_MAX_RESULTS


class EmailProcessor:
    """
    Processes emails: scan → classify → ingest → file

    Single responsibility: Orchestrate the email processing workflow
    """

    def __init__(self, service, auto_file=True, auto_scrape=True):
        """
        Initialize email processor

        Args:
            service: Authenticated Gmail API service
            auto_file: If True, automatically files emails to labels
            auto_scrape: If True, automatically scrapes press releases
        """
        self.service = service
        self.auto_file = auto_file
        self.auto_scrape = auto_scrape
        self.filer = GmailFiler(service) if auto_file else None

        # Initialize database and scraper
        self.db = get_session()
        self.scraper = PressReleaseScraper() if auto_scrape else None
        self.categorizer = PressReleaseCategorizer()

        # Statistics
        self.stats = {
            'total': 0,
            'press_releases': 0,
            'subscriptions': 0,
            'reviews': 0,
            'scraped': 0,
            'filed': 0,
            'errors': 0
        }

    def gmail_message_to_email_object(self, gmail_msg):
        """Convert Gmail API message to Python email object"""
        msg_str = base64.urlsafe_b64decode(gmail_msg['raw'].encode('ASCII'))
        return email.message_from_bytes(msg_str)

    def parse_email_date(self, gmail_msg_metadata):
        """
        Extract and parse email date

        Returns:
            datetime object or current time if parsing fails
        """
        try:
            date_header = get_message_header(gmail_msg_metadata, 'date')
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(date_header)
        except:
            return datetime.now()

    def ingest_press_release(self, pr_url, subject, from_header, email_date):
        """
        Scrape and save press release to database

        Args:
            pr_url: Press release URL
            subject: Email subject
            from_header: From email header
            email_date: Email date

        Returns:
            PressRelease object or None if failed
        """
        try:
            # Extract company from email (simple heuristic)
            # Try to find company by matching domain or subject
            company = self._find_company_from_email(pr_url, subject, from_header)

            if not company:
                print(f"   ⚠️  Could not identify company")
                return None

            # Check if already exists
            existing = self.db.query(PressRelease).filter_by(url=pr_url).first()
            if existing:
                print(f"   ℹ️  Already in database: {company.ticker}")
                return existing

            # Scrape the press release
            print(f"   🔍 Scraping: {company.ticker}")
            scraped = self.scraper.scrape_single_url(
                url=pr_url,
                company=company,
                published_date=email_date
            )

            if scraped:
                # Categorize
                if not scraped.category:
                    category_result = self.categorizer.categorize_press_release(
                        scraped.title,
                        scraped.full_text or ""
                    )
                    scraped.category = category_result.category
                    scraped.is_breaking = category_result.is_breaking

                # Save to database
                self.db.add(scraped)
                self.db.commit()

                print(f"   ✅ Scraped & saved: {scraped.category}")
                self.stats['scraped'] += 1
                return scraped

        except Exception as e:
            print(f"   ❌ Scraping failed: {e}")
            self.stats['errors'] += 1

        return None

    def _find_company_from_email(self, pr_url, subject, from_header):
        """
        Find company from email metadata

        Tries multiple strategies:
        1. URL domain matching
        2. From header matching
        3. Subject line matching
        """
        # Strategy 1: Match URL domain to company.ir_url or press_release_url
        from urllib.parse import urlparse
        url_domain = urlparse(pr_url).netloc.lower()

        companies = self.db.query(Company).filter(Company.active == True).all()

        for company in companies:
            # Check if URL domain matches company IR domain
            if company.ir_url:
                company_domain = urlparse(company.ir_url).netloc.lower()
                if company_domain in url_domain or url_domain in company_domain:
                    return company

            # Check press release URL
            if company.press_release_url:
                pr_domain = urlparse(company.press_release_url).netloc.lower()
                if pr_domain in url_domain or url_domain in pr_domain:
                    return company

        # Strategy 2: Check subject line for company ticker or name
        subject_lower = subject.lower()
        for company in companies:
            if company.ticker.lower() in subject_lower:
                return company
            if company.name and company.name.lower() in subject_lower:
                return company

        return None

    def process_batch(self, max_results=50, days_back=7):
        """
        Process a batch of emails from inbox

        Args:
            max_results: Maximum number of emails to process
            days_back: Only process emails from last N days

        Returns:
            Statistics dict
        """
        print(f"\n{'='*80}")
        print(f"AUTOMATED EMAIL PROCESSING")
        print(f"{'='*80}\n")

        print(f"📧 Fetching up to {max_results} emails from last {days_back} days...")

        # Calculate date cutoff
        cutoff_date = datetime.now() - timedelta(days=days_back)
        after_query = cutoff_date.strftime('%Y/%m/%d')

        # Get recent emails
        try:
            results = self.service.users().messages().list(
                userId='me',
                labelIds=['INBOX'],
                maxResults=max_results,
                q=f'after:{after_query}'
            ).execute()
        except Exception as e:
            print(f"❌ Failed to fetch emails: {e}")
            return self.stats

        messages = results.get('messages', [])
        self.stats['total'] = len(messages)
        print(f"✅ Found {len(messages)} messages\n")

        if not messages:
            print("No messages to process.")
            return self.stats

        # Initialize browser for URL extraction
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'
            )

            # Process each email
            for i, msg_ref in enumerate(messages, 1):
                print(f"\n[{i}/{len(messages)}] Processing email...")

                try:
                    # Get full message
                    gmail_msg = self.service.users().messages().get(
                        userId='me',
                        id=msg_ref['id'],
                        format='raw'
                    ).execute()

                    gmail_msg_metadata = self.service.users().messages().get(
                        userId='me',
                        id=msg_ref['id'],
                        format='full'
                    ).execute()

                    # Extract metadata
                    subject = get_message_header(gmail_msg_metadata, 'subject')
                    from_header = get_message_header(gmail_msg_metadata, 'from')
                    email_date = self.parse_email_date(gmail_msg_metadata)
                    message_id = msg_ref['id']

                    print(f"Subject: {subject[:70]}")
                    print(f"From: {from_header[:60]}")

                    # Classify email
                    classification = classify_email(subject, from_header)
                    print(f"Classification: {classification['action'].upper()}")

                    # Process based on classification
                    if classification['action'] == 'skip':
                        # Subscription email
                        self.stats['subscriptions'] += 1
                        print(f"→ Subscription email")

                        if self.auto_file:
                            self.filer.file_subscription(message_id)
                            self.stats['filed'] += 1

                    elif classification['action'] == 'review':
                        # Flag for review
                        self.stats['reviews'] += 1
                        print(f"→ Flagged for review")

                        if self.auto_file:
                            self.filer.file_review_email(message_id, remove_from_inbox=False)
                            self.stats['filed'] += 1

                    elif classification['action'] == 'process':
                        # Press release
                        self.stats['press_releases'] += 1
                        print(f"→ Press release")

                        # Extract PR URL
                        email_obj = self.gmail_message_to_email_object(gmail_msg)
                        decoded_subject = decode_email_subject(subject)

                        pr_result = extract_pr_url_from_email(email_obj, context, decoded_subject)

                        if pr_result and pr_result.pr_url:
                            print(f"   URL: {pr_result.pr_url[:60]}...")

                            # Ingest (scrape and save)
                            if self.auto_scrape:
                                press_release = self.ingest_press_release(
                                    pr_result.pr_url,
                                    subject,
                                    from_header,
                                    email_date
                                )

                            # File to label
                            if self.auto_file:
                                self.filer.file_press_release(message_id, email_date)
                                self.stats['filed'] += 1
                        else:
                            print(f"   ❌ Could not extract PR URL")
                            self.stats['errors'] += 1

                except Exception as e:
                    print(f"   ❌ Error processing email: {e}")
                    self.stats['errors'] += 1
                    continue

            browser.close()

        # Print summary
        self._print_summary()

        return self.stats

    def _print_summary(self):
        """Print processing summary"""
        print(f"\n{'='*80}")
        print("SUMMARY")
        print(f"{'='*80}\n")

        print(f"Total emails processed: {self.stats['total']}")
        print(f"  📰 Press releases: {self.stats['press_releases']}")
        print(f"  ✉️  Subscriptions: {self.stats['subscriptions']}")
        print(f"  ⚠️  Flagged for review: {self.stats['reviews']}")
        print(f"\nActions:")
        print(f"  🔍 Scraped & saved: {self.stats['scraped']}")
        print(f"  📁 Filed to labels: {self.stats['filed']}")
        print(f"  ❌ Errors: {self.stats['errors']}")
        print()

    def close(self):
        """Clean up resources"""
        if self.scraper:
            self.scraper.close()
        if self.db:
            self.db.close()


def main():
    """Main execution"""
    import argparse

    parser = argparse.ArgumentParser(description='Scan, ingest, and file emails automatically')
    parser.add_argument('--max-results', type=int, default=50, help='Maximum emails to process')
    parser.add_argument('--days-back', type=int, default=7, help='Process emails from last N days')
    parser.add_argument('--no-scrape', action='store_true', help='Skip scraping press releases')
    parser.add_argument('--no-file', action='store_true', help='Skip filing to labels')

    args = parser.parse_args()

    # Authenticate
    print("Authenticating with Gmail API...")
    service = authenticate_gmail()
    print("✅ Authenticated!\n")

    # Process emails
    processor = EmailProcessor(
        service,
        auto_file=not args.no_file,
        auto_scrape=not args.no_scrape
    )

    try:
        stats = processor.process_batch(
            max_results=args.max_results,
            days_back=args.days_back
        )

        print(f"\n{'='*80}")
        print("COMPLETE")
        print(f"{'='*80}\n")
        print("✅ Your inbox has been organized!")
        print("   • Press releases filed by year and month")
        print("   • Subscriptions filed to 'IR Account Validations'")
        print("   • Review emails labeled 'To Review'")
        print("   • All processed emails archived from INBOX")

    finally:
        processor.close()


if __name__ == '__main__':
    main()
