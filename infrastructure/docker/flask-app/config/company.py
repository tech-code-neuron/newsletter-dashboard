"""
Company configuration - single source of truth for business details.
"""

# Physical address (CAN-SPAM requirement for emails)
COMPANY_ADDRESS = "3010 Edgeview Ln #312, Charlotte, NC 28209"

# Email sender
COMPANY_NAME = "The Press Release Pipeline"
SENDER_EMAIL = "alerts@reitsheet.co"  # For internal/forwarded emails
NEWSLETTER_EMAIL = "newsletter@reitsheet.co"  # For subscriber emails (unmonitored)
REPLY_TO_EMAIL = "hello@reitsheet.co"  # Where replies should go
