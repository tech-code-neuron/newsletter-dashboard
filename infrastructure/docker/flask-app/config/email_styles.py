"""
Email Styles - Inline CSS for HTML Emails

AUTO-GENERATED - DO NOT EDIT DIRECTLY
Generated from: config/design-tokens.json
Generated at: 2026-03-29 22:14:13

To modify these values, edit config/design-tokens.json
then run: python3 scripts/build_design_tokens.py

Usage:
    from config.email_styles import EMAIL_STYLES
    style = EMAIL_STYLES["colors"]["primary"]
"""

# Raw token values for use in inline styles
EMAIL_STYLES = {
    'color': {
        'primary': '#0066cc',
        'primary_hover': '#0052a3',
        'primary_light': '#e8f0fe',
        'success': '#28a745',
        'success_hover': '#218838',
        'success_bg': '#d4edda',
        'success_border': '#c3e6cb',
        'success_text': '#155724',
        'danger': '#dc3545',
        'danger_hover': '#c82333',
        'danger_bg': '#f8d7da',
        'danger_border': '#f5c6cb',
        'danger_text': '#721c24',
        'warning': '#ffc107',
        'warning_hover': '#e0a800',
        'warning_bg': '#fff3cd',
        'warning_bg_hover': '#ffe0b2',
        'warning_border': '#ffeaa7',
        'warning_text': '#856404',
        'warning_dark': '#bf360c',
        'info': '#17a2b8',
        'info_hover': '#138496',
        'info_bg': '#d1ecf1',
        'info_border': '#bee5eb',
        'info_text': '#0c5460',
        'secondary': '#6c757d',
        'secondary_hover': '#545b62',
        'secondary_bg': '#e2e3e5',
        'secondary_text': '#6c757d',
        'sec_purple': '#6f42c1',
        'sec_bg': '#e8dcf5',
        'sec_border': '#d8c8e8',
        'breaking': '#ff6b6b',
        'text': '#333333',
        'text_dark': '#1a1a1a',
        'text_muted': '#666666',
        'text_light': '#999999',
        'text_tertiary': '#aaaaaa',
        'bg': '#f5f5f5',
        'bg_white': '#ffffff',
        'bg_card': '#ffffff',
        'bg_hover': '#f8f9fa',
        'bg_hover_alt': '#f0f8ff',
        'bg_subtle': '#e9ecef',
        'bg_section': '#fafafa',
        'border': '#dee2e6',
        'border_light': '#ced4da',
        'border_dark': '#0066cc',
    },
    'spacing': {
        'xs': '0.25rem',
        'sm': '0.5rem',
        'md': '1rem',
        'lg': '1.5rem',
        'xl': '2rem',
        '2xl': '3rem',
    },
    'spacing_mobile': {
        'sm': '0.5rem',
        'md': '1rem',
        'lg': '1.5rem',
    },
    'spacing_touch': {
        'target_min': '44px',
        'target_small': '40px',
        'sm': '10px',
        'md': '12px',
    },
    'typography': {
        'font_base': 'Arial, Helvetica, sans-serif',
        'font_body': 'Georgia, \'Times New Roman\', Times, serif',
        'font_ui': '-apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, \'Helvetica Neue\', Arial, sans-serif',
        'font_mono': 'monospace',
        'size_xs': '0.75rem',
        'size_sm': '0.85rem',
        'size_base': '1rem',
        'size_md': '1.125rem',
        'size_lg': '1.5rem',
        'size_xl': '2rem',
        'size_2xl': '2.5rem',
        'weight_normal': '400',
        'weight_medium': '500',
        'weight_semibold': '600',
        'weight_bold': '700',
        'line_height_base': '1.6',
    },
    'typography_mobile': {
        'size_xs': '0.75rem',
        'size_sm': '0.8125rem',
        'size_base': '0.875rem',
        'size_md': '1rem',
        'size_lg': '1.25rem',
        'size_xl': '1.75rem',
    },
    'sizing': {
        'width_xs': '40px',
        'width_sm': '70px',
        'width_md': '80px',
        'width_lg': '90px',
        'width_xl': '120px',
        'width_2xl': '130px',
        'width_3xl': '150px',
        'width_container': '1200px',
        'width_form_narrow': '600px',
        'width_screenshot_preview': '600px',
        'width_modal': '1000px',
        'height_modal': '90vh',
        'height_screenshot_preview': '80vh',
    },
    'border': {
        'radius_sm': '3px',
        'radius_md': '4px',
        'radius_lg': '8px',
        'radius_xl': '12px',
        'radius_circle': '50%',
        'width_thin': '1px',
        'width_medium': '2px',
    },
    'shadow': {
        'sm': '0 2px 4px rgba(0, 0, 0, 0.1)',
        'md': '0 4px 12px rgba(0, 0, 0, 0.15)',
        'lg': '0 4px 20px rgba(0, 0, 0, 0.3)',
        'xl': '0 4px 40px rgba(0, 0, 0, 0.5)',
        'focus': '0 0 0 3px rgba(0, 102, 204, 0.1)',
    },
    'z_index': {
        'base': '1',
        'dropdown': '100',
        'sticky': '200',
        'fixed': '300',
        'modal_backdrop': '1000',
        'modal': '2000',
        'popover': '3000',
        'tooltip': '4000',
    },
    'transition': {
        'fast': '0.15s ease',
        'base': '0.2s ease',
        'slow': '0.3s ease',
    },
    'opacity': {
        'disabled': '0.5',
        'muted': '0.7',
        'hover': '0.9',
        'faint': '0.3',
    },
    'breakpoint': {
        'tablet': '768px',
        'desktop': '1024px',
        'large': '1440px',
    },
}


