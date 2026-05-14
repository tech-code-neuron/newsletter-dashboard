"""
Blueprint registration - Central import point for all blueprints
Add new blueprints here to enable them in the application

SOLID Compliance: Open/Closed Principle
- Add new blueprints by adding to this list
- No need to modify app.py (just re-import from routes)

ECS Support:
- Core blueprints use DynamoDB repositories (work everywhere)
- Local-only blueprints (actions, review_emails) require SQLite, Gmail, Playwright
- These are conditionally imported to avoid boot failures in ECS
"""
# Core blueprints - work in both ECS and local environments
from routes.dashboard import dashboard_bp
from routes.companies import companies_bp
from routes.actions import actions_bp  # Uses deferred imports for SQLite modules
from routes.api import api_bp
from routes.auth import auth_bp
from routes.publisher import publisher_bp
from routes.publisher_styles import bp as publisher_styles_bp
from routes.publisher_email import bp as publisher_email_bp
from routes.emails import emails_bp
from routes.contact import contact_bp
from routes.disclosures import disclosures_bp
from routes.test_signup import test_signup_bp
from routes.subscribe import subscribe_bp
from routes.public import public_bp
from routes.sponsors import sponsors_bp
from routes.brave_review import brave_review_bp
from routes.og import og_bp

__all__ = [
    'dashboard_bp',
    'companies_bp',
    'actions_bp',
    'api_bp',
    'auth_bp',
    'publisher_bp',
    'publisher_styles_bp',
    'publisher_email_bp',
    'emails_bp',
    'contact_bp',
    'disclosures_bp',
    'test_signup_bp',
    'subscribe_bp',
    'public_bp',
    'sponsors_bp',
    'brave_review_bp',
    'og_bp',
]

# Local-only blueprints - conditionally imported
# These require Gmail OAuth and Playwright
try:
    from routes.review_emails import review_emails_bp
    __all__.append('review_emails_bp')
except ImportError:
    # Expected in ECS - review_emails blueprint isn't needed there
    review_emails_bp = None
