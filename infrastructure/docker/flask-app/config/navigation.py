"""
Navigation Configuration
Centralized navigation menu structure following SOLID principles

ECS Support:
- Some navigation items (Email Review) require local-only features
- get_navigation_items() filters based on environment
"""
from config.aws_config import aws_config

# Main navigation items
# Format: (label, endpoint, icon_optional)
# NOTE: After blueprint refactoring, endpoints are blueprint_name.function_name
MAIN_NAVIGATION = [
    {
        'label': 'Dashboard',
        'endpoint': 'dashboard.index',
        'icon': None
    },
    {
        'label': 'Companies',
        'endpoint': 'companies.companies',
        'icon': None
    },
    {
        'label': 'Sponsors',
        'endpoint': 'sponsors.sponsors',
        'icon': None
    },
    {
        'label': 'Press Releases',
        'endpoint': 'press_releases.press_releases',
        'icon': None
    },
    {
        'label': 'URL Testing',
        'endpoint': 'url_testing.dashboard',
        'icon': None
    },
    {
        'label': 'Press Release Review',
        'endpoint': 'review.review',
        'icon': None
    },
    {
        'label': 'Newsletters',
        'endpoint': 'newsletters.newsletters',
        'icon': None
    },
    {
        'label': 'Publisher',
        'endpoint': 'publisher.publisher',
        'icon': None
    },
    {
        'label': 'Analytics',
        'endpoint': 'analytics.analytics_dashboard',
        'icon': None
    },
    {
        'label': '8K Disclosures',
        'endpoint': 'disclosures.disclosure_list',
        'icon': None
    },
    {
        'label': 'Email Viewer',
        'endpoint': 'emails.email_list',
        'icon': None
    },
    {
        'label': 'Site Editor',
        'endpoint': 'site_editor.index',
        'icon': None
    },
    {
        'label': 'Card Preview',
        'endpoint': 'card_preview.card_preview',
        'icon': None
    },
    {
        'label': 'Social Status',
        'endpoint': 'social_admin.social_status',
        'icon': None
    },
]

# Local-only navigation items (require SQLite, Gmail, Playwright)
LOCAL_ONLY_NAVIGATION = [
    {
        'label': 'Email Review',
        'endpoint': 'review_emails.review_emails',
        'icon': None
    },
]


def get_navigation_items():
    """
    Returns the navigation items for the main menu.
    Filters out local-only items when running in ECS.
    """
    if aws_config.is_ecs:
        return MAIN_NAVIGATION
    return MAIN_NAVIGATION + LOCAL_ONLY_NAVIGATION
