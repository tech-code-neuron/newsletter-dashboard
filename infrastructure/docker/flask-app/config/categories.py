"""
Press release category configuration.

Extracted from core/categorizer.py to allow importing without SQLite dependencies.
These are used by templates and routes that need category lists.
"""

# Category priorities (order matters for newsletter)
CATEGORIES = [
    'M&A',
    'Property Transactions and Leases',
    'Equity Offerings',
    'Debt Offerings',
    'Credit Facilities',
    'Board Changes',
    'Personnel Changes',
    'Earnings',
    'Dividends',
    'Conference Call',
    'Other'
]

# Breaking news categories (for 9am brief)
BREAKING_CATEGORIES = ['M&A', 'Equity Offerings', 'Debt Offerings']
