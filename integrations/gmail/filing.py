"""
Gmail Filing System

Automatically organizes emails into labeled folders:
- Press releases: Year/MM-Month (e.g., "2026/03-Mar")
- Subscription emails: "IR Account Validations"

SOLID Principle: Single responsibility - handles ONLY Gmail label management and filing.
"""
import sys
import os
from datetime import datetime
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


class GmailFiler:
    """
    Manages Gmail labels and files emails into organized folders.

    Follows Gmail's label hierarchy: parent/child labels create folder-like structure.
    """

    def __init__(self, service):
        """
        Initialize Gmail filer

        Args:
            service: Authenticated Gmail API service
        """
        self.service = service
        self._label_cache = {}  # Cache label IDs to avoid repeated API calls
        self._refresh_label_cache()

    def _refresh_label_cache(self):
        """Load all existing labels into cache"""
        try:
            results = self.service.users().labels().list(userId='me').execute()
            labels = results.get('labels', [])

            for label in labels:
                self._label_cache[label['name']] = label['id']

        except Exception as e:
            print(f"Warning: Could not load label cache: {e}")
            self._label_cache = {}

    def _get_or_create_label(self, label_name: str, parent_label_id: Optional[str] = None) -> str:
        """
        Get existing label ID or create new label

        Args:
            label_name: Name of the label
            parent_label_id: Parent label ID for nested labels (optional)

        Returns:
            Label ID
        """
        # Check cache first
        if label_name in self._label_cache:
            return self._label_cache[label_name]

        # Create new label
        try:
            label_object = {
                'name': label_name,
                'labelListVisibility': 'labelShow',
                'messageListVisibility': 'show'
            }

            created_label = self.service.users().labels().create(
                userId='me',
                body=label_object
            ).execute()

            label_id = created_label['id']
            self._label_cache[label_name] = label_id

            print(f"✅ Created label: {label_name}")
            return label_id

        except Exception as e:
            # Label might already exist but not in cache - refresh and try again
            if 'Label name exists' in str(e):
                self._refresh_label_cache()
                if label_name in self._label_cache:
                    return self._label_cache[label_name]

            print(f"❌ Error creating label {label_name}: {e}")
            raise

    def get_press_release_label(self, date: datetime) -> str:
        """
        Get or create press release label in format: Year/MM-Month

        Example: "2026/03-Mar", "2025/12-Dec"

        Args:
            date: Date of the press release

        Returns:
            Label ID
        """
        year = date.strftime('%Y')
        month_num = date.strftime('%m')
        month_abbr = date.strftime('%b')
        month_label = f"{month_num}-{month_abbr}"

        # Gmail uses "/" in label names to create hierarchy
        year_label_name = year
        full_label_name = f"{year}/{month_label}"

        # Ensure year label exists
        year_label_id = self._get_or_create_label(year_label_name)

        # Create/get month label (nested under year)
        month_label_id = self._get_or_create_label(full_label_name, parent_label_id=year_label_id)

        return month_label_id

    def get_subscription_label(self) -> str:
        """
        Get or create subscription/validation email label

        Returns:
            Label ID for "IR Account Validations"
        """
        label_name = "IR Account Validations"
        return self._get_or_create_label(label_name)

    def file_press_release(self, message_id: str, date: datetime, remove_from_inbox: bool = True):
        """
        File press release email into Year/MM-Month label

        Args:
            message_id: Gmail message ID
            date: Date of the press release
            remove_from_inbox: If True, removes INBOX label (archives email)
        """
        try:
            label_id = self.get_press_release_label(date)

            # Add press release label
            self.service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'addLabelIds': [label_id]}
            ).execute()

            # Remove from inbox (archive)
            if remove_from_inbox:
                self.service.users().messages().modify(
                    userId='me',
                    id=message_id,
                    body={'removeLabelIds': ['INBOX']}
                ).execute()

            print(f"   📁 Filed to: {date.strftime('%Y/%m-%b')}")

        except Exception as e:
            print(f"   ❌ Failed to file press release: {e}")

    def file_subscription(self, message_id: str, remove_from_inbox: bool = True):
        """
        File subscription/validation email into "IR Account Validations" label

        Args:
            message_id: Gmail message ID
            remove_from_inbox: If True, removes INBOX label (archives email)
        """
        try:
            label_id = self.get_subscription_label()

            # Add subscription label
            self.service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'addLabelIds': [label_id]}
            ).execute()

            # Remove from inbox (archive)
            if remove_from_inbox:
                self.service.users().messages().modify(
                    userId='me',
                    id=message_id,
                    body={'removeLabelIds': ['INBOX']}
                ).execute()

            print(f"   📁 Filed to: IR Account Validations")

        except Exception as e:
            print(f"   ❌ Failed to file subscription: {e}")

    def file_review_email(self, message_id: str, remove_from_inbox: bool = False):
        """
        File review email into "To Review" label (keeps in inbox by default)

        Args:
            message_id: Gmail message ID
            remove_from_inbox: If True, removes INBOX label
        """
        try:
            # Get or create "To Review" label
            label_id = self._get_or_create_label("To Review")

            # Add review label
            self.service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'addLabelIds': [label_id]}
            ).execute()

            # Optionally remove from inbox
            if remove_from_inbox:
                self.service.users().messages().modify(
                    userId='me',
                    id=message_id,
                    body={'removeLabelIds': ['INBOX']}
                ).execute()

            print(f"   📁 Labeled: To Review")

        except Exception as e:
            print(f"   ❌ Failed to label review email: {e}")

    def batch_file_emails(self, emails_to_file: List[Dict]):
        """
        File multiple emails in batch

        Args:
            emails_to_file: List of dicts with keys:
                - message_id: Gmail message ID
                - type: 'press_release', 'subscription', or 'review'
                - date: datetime (required for press_release type)
        """
        print(f"\n📁 Filing {len(emails_to_file)} emails...")

        for email_info in emails_to_file:
            message_id = email_info['message_id']
            email_type = email_info['type']

            if email_type == 'press_release':
                date = email_info.get('date')
                if date:
                    self.file_press_release(message_id, date)
                else:
                    print(f"   ⚠️  Missing date for press release: {message_id}")

            elif email_type == 'subscription':
                self.file_subscription(message_id)

            elif email_type == 'review':
                self.file_review_email(message_id)

        print("✅ Filing complete!")


