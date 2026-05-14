"""
UI Strings Configuration

Centralized UI strings for consistency and i18n-readiness.
All user-facing text that appears in multiple places should be defined here.

SOLID Principle: Single source of truth for UI text.
"""

UI_STRINGS = {
    # Empty states
    'not_set': 'Not set',
    'uncategorized': 'Uncategorized',
    'no_data': 'No data available',
    'no_results': 'No results found',
    'no_items': 'No items yet',
    'loading': 'Loading...',

    # Actions
    'save': 'Save',
    'cancel': 'Cancel',
    'delete': 'Delete',
    'edit': 'Edit',
    'add': 'Add',
    'create': 'Create',
    'update': 'Update',
    'submit': 'Submit',
    'close': 'Close',
    'retry': 'Try Again',
    'clear': 'Clear',
    'search': 'Search',

    # Confirmations
    'confirm_delete': 'Are you sure you want to delete this?',
    'confirm_action': 'Are you sure?',
    'unsaved_changes': 'You have unsaved changes. Are you sure you want to leave?',

    # Status
    'success': 'Success',
    'error': 'Error',
    'warning': 'Warning',
    'info': 'Info',

    # Pagination
    'previous': 'Previous',
    'next': 'Next',
    'page_of': 'Page {current} of {total}',

    # Filters
    'all': 'All',
    'filter_by': 'Filter by',
    'sort_by': 'Sort by',
    'clear_filters': 'Clear all filters',

    # Hints
    'search_hint': 'Try adjusting your search or filters',
    'required_field': 'This field is required',
}


def get_string(key: str, **kwargs) -> str:
    """
    Get a UI string by key, with optional format arguments.

    Args:
        key: The string key from UI_STRINGS
        **kwargs: Format arguments for string interpolation

    Returns:
        The formatted string, or the key itself if not found

    Example:
        get_string('page_of', current=1, total=10)
        # Returns: 'Page 1 of 10'
    """
    text = UI_STRINGS.get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except KeyError:
            return text
    return text
