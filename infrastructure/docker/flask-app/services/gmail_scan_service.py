"""
Gmail Scan Service - Email Scanning and Processing

Single Responsibility: Handle Gmail inbox scanning operations.
Breaks down complex scanning logic into focused functions.

Uses Repository Pattern for database abstraction (DynamoDB in ECS, SQLite local).
"""
import base64
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr, parsedate_to_datetime
from playwright.sync_api import sync_playwright

from core.repositories import get_review_email_repo
from integrations.gmail.auth import authenticate_gmail, get_message_header
from integrations.gmail.to_review import classify_email, extract_html_from_email, capture_email_screenshot
from utils.file_utils import ensure_screenshot_directory, get_screenshot_full_path, get_screenshot_web_path
from utils.review_constants import (
    MAX_EMAIL_SIZE_BYTES,
    SCAN_MAX_RESULTS_ALL_TIME,
    SCAN_MAX_RESULTS_24H,
    SCAN_MAX_RESULTS_7D,
    ReviewEmailStatus,
    ReviewEmailErrors
)


class GmailScanService:
    """Service class for Gmail scanning operations"""

    @staticmethod
    def authenticate():
        """
        Authenticate with Gmail API.

        Returns:
            Resource: Gmail API service
        """
        return authenticate_gmail()

    @staticmethod
    def build_time_query(time_range):
        """
        Build Gmail query based on time range.

        Args:
            time_range (str): '24h', '7d', or 'all'

        Returns:
            str: Gmail query string
        """
        query = 'in:inbox'

        if time_range == '24h':
            after_date = (datetime.now() - timedelta(days=1)).strftime('%Y/%m/%d')
            query += f' after:{after_date}'
        elif time_range == '7d':
            after_date = (datetime.now() - timedelta(days=7)).strftime('%Y/%m/%d')
            query += f' after:{after_date}'

        return query

    @staticmethod
    def get_max_results(time_range):
        """
        Get maximum results to fetch based on time range.

        Args:
            time_range (str): '24h', '7d', or 'all'

        Returns:
            int: Maximum number of results
        """
        return {
            'all': SCAN_MAX_RESULTS_ALL_TIME,
            '24h': SCAN_MAX_RESULTS_24H,
            '7d': SCAN_MAX_RESULTS_7D
        }.get(time_range, SCAN_MAX_RESULTS_ALL_TIME)

    @staticmethod
    def fetch_messages(service, time_range):
        """
        Fetch messages from Gmail inbox.

        Args:
            service: Gmail API service
            time_range (str): '24h', '7d', or 'all'

        Returns:
            list: Gmail message references
        """
        query = GmailScanService.build_time_query(time_range)
        max_results = GmailScanService.get_max_results(time_range)

        results = service.users().messages().list(
            userId='me',
            q=query,
            maxResults=max_results
        ).execute()

        return results.get('messages', [])

    @staticmethod
    def get_message_details(service, message_id):
        """
        Get message metadata and raw content.

        Args:
            service: Gmail API service
            message_id (str): Gmail message ID

        Returns:
            tuple: (metadata_message, raw_message)
        """
        metadata = service.users().messages().get(
            userId='me',
            id=message_id,
            format='full'
        ).execute()

        raw = service.users().messages().get(
            userId='me',
            id=message_id,
            format='raw'
        ).execute()

        return metadata, raw

    @staticmethod
    def extract_email_headers(metadata_message):
        """
        Extract subject, from, and date headers from message.

        Args:
            metadata_message (dict): Gmail message metadata

        Returns:
            tuple: (subject, from_header, email_date)
        """
        subject = get_message_header(metadata_message, 'subject')
        from_header = get_message_header(metadata_message, 'from')
        date_header = get_message_header(metadata_message, 'date')

        try:
            email_date = parsedate_to_datetime(date_header)
        except:
            email_date = datetime.now(timezone.utc)

        return subject, from_header, email_date

    @staticmethod
    def parse_sender_info(from_header):
        """
        Parse sender name, email, and domain from header.

        Args:
            from_header (str): Email "From" header

        Returns:
            tuple: (name, email_addr, domain)
        """
        name, email_addr = parseaddr(from_header)
        domain = email_addr.split('@')[1] if '@' in email_addr else 'unknown'
        return name, email_addr, domain

    @staticmethod
    def check_email_size(raw_message):
        """
        Check if email size is within limits.

        Args:
            raw_message (dict): Gmail raw message

        Returns:
            tuple[bool, bytes]: (is_valid, raw_data)
        """
        raw_email_data = base64.urlsafe_b64decode(raw_message['raw'])

        if len(raw_email_data) > MAX_EMAIL_SIZE_BYTES:
            return False, raw_email_data

        return True, raw_email_data

    @staticmethod
    def review_email_exists(gmail_message_id):
        """
        Check if review email already exists in database.

        Args:
            gmail_message_id (str): Gmail message ID

        Returns:
            ReviewEmailDTO or None: Existing review email if found
        """
        repo = get_review_email_repo()
        return repo.get_by_gmail_id(gmail_message_id)

    @staticmethod
    def capture_screenshot_for_email(html_content, gmail_message_id, browser_context):
        """
        Capture screenshot for email.

        Args:
            html_content (str): Email HTML content
            gmail_message_id (str): Gmail message ID
            browser_context: Playwright browser context

        Returns:
            str or None: Web path to screenshot if successful
        """
        if not html_content:
            return None

        screenshot_full_path = get_screenshot_full_path(gmail_message_id)

        if capture_email_screenshot(html_content, screenshot_full_path, browser_context):
            return get_screenshot_web_path(gmail_message_id)

        return None

    @staticmethod
    def save_review_email(gmail_message_id, subject, from_header, email_addr,
                         domain, email_date, raw_email_data, screenshot_path,
                         classification_reason):
        """
        Save review email to database.

        Args:
            gmail_message_id (str): Gmail message ID
            subject (str): Email subject
            from_header (str): From header
            email_addr (str): Email address
            domain (str): Email domain
            email_date (datetime): Email date
            raw_email_data (bytes): Raw email data
            screenshot_path (str): Path to screenshot
            classification_reason (str): Why it was flagged for review

        Returns:
            ReviewEmailDTO: Created review email
        """
        repo = get_review_email_repo()

        review_data = {
            'gmail_message_id': gmail_message_id,
            'subject': subject,
            'from_header': from_header,
            'from_email': email_addr,
            'from_domain': domain,
            'date': email_date.isoformat() if hasattr(email_date, 'isoformat') else str(email_date),
            'raw_email': raw_email_data.decode('utf-8', errors='ignore'),
            'screenshot_path': screenshot_path,
            'classification_reason': classification_reason,
            'status': ReviewEmailStatus.PENDING
        }

        return repo.create(review_data)

    @staticmethod
    def setup_browser():
        """
        Setup Playwright browser for screenshot capture.

        Returns:
            tuple: (playwright, browser, context)
        """
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        return playwright, browser, context

    @staticmethod
    def cleanup_browser(playwright, browser):
        """
        Cleanup browser resources.

        Args:
            playwright: Playwright instance
            browser: Browser instance
        """
        if browser:
            browser.close()
        if playwright:
            playwright.stop()

    @staticmethod
    def process_single_message(message_ref, service, browser_context):
        """
        Process a single Gmail message.

        Args:
            message_ref (dict): Gmail message reference
            service: Gmail API service
            browser_context: Playwright browser context

        Returns:
            dict: Processing result {'action': str, 'review_saved': bool, 'existing': bool}
        """
        result = {
            'action': 'skip',
            'review_saved': False,
            'existing': False
        }

        # Get message details
        metadata, raw = GmailScanService.get_message_details(service, message_ref['id'])

        # Extract headers
        subject, from_header, email_date = GmailScanService.extract_email_headers(metadata)

        # Classify email
        classification = classify_email(subject, from_header)
        result['action'] = classification['action']

        # Only process review emails
        if classification['action'] != 'review':
            return result

        # Check email size
        size_ok, raw_email_data = GmailScanService.check_email_size(raw)
        if not size_ok:
            return result

        # Check if already exists
        existing = GmailScanService.review_email_exists(message_ref['id'])
        if existing:
            result['existing'] = True
            return result

        # Extract sender info
        name, email_addr, domain = GmailScanService.parse_sender_info(from_header)

        # Capture screenshot
        html_content = extract_html_from_email(raw)
        screenshot_path = GmailScanService.capture_screenshot_for_email(
            html_content, message_ref['id'], browser_context
        )

        # Save to database
        GmailScanService.save_review_email(
            message_ref['id'], subject, from_header, email_addr,
            domain, email_date, raw_email_data, screenshot_path,
            classification['reason']
        )

        result['review_saved'] = True
        return result

    @staticmethod
    def execute_scan(time_range, scan_manager):
        """
        Execute Gmail inbox scan in background.

        Single Responsibility: Orchestrates full Gmail scan workflow

        Workflow:
        1. Authenticate with Gmail
        2. Fetch messages based on time range
        3. Setup browser for screenshots
        4. Process each message (classify, screenshot, save)
        5. Update scan progress
        6. Cleanup resources

        Args:
            time_range (str): '24h', '7d', or 'all'
            scan_manager: Scan manager instance for progress tracking

        Returns:
            None (updates scan_manager state)
        """
        try:
            # Step 1: Authenticate
            scan_manager.update_status('Authenticating with Gmail...')
            service = GmailScanService.authenticate()

            # Step 2: Fetch messages
            scan_manager.update_status(f'Fetching emails ({time_range})...')
            messages = GmailScanService.fetch_messages(service, time_range)
            scan_manager.set_total(len(messages))

            # Check if scan was aborted
            if scan_manager.check_abort():
                scan_manager.finish_scan(success=False)
                return

            # Step 3: Setup resources
            ensure_screenshot_directory()
            playwright, browser, browser_context = GmailScanService.setup_browser()

            # Step 4: Process each message
            for i, msg_ref in enumerate(messages, 1):
                # Check for abort
                if scan_manager.check_abort():
                    break

                # Update progress
                scan_manager.update_progress(i)
                scan_manager.update_status(f'Processing email {i}/{len(messages)}...')

                # Process single message (all logic in service)
                result = GmailScanService.process_single_message(
                    msg_ref, service, browser_context
                )

                # Update counters
                if result['review_saved']:
                    scan_manager.increment_new()
                elif result['existing']:
                    scan_manager.increment_existing()

            # Step 5: Cleanup
            GmailScanService.cleanup_browser(playwright, browser)

            scan_manager.finish_scan(success=True)

        except Exception as e:
            scan_manager.update_status(f'Error: {str(e)}')
            scan_manager.finish_scan(success=False)
