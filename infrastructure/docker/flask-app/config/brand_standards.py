"""
Brand Standards - Single Source of Truth

Pre-commit validation reads from this file.
No .md documentation needed - the code IS the documentation.
"""

import re

# =============================================================================
# BRAND IDENTITY
# =============================================================================

BRAND = {
    'name_full': 'The Press Release Pipeline',
    'name_short': 'Press Release Pipeline',
    'logo_alt': 'Press Release Pipeline',
    'tagline': 'Never miss a REIT release',
    'domain': 'your-domain.com',
    'email_from': 'The Press Release Pipeline <alerts@your-domain.com>',
}

# =============================================================================
# CTA TEXT (approved copy)
# =============================================================================

CTA_TEXT = {
    'signup_nav': 'Get the Daily Brief',           # 19 chars (mobile-safe)
    'signup_box': 'Get the daily brief before the open',
    'signup_button': 'Subscribe',
    'email_cta': 'Subscribe',
}

# =============================================================================
# MOBILE TEXT LIMITS
# =============================================================================

MOBILE_TEXT_LIMITS = {
    'nav_cta': 28,        # Navigation CTA max chars
    'headline': 40,       # Signup box headline max
    'button': 15,         # Button text max
    'email_subject': 50,  # Email subject line max
}

# =============================================================================
# CTA SUGGESTIONS (for pre-commit warnings)
# =============================================================================

CTA_SUGGESTIONS = {
    # If CTA text is too long, suggest these alternatives
    'Get This Brief Before the Open': [       # 32 chars - too long for mobile nav
        'Get the Daily Brief',                # 19 chars
        'Free Daily REIT News',               # 20 chars
        'Subscribe Free',                     # 14 chars
    ],
}

# =============================================================================
# FORBIDDEN PATTERNS (pre-commit blocks these)
# =============================================================================

FORBIDDEN_PATTERNS = [
    # Brand name errors
    (r'\bREIT sheet\b', 'Brand Error: Use "Press Release Pipeline" (capital S)'),
    (r'\bThe Reit Sheet\b', 'Brand Error: Use "The Press Release Pipeline" (all caps REIT)'),
    (r'\breit sheet\b', 'Brand Error: Use "Press Release Pipeline" (capital letters)'),
    (r'\bReitSheet\b', 'Brand Error: Use "Press Release Pipeline" (with space)'),

    # CTA anti-patterns
    (r'\bClick here\b', 'CTA Error: Use action-oriented CTAs like "Subscribe" or "Get"'),
    # Note: "Submit" as button TEXT (not type="submit") - use >Submit< pattern
    (r'>Submit<', 'CTA Error: Use "Subscribe" instead of "Submit" for signup buttons'),

    # Domain errors
    (r'reit-sheet\.com', 'Domain Error: Use your-domain.com (no hyphen, .co not .com)'),
    (r'reitsheet\.com', 'Domain Error: Use your-domain.com (.co not .com)'),
]

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def check_forbidden_patterns(content: str) -> list[tuple[str, str]]:
    """Check content against forbidden patterns, return list of (match, message)."""
    violations = []
    for pattern, message in FORBIDDEN_PATTERNS:
        # Don't use IGNORECASE for brand name patterns - case matters!
        matches = re.findall(pattern, content)
        for match in matches:
            violations.append((match, message))
    return violations

def get_cta_suggestions(text: str, max_chars: int) -> list[str]:
    """Get shorter CTA alternatives if text exceeds limit."""
    if len(text) <= max_chars:
        return []

    # Check if we have pre-defined suggestions
    if text in CTA_SUGGESTIONS:
        return [s for s in CTA_SUGGESTIONS[text] if len(s) <= max_chars]

    # Generic suggestions
    return [
        'Get the Daily Brief',
        'Subscribe Free',
    ]
