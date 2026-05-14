"""
Review Email Service - Business Logic Layer

Single Responsibility: Handle review email operations.
Each function does ONE thing and does it well.

Uses Repository Pattern for database abstraction (DynamoDB in ECS, SQLite local).
"""
from datetime import datetime, timezone
import re

from core.repositories import get_review_email_repo, get_press_release_repo, get_company_repo
from integrations.gmail.auth import authenticate_gmail
from utils.file_utils import delete_screenshot
from utils.review_constants import (
    ReviewEmailStatus,
    ReviewEmailErrors,
    PR_CONTENT_PREVIEW_LENGTH,
    SCRAPER_HEADLESS_MODE
)


class ReviewEmailService:
    """Service class for review email operations"""

    @staticmethod
    def get_pending_reviews():
        """
        Get all pending review emails, newest first.

        Returns:
            list[ReviewEmailDTO]: Pending review emails
        """
        repo = get_review_email_repo()
        return repo.get_pending()

    @staticmethod
    def get_review_by_id(review_id):
        """
        Get review email by ID.

        Args:
            review_id (int): Review email ID

        Returns:
            ReviewEmailDTO or None: Review email if found
        """
        repo = get_review_email_repo()
        return repo.get_by_id(review_id)

    @staticmethod
    def validate_for_processing(review):
        """
        Validate that review can be processed.

        Args:
            review (ReviewEmailDTO): Review email to validate

        Returns:
            tuple[bool, str or None]: (is_valid, error_message)
        """
        if not review:
            return False, ReviewEmailErrors.NOT_FOUND

        if review.status != ReviewEmailStatus.PENDING:
            return False, ReviewEmailErrors.ALREADY_PROCESSING.format(status=review.status)

        return True, None

    @staticmethod
    def mark_as_processing(review_id):
        """
        Mark review email as processing.

        Args:
            review_id (int): Review email ID
        """
        repo = get_review_email_repo()
        repo.update_status(review_id, ReviewEmailStatus.PROCESSING)

    @staticmethod
    def mark_as_pending(review_id, reason):
        """
        Mark review email as pending with reason.

        Args:
            review_id (int): Review email ID
            reason (str): Reason for pending status
        """
        repo = get_review_email_repo()
        repo.update_status(review_id, ReviewEmailStatus.PENDING, classification_reason=reason)

    @staticmethod
    def mark_as_added(review_id, press_release_id):
        """
        Mark review email as successfully added.

        Args:
            review_id (int): Review email ID
            press_release_id: ID/URL of created press release
        """
        repo = get_review_email_repo()
        repo.update_status(
            review_id,
            ReviewEmailStatus.ADDED,
            press_release_id=press_release_id,
            processed_at=datetime.now(timezone.utc).isoformat()
        )

    @staticmethod
    def mark_as_deleted(review_id):
        """
        Mark review email as deleted.

        Args:
            review_id (int): Review email ID
        """
        repo = get_review_email_repo()
        repo.update_status(
            review_id,
            ReviewEmailStatus.DELETED,
            processed_at=datetime.now(timezone.utc).isoformat()
        )

    @staticmethod
    def extract_pr_url(review, browser_context):
        """
        Extract press release URL from email.

        Args:
            review (ReviewEmailDTO): Review email
            browser_context: Playwright browser context

        Returns:
            str or None: Press release URL if found
        """
        from pr_email_parser_v2 import extract_pr_url_from_email, decode_email_subject
        import email as email_lib

        try:
            msg = email_lib.message_from_bytes(review.raw_email.encode('utf-8'))
            decoded_subject = decode_email_subject(review.subject)
            pr_result = extract_pr_url_from_email(msg, browser_context, decoded_subject)

            if pr_result:
                return pr_result.pr_url
            return None

        except Exception:
            return None

    @staticmethod
    def match_company_from_subject(subject):
        """
        Match company from email subject.

        Args:
            subject (str): Email subject

        Returns:
            CompanyDTO or None: Matched company if found
        """
        company_repo = get_company_repo()
        companies = company_repo.get_all_active()

        for company in companies:
            if company.name.lower() in subject.lower() or \
               company.ticker.lower() in subject.lower():
                return company

        return None

    @staticmethod
    def check_pr_exists(pr_url):
        """
        Check if press release already exists.

        Args:
            pr_url (str): Press release URL

        Returns:
            PressReleaseDTO or None: Existing press release if found
        """
        pr_repo = get_press_release_repo()
        return pr_repo.get_by_url(pr_url)

    @staticmethod
    def clean_title_from_subject(subject):
        """
        Clean title from email subject.

        Removes company name prefix (e.g., "Company Name - Title" -> "Title")

        Args:
            subject (str): Email subject

        Returns:
            str: Cleaned title
        """
        # Remove company name prefix if present
        title = re.sub(r'^.*?\s*-\s*', '', subject)
        return title.strip()

    @staticmethod
    def scrape_press_release_content(pr_url):
        """
        Scrape press release content from URL.

        Args:
            pr_url (str): Press release URL

        Returns:
            str or None: Press release content if successful
        """
        from core.scraper import PressReleaseScraper

        scraper = None
        try:
            scraper = PressReleaseScraper(headless=SCRAPER_HEADLESS_MODE)
            content = scraper.fetch_press_release_content(pr_url)
            return content
        finally:
            if scraper:
                scraper.close()

    @staticmethod
    def create_press_release(company, title, pr_url, published_date, content):
        """
        Create new press release in database.

        Args:
            company (CompanyDTO): Company
            title (str): Press release title
            pr_url (str): Press release URL
            published_date (datetime): Published date
            content (str): Full content

        Returns:
            PressReleaseDTO: Created press release
        """
        import secrets

        pr_repo = get_press_release_repo()

        # Generate unique_id and slug
        # SECURITY: Use cryptographically secure random for IDs (not random.randint)
        unique_id = secrets.token_urlsafe(8)  # URL-safe, cryptographically secure
        words = re.sub(r'[^\w\s]', '', title.lower()).split()
        slug = '-'.join(words[:4])

        pr_data = {
            'company_id': company.id,
            'ticker': company.ticker,
            'title': title,
            'url': pr_url,
            'published_date': published_date.isoformat() if hasattr(published_date, 'isoformat') else str(published_date),
            'press_release_date': published_date.isoformat() if hasattr(published_date, 'isoformat') else str(published_date),
            'content': content[:PR_CONTENT_PREVIEW_LENGTH] if content else '',
            'full_text': content,
            'unique_id': unique_id,
            'slug': slug
        }

        return pr_repo.create(pr_data)

    @staticmethod
    def delete_from_gmail(gmail_message_id):
        """
        Delete email from Gmail (move to trash).

        Args:
            gmail_message_id (str): Gmail message ID

        Returns:
            bool: True if deleted successfully
        """
        try:
            service = authenticate_gmail()
            service.users().messages().trash(
                userId='me',
                id=gmail_message_id
            ).execute()
            return True
        except Exception:
            return False

    @staticmethod
    def cleanup_review_resources(review):
        """
        Clean up resources associated with review email.

        Deletes screenshot file.

        Args:
            review (ReviewEmailDTO): Review email
        """
        if review.screenshot_path:
            delete_screenshot(review.screenshot_path)

    @staticmethod
    def process_review_in_background(review_id):
        """
        Process review email in background thread.

        Single Responsibility: Orchestrates full review email processing workflow

        Workflow:
        1. Extract PR URL from email
        2. Validate URL (SSRF protection)
        3. Match company from subject
        4. Check if PR already exists
        5. Scrape content
        6. Create press release
        7. Mark review as completed

        Args:
            review_id (int): Review email ID
        """
        from playwright.sync_api import sync_playwright
        from utils.url_utils import is_safe_url

        review = ReviewEmailService.get_review_by_id(review_id)
        if not review:
            return

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                )

                # Step 1: Extract PR URL
                pr_url = ReviewEmailService.extract_pr_url(review, context)
                if not pr_url:
                    ReviewEmailService.mark_as_pending(review_id, ReviewEmailErrors.EXTRACTION_FAILED)
                    browser.close()
                    return

                # Step 2: SECURITY - Validate URL
                if not is_safe_url(pr_url):
                    ReviewEmailService.mark_as_pending(
                        review_id,
                        ReviewEmailErrors.UNSAFE_URL.format(url=pr_url)
                    )
                    browser.close()
                    return

                browser.close()

            # Step 3: Match company
            company = ReviewEmailService.match_company_from_subject(review.subject)
            if not company:
                ReviewEmailService.mark_as_pending(review_id, ReviewEmailErrors.NO_COMPANY_MATCH)
                return

            # Step 4: Check if already exists
            existing = ReviewEmailService.check_pr_exists(pr_url)
            if existing:
                ReviewEmailService.mark_as_added(review_id, existing.url)
                return

            # Step 5: Scrape content
            content = ReviewEmailService.scrape_press_release_content(pr_url)
            if not content:
                ReviewEmailService.mark_as_pending(review_id, ReviewEmailErrors.FETCH_FAILED)
                return

            # Step 6: Create press release
            title = ReviewEmailService.clean_title_from_subject(review.subject)
            published_date = review.date or datetime.now(timezone.utc)

            new_pr = ReviewEmailService.create_press_release(
                company, title, pr_url, published_date, content
            )

            # Step 7: Mark as added and cleanup
            ReviewEmailService.mark_as_added(review_id, new_pr.url)
            ReviewEmailService.cleanup_review_resources(review)

        except Exception as e:
            ReviewEmailService.mark_as_pending(review_id, f'Error: {str(e)}')
