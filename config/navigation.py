"""
Navigation Configuration
Centralized navigation menu structure following SOLID principles
"""

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
]


def get_navigation_items():
    """
    Returns the navigation items for the main menu.
    Can be extended to support role-based navigation in the future.
    """
    return MAIN_NAVIGATION
