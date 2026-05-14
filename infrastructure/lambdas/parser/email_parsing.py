"""
Parser Lambda - Email Parsing
==============================
Extract metadata and URLs from email content

SOLID Principles:
- Single Responsibility: Each function does ONE thing
- No Hardcoded Values: All constants imported

Last Updated: 2026-03-12
"""

import logging
import re
from datetime import datetime
from email.parser import BytesParser
from email import policy
from constants import CONFIRMATION_KEYWORDS, ACTIVATION_KEYWORDS
from url_utils import extract_urls_from_text, extract_urls_from_email

logger = logging.getLogger()

# ============================================================================
# Press Release Date Extraction
# ============================================================================


def extract_press_release_date(html_text, plain_text=''):
    """
    Extract press release date from email body.

    Most PR emails have a "Date Sent: YYYY-MM-DD H:MM:SS AM/PM" in the footer.
    This function finds and parses that date.

    Single Responsibility: Only extracts the PR date from email body

    Args:
        html_text: HTML email body
        plain_text: Plain text email body (fallback)

    Returns:
        str: Press release date in YYYY-MM-DD format, or None if not found
    """
    # Pattern: "Date Sent: 2026-03-11 7:18:30 PM"
    date_pattern = r'Date Sent:\s*(\d{4}-\d{2}-\d{2})\s+\d{1,2}:\d{2}:\d{2}\s+(?:AM|PM)'

    # Try HTML text first (most emails are HTML)
    if html_text:
        match = re.search(date_pattern, html_text, re.IGNORECASE)
        if match:
            date_str = match.group(1)  # YYYY-MM-DD
            logger.info(f"Extracted press release date from HTML: {date_str}")
            return date_str

    # Fallback to plain text
    if plain_text:
        match = re.search(date_pattern, plain_text, re.IGNORECASE)
        if match:
            date_str = match.group(1)  # YYYY-MM-DD
            logger.info(f"Extracted press release date from plain text: {date_str}")
            return date_str

    # Alternative pattern: Try other date formats if Date Sent doesn't exist
    # Pattern: "March 11, 2026" or "3/11/2026"
    alt_patterns = [
        r'(\w+\s+\d{1,2},\s+\d{4})',  # March 11, 2026
        r'(\d{1,2}/\d{1,2}/\d{4})',   # 3/11/2026
        r'(\d{4}-\d{2}-\d{2})',        # 2026-03-11
    ]

    for pattern in alt_patterns:
        if html_text:
            match = re.search(pattern, html_text)
            if match:
                date_str = match.group(1)
                try:
                    # Try to parse and convert to YYYY-MM-DD
                    if '/' in date_str:
                        dt = datetime.strptime(date_str, '%m/%d/%Y')
                    elif ',' in date_str:
                        dt = datetime.strptime(date_str, '%B %d, %Y')
                    else:
                        dt = datetime.strptime(date_str, '%Y-%m-%d')

                    formatted_date = dt.strftime('%Y-%m-%d')
                    logger.info(f"Extracted press release date from HTML (alt format): {formatted_date}")
                    return formatted_date
                except Exception as e:
                    logger.debug(f"Could not parse date '{date_str}': {e}")
                    continue

    logger.warning("Could not extract press release date from email body")
    return None


# ============================================================================
# Email Metadata Extraction
# ============================================================================


