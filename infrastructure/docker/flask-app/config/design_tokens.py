"""
Design System Tokens - Single Source of Truth

All visual values flow from here to CSS and templates.
Change theme by modifying these values, not individual styles.

SOLID Principle: Single Responsibility - this module owns all design tokens.
"""

# =============================================================================
# COLORS
# =============================================================================

COLORS = {
    # Brand
    'primary': '#0066cc',
    'primary_hover': '#0052a3',
    'primary_light': '#e8f0fe',

    # Semantic - Success
    'success': '#28a745',
    'success_hover': '#218838',
    'success_bg': '#d4edda',
    'success_border': '#c3e6cb',
    'success_text': '#155724',

    # Semantic - Danger
    'danger': '#dc3545',
    'danger_hover': '#c82333',
    'danger_bg': '#f8d7da',
    'danger_border': '#f5c6cb',
    'danger_text': '#721c24',

    # Semantic - Warning
    'warning': '#ffc107',
    'warning_hover': '#e0a800',
    'warning_bg': '#fff3cd',
    'warning_border': '#ffeaa7',
    'warning_text': '#856404',

    # Semantic - Info
    'info': '#17a2b8',
    'info_hover': '#138496',
    'info_bg': '#cce5ff',
    'info_border': '#bee5eb',
    'info_text': '#004085',

    # Secondary
    'secondary': '#6c757d',
    'secondary_hover': '#545b62',
    'secondary_bg': '#e2e3e5',
    'secondary_text': '#6c757d',

    # Special
    'breaking': '#ff6b6b',
    'sec_purple': '#6f42c1',
    'sec_bg': '#e8dcf5',

    # Text
    'text': '#333333',
    'text_dark': '#1a1a1a',
    'text_muted': '#666666',
    'text_light': '#999999',

    # Backgrounds
    'bg': '#f5f5f5',
    'bg_white': '#ffffff',
    'bg_card': '#ffffff',
    'bg_hover': '#f8f9fa',
    'bg_hover_alt': '#f0f8ff',
    'bg_info_light': '#f0f5ff',

    # Borders
    'border': '#dee2e6',
    'border_light': '#ced4da',
    'border_dark': '#0066cc',
    'border_info': '#cce0ff',

    # Email-specific borders (match your-domain.com website)
    'border_section': '#e5e5e5',   # Section header underlines
    'border_item': '#f0f0f0',      # Item row separators
    'border_footer': '#cccccc',    # Footer separator
}


# =============================================================================
# SPACING
# =============================================================================

SPACING = {
    'xs': '0.25rem',   # 4px
    'sm': '0.5rem',    # 8px
    'md': '1rem',      # 16px
    'lg': '1.5rem',    # 24px
    'xl': '2rem',      # 32px
    '2xl': '3rem',     # 48px
}

SPACING_MOBILE = {
    'sm': '0.5rem',    # 8px
    'md': '1rem',      # 16px
    'lg': '1.5rem',    # 24px
}

SPACING_TOUCH = {
    'target_min': '44px',
    'target_small': '40px',
    'sm': '10px',
    'md': '12px',
}


# =============================================================================
# TYPOGRAPHY
# =============================================================================

TYPOGRAPHY = {
    # Font families
    'font_body': 'Georgia, "Times New Roman", Times, serif',
    'font_heading': '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
    'font_mono': 'monospace',
    'ui': 'Arial, Helvetica, sans-serif',  # UI elements (section headers, tickers, footer links)

    # Font sizes
    'size_xs': '0.75rem',     # 12px
    'size_sm': '0.875rem',    # 14px
    'size_base': '1rem',      # 16px
    'size_md': '1.125rem',    # 18px
    'size_lg': '1.25rem',     # 20px
    'size_xl': '1.5rem',      # 24px
    'size_2xl': '2rem',       # 32px

    # Font weights
    'weight_normal': '400',
    'weight_medium': '500',
    'weight_semibold': '600',
    'weight_bold': '700',

    # Line height
    'line_height_base': '1.6',
}

TYPOGRAPHY_MOBILE = {
    'size_xs': '0.75rem',      # 12px
    'size_sm': '0.8125rem',    # 13px
    'size_base': '0.875rem',   # 14px
    'size_md': '1rem',         # 16px
    'size_lg': '1.25rem',      # 20px
    'size_xl': '1.75rem',      # 28px
}


# =============================================================================
# BORDERS
# =============================================================================

BORDERS = {
    'radius_sm': '3px',
    'radius_md': '4px',
    'radius_lg': '8px',
    'radius_xl': '12px',
    'radius_circle': '50%',

    'width_thin': '1px',
    'width_medium': '2px',
}


# =============================================================================
# SHADOWS
# =============================================================================

SHADOWS = {
    'sm': '0 2px 4px rgba(0, 0, 0, 0.1)',
    'md': '0 4px 12px rgba(0, 0, 0, 0.15)',
    'lg': '0 4px 20px rgba(0, 0, 0, 0.3)',
    'xl': '0 4px 40px rgba(0, 0, 0, 0.5)',
}


# =============================================================================
# Z-INDEX LAYERS
# =============================================================================

Z_INDEX = {
    'base': 1,
    'dropdown': 100,
    'sticky': 200,
    'fixed': 300,
    'modal_backdrop': 1000,
    'modal': 2000,
    'popover': 3000,
    'tooltip': 4000,
}


# =============================================================================
# TRANSITIONS
# =============================================================================

TRANSITIONS = {
    'fast': '0.15s ease',
    'base': '0.2s ease',
    'slow': '0.3s ease',
}


# =============================================================================
# OPACITY
# =============================================================================

OPACITY = {
    'disabled': 0.5,
    'muted': 0.7,
    'hover': 0.9,
    'faint': 0.3,
}


# =============================================================================
# BREAKPOINTS
# =============================================================================

BREAKPOINTS = {
    'tablet': '768px',
    'desktop': '1024px',
    'large': '1440px',
}


# =============================================================================
# WIDTHS
# =============================================================================

WIDTHS = {
    'container': '1200px',
    'form_narrow': '600px',
    'modal': '1000px',
    'screenshot_preview': '600px',
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_color(name: str) -> str:
    """Get a color value by name."""
    return COLORS.get(name, COLORS['text'])


def get_font(name: str) -> str:
    """Get a typography value by name (e.g., 'font_body', 'size_base')."""
    return TYPOGRAPHY.get(name, TYPOGRAPHY.get('font_body', ''))


def get_spacing(name: str) -> str:
    """Get a spacing value by name."""
    return SPACING.get(name, SPACING['md'])


def get_all_tokens() -> dict:
    """Get all design tokens as a single dictionary for template context."""
    return {
        'colors': COLORS,
        'spacing': SPACING,
        'typography': TYPOGRAPHY,
        'borders': BORDERS,
        'shadows': SHADOWS,
        'z_index': Z_INDEX,
        'transitions': TRANSITIONS,
    }
