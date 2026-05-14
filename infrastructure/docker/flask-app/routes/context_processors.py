"""
Flask context processors - Auto-inject common template variables
Shared across all blueprints
"""
from datetime import datetime
from flask import session
from config.platform_config import PLATFORM_LABELS
from config.navigation import get_navigation_items
from config.aws_config import aws_config
from config.site_config import get_public_config
from config.ui_strings import UI_STRINGS


def inject_common_context():
    """
    Auto-inject commonly-used template variables into all templates.
    Eliminates need to manually pass these to every render_template() call.

    Returns:
        dict: Variables to inject into all template contexts

    Variables:
        - platform_labels: Platform display labels
        - current_year: Current year for copyright
        - nav_items: Navigation menu items
        - is_ecs: True if running in ECS (hides local-only features)
        - view_mode: User's preferred view mode ('auto', 'desktop', 'mobile')
        - config: Site configuration (name, footer, etc.)
        - ui: UI strings for consistency and i18n-readiness
    """
    return {
        'platform_labels': PLATFORM_LABELS,
        'current_year': datetime.now().year,
        'nav_items': get_navigation_items(),
        'is_ecs': aws_config.is_ecs,
        'view_mode': session.get('view_mode', 'auto'),
        'config': get_public_config(),
        'ui': UI_STRINGS,
    }