# Convenience accessors
def get_color(name: str) -> str:
    """Get a color value by name (use underscores, e.g., 'primary_hover')."""
    return EMAIL_STYLES['color'].get(name, EMAIL_STYLES['color']['text'])


def get_spacing(name: str) -> str:
    """Get a spacing value by name."""
    return EMAIL_STYLES['spacing'].get(name, EMAIL_STYLES['spacing']['md'])


def get_font(name: str) -> str:
    """Get a typography value by name."""
    return EMAIL_STYLES['typography'].get(name, '')


# Pre-built inline style strings for common email elements
INLINE_STYLES = {
    'body': f"font-family: {EMAIL_STYLES['typography']['font_ui']}; color: {EMAIL_STYLES['color']['text']}; background-color: {EMAIL_STYLES['color']['bg']}; line-height: {EMAIL_STYLES['typography']['line_height_base']};",
    'heading': f"font-family: {EMAIL_STYLES['typography']['font_ui']}; color: {EMAIL_STYLES['color']['text_dark']}; font-weight: {EMAIL_STYLES['typography']['weight_bold']};",
    'link': f"color: {EMAIL_STYLES['color']['primary']}; text-decoration: none;",
    'muted': f"color: {EMAIL_STYLES['color']['text_muted']}; font-size: {EMAIL_STYLES['typography']['size_sm']};",
    'card': f"background-color: {EMAIL_STYLES['color']['bg_card']}; border: 1px solid {EMAIL_STYLES['color']['border']}; border-radius: {EMAIL_STYLES['border']['radius_md']}; padding: {EMAIL_STYLES['spacing']['md']};",
    'button_primary': f"background-color: {EMAIL_STYLES['color']['primary']}; color: #ffffff; padding: {EMAIL_STYLES['spacing']['sm']} {EMAIL_STYLES['spacing']['md']}; border-radius: {EMAIL_STYLES['border']['radius_md']}; text-decoration: none; display: inline-block;",
    'button_success': f"background-color: {EMAIL_STYLES['color']['success']}; color: #ffffff; padding: {EMAIL_STYLES['spacing']['sm']} {EMAIL_STYLES['spacing']['md']}; border-radius: {EMAIL_STYLES['border']['radius_md']}; text-decoration: none; display: inline-block;",
    'alert_success': f"background-color: {EMAIL_STYLES['color']['success_bg']}; border: 1px solid {EMAIL_STYLES['color']['success_border']}; color: {EMAIL_STYLES['color']['success_text']}; padding: {EMAIL_STYLES['spacing']['md']}; border-radius: {EMAIL_STYLES['border']['radius_md']};",
    'alert_warning': f"background-color: {EMAIL_STYLES['color']['warning_bg']}; border: 1px solid {EMAIL_STYLES['color']['warning_border']}; color: {EMAIL_STYLES['color']['warning_text']}; padding: {EMAIL_STYLES['spacing']['md']}; border-radius: {EMAIL_STYLES['border']['radius_md']};",
    'alert_danger': f"background-color: {EMAIL_STYLES['color']['danger_bg']}; border: 1px solid {EMAIL_STYLES['color']['danger_border']}; color: {EMAIL_STYLES['color']['danger_text']}; padding: {EMAIL_STYLES['spacing']['md']}; border-radius: {EMAIL_STYLES['border']['radius_md']};",
}
