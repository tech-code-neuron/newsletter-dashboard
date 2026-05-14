"""
Email Body Extractor
====================
Extracted from handler.py (lines 145-159)

SOLID: Single Responsibility - Only extracts email body text

Last Created: 2026-03-13
"""


def extract_email_body(msg):
    """
    Extract plain text body from email message

    SOLID: Single Responsibility - Only handles body extraction

    Args:
        msg: Email message object

    Returns:
        str: Email body text (lowercase)
    """
    body_text = ""

    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == 'text/plain':
                try:
                    body_text = part.get_payload(decode=True).decode('utf-8', errors='ignore').lower()
                    break
                except:
                    pass
    else:
        try:
            body_text = msg.get_payload(decode=True).decode('utf-8', errors='ignore').lower()
        except:
            pass

    return body_text
