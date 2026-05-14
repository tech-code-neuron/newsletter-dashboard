"""
Single source of truth for title display logic.

All components MUST use get_display_title() instead of inline priority logic.
This prevents drift between press release, publisher, and newsletter.

Priority order (highest to lowest):
  1. display_title - Cleaned/edited title
  2. title - Original from ingestion

Usage:
    from core.title_utils import get_display_title

    # For DTOs
    title = get_display_title(release)

    # For dicts
    title = get_display_title(item_dict)

    # In Jinja templates, use the filter:
    {{ item|display_title }}
"""


def get_display_title(item) -> str:
    """
    Get the display title for any publishable item.

    Priority (highest to lowest):
      1. display_title - Cleaned/edited title
      2. title - Original from ingestion

    Args:
        item: PressReleaseDTO, DisclosureDTO, or dict with title fields

    Returns:
        The best available title string
    """
    # Handle DTO objects (PressReleaseDTO, DisclosureDTO)
    if hasattr(item, 'display_title') and item.display_title:
        return item.display_title
    if hasattr(item, 'title') and item.title:
        return item.title

    # Handle dict objects (from DynamoDB, API responses, etc.)
    if isinstance(item, dict):
        return item.get('display_title') or item.get('title', '')

    return ''