def create_label_structure_preview(service):
    """
    Preview the label structure that will be created

    Useful for testing before actually filing emails.
    """
    print("\n📋 Gmail Label Structure Preview:")
    print("=" * 60)

    current_year = datetime.now().year
    current_month = datetime.now().month

    print(f"\nPress Release Labels (example for {current_year}):")
    print(f"  📁 {current_year}/")

    for month in range(1, 13):
        date = datetime(current_year, month, 1)
        label = date.strftime("%m-%b")
        indicator = "👉" if month == current_month else "  "
        print(f"    {indicator} 📄 {label}")

    print(f"\nSubscription Labels:")
    print(f"  📁 IR Account Validations")

    print(f"\nReview Labels:")
    print(f"  📁 To Review")

    print("=" * 60)
    print("\nNote: Labels will be created automatically as emails are filed.")
    print("Gmail displays labels with '/' as nested folders.\n")


if __name__ == '__main__':
    """Test the filing system"""
    from integrations.gmail.auth import authenticate_gmail

    print("Authenticating with Gmail...")
    service = authenticate_gmail()
    print("✅ Authenticated!\n")

    # Show label structure preview
    create_label_structure_preview(service)

    # Initialize filer
    filer = GmailFiler(service)

    print("\n✅ Gmail Filer initialized and ready!")
    print("\nTo use in your code:")
    print("  from integrations.gmail.filing import GmailFiler")
    print("  filer = GmailFiler(service)")
    print("  filer.file_press_release(message_id, date)")
    print("  filer.file_subscription(message_id)")