def extract_email_metadata(email_content):
    """
    Extract metadata from email (subject, from, date, URLs)

    Single Responsibility: Only extracts metadata

    Args:
        email_content: Raw email bytes

    Returns:
        dict: Email metadata {subject, from, date, urls_plain, urls_html}
    """
    try:
        # Parse email
        msg = BytesParser(policy=policy.default).parsebytes(email_content)

        # Extract headers
        subject = msg.get('Subject', '')
        from_field = msg.get('From', '')
        date_field = msg.get('Date', '')

        # Extract sender name and domain from From header
        # Format: "Name <email@domain.com>" or just "email@domain.com"
        sender_name = ''
        sender_domain = ''
        if from_field:
            # Try to extract email address
            email_match = re.search(r'<([^>]+)>|([^\s]+@[^\s]+)', from_field)
            if email_match:
                email_address = email_match.group(1) or email_match.group(2)
                # Extract domain from email
                if '@' in email_address:
                    sender_domain = email_address.split('@')[1].strip()

            # Extract sender name (text before <email>)
            name_match = re.match(r'([^<]+)<', from_field)
            if name_match:
                sender_name = name_match.group(1).strip().strip('"')
            elif '@' not in from_field:
                sender_name = from_field.strip()

        # Extract body text (both plain and HTML)
        plain_text = ""
        html_text = ""

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == 'text/plain':
                    try:
                        plain_text = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                        logger.debug(f"Extracted plain text: {len(plain_text)} chars")
                    except Exception as e:
                        logger.warning(f"Error decoding plain text: {e}")
                elif content_type == 'text/html':
                    try:
                        html_text = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                        logger.info(f"Extracted HTML text: {len(html_text)} chars")
                    except Exception as e:
                        logger.warning(f"Error decoding HTML: {e}")
        else:
            # Single-part message
            try:
                content = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                # Check if HTML or plain text
                if msg.get_content_type() == 'text/html':
                    html_text = content
                    logger.info(f"Extracted HTML text (single-part): {len(html_text)} chars")
                else:
                    plain_text = content
                    logger.debug(f"Extracted plain text (single-part): {len(plain_text)} chars")
            except Exception as e:
                logger.warning(f"Error decoding message: {e}")

        # Extract URLs with fuzzy logic (prioritizes "View Press Release" links)
        # NEW 2026-03-10: Uses link text context for better PR detection
        all_urls = extract_urls_from_email(msg)

        # Legacy fallback: Extract from plain/HTML text separately (for debugging)
        urls_plain = extract_urls_from_text(plain_text)
        urls_html = extract_urls_from_text(html_text)

        # Extract press release date from email body
        press_release_date = extract_press_release_date(html_text, plain_text)

        metadata = {
            'subject': subject,
            'from': from_field,
            'sender_name': sender_name,  # Extracted sender name (for confidence scoring)
            'sender_domain': sender_domain,  # Extracted sender domain (for confidence scoring)
            'date': date_field,
            'press_release_date': press_release_date,  # Extracted from email body (YYYY-MM-DD)
            'plain_text': plain_text,
            'html_text': html_text,
            'urls': all_urls,  # Prioritized URLs with fuzzy logic
            'urls_plain': urls_plain,  # Legacy
            'urls_html': urls_html  # Legacy
        }

        logger.info(f"Extracted email metadata: Subject='{subject[:60]}...', URLs={len(all_urls)} (with fuzzy logic), PR Date={press_release_date}")

        return metadata

    except Exception as e:
        logger.error(f"Error extracting email metadata: {e}", exc_info=True)
        return {
            'subject': '',
            'from': '',
            'date': '',
            'press_release_date': None,
            'plain_text': '',
            'html_text': '',
            'urls': [],
            'urls_plain': [],
            'urls_html': []
        }


# ============================================================================
# Email Classification
# ============================================================================


def is_confirmation_email(subject, body_text=''):
    """
    Check if email is a confirmation/validation/signup OR SEC filing

    Single Responsibility: Only classifies email type

    Returns True if email should be skipped (not a press release)

    Args:
        subject: Email subject line
        body_text: Email body text (optional)

    Returns:
        bool: True if confirmation/SEC email, False otherwise
    """
    if not subject:
        return False

    subject_lower = subject.lower()
    body_lower = body_text.lower() if body_text else ''

    # Check activation keywords first (subject only - these are subscription emails)
    for keyword in ACTIVATION_KEYWORDS:
        if keyword in subject_lower:
            logger.info(f"Skipping activation email (subject): '{subject[:80]}'")
            return True

    # Check SEC filing keywords in subject line
    for keyword in CONFIRMATION_KEYWORDS:
        if keyword in subject_lower:
            logger.info(f"Skipping confirmation email (subject): '{subject[:80]}'")
            return True

    # If subject doesn't have keywords, check body (first 2000 chars for SEC filing announcements)
    # SEC filing announcement text often appears after company logo/header in HTML emails
    if body_lower:
        body_sample = body_lower[:2000]  # Increased from 500 to catch SEC filing announcements
        for keyword in CONFIRMATION_KEYWORDS:
            if keyword in body_sample:
                logger.info(f"Skipping confirmation/SEC email (body keyword: '{keyword}'): '{subject[:80]}'")
                return True

    return False
