"""
Email parser configuration.
Centralizes email parsing constants and mappings (Single Source of Truth).
"""

# ------------------------------------------------------------------
# TIMEOUT CONFIGURATION
# ------------------------------------------------------------------

# Playwright timeout for page loads (milliseconds)
PLAYWRIGHT_TIMEOUT_MS = 10000


# ------------------------------------------------------------------
# COMPANY DOMAIN MAPPINGS
# ------------------------------------------------------------------

# Company email → IR domain mapping
# Used to identify company from sender address
COMPANY_IR_DOMAINS = {
    'newsalerts@acresreit.com': 'www.acresreit.com',
    'no-reply@q4inc.com': None,  # Need to match by subject
    'no-reply@notification.gcs-web.com': None,  # Need to match by subject
    'alerts@em.equisolve.com': None,  # Need to match by subject
}

# Company name → IR domain mapping
# Used to identify company from email subject line
COMPANY_NAME_TO_DOMAIN = {
    'chatham': 'chathamlodgingtrust.gcs-web.com',
    'digital realty': 'investor.digitalrealty.com',
    'brixmor': 'investors.brixmor.com',
    'veris': 'investors.verisresidential.com',
    'acres': 'www.acresreit.com',
}


# ------------------------------------------------------------------
# URL FILTERING - Skip Patterns
# ------------------------------------------------------------------

# URL patterns to skip (not PR links)
# Open/Closed: Add new patterns here without modifying parser logic
SKIP_URL_PATTERNS = [
    'unsubscribe',
    'mailto:',
    'preferences',
    'manage',
    'logo',
    'facebook',
    'twitter',
    'linkedin',
    'instagram',
    'youtube',
    '.png',
    '.jpg',
    '.gif',
    'email-alert',
    'email alert',
    'q4inc.com',  # Q4 platform domain (not PR URL)
]

# Generic newswire homepage URLs to skip
# We want company-specific PR URLs only, not newswire homepages
NEWSWIRE_GENERIC_URLS = [
    'http://www.prnewswire.com/',
    'https://www.prnewswire.com/',
    'http://www.businesswire.com/',
    'https://www.businesswire.com/',
    'http://www.globenewswire.com/',
    'https://www.globenewswire.com/',
]
