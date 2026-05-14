"""
Platform display configuration for IR platforms.
Centralizes labels and colors for consistent UI rendering.
"""

# Platform display configuration: (label, color)
PLATFORM_LABELS = {
    'rss': ('RSS', '#28a745'),
    'q4_drupal': ('Q4 / Drupal', '#0066cc'),
    'q4_js': ('Q4 (JS)', '#fd7e14'),
    'q4_detail': ('Q4 Detail', '#0066cc'),
    'q4_pdf': ('Q4 PDF', '#0066cc'),
    'businesswire': ('Business Wire', '#6f42c1'),
    'globenewswire': ('Globe Newswire', '#6f42c1'),
    'prnewswire': ('PR Newswire', '#6f42c1'),
    'accesswire': ('Access Wire', '#6f42c1'),
    'gcs': ('GCS', '#17a2b8'),
    'gcs_with_dates': ('GCS (dates)', '#17a2b8'),
    'investis': ('Investis', '#6c757d'),
    'apollo_accordion': ('Apollo', '#6c757d'),
    'date_slug': ('Date Slug', '#6c757d'),
    'welltower': ('Welltower', '#6c757d'),
    'olp_pdf': ('OLP PDF', '#6c757d'),
    'wordpress_pdf': ('WordPress', '#6c757d'),
    'custom': ('Custom', '#6c757d'),
}

# Default for unknown platforms
DEFAULT_PLATFORM = ('Unknown', '#6c757d')


def get_platform_display(platform_key):
    """
    Get display label and color for a platform.

    Args:
        platform_key: Platform identifier (e.g., 'q4_drupal')

    Returns:
        tuple: (label, color) for display
    """
    return PLATFORM_LABELS.get(platform_key, DEFAULT_PLATFORM)
