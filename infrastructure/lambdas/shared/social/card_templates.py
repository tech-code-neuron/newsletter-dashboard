"""
Social Card Templates
=====================
Template configurations for Instagram and X (Twitter) social cards.

Templates define canvas size, colors, and element positioning.
The card_generator.py module renders these templates with Pillow.
"""

# Category display labels (uppercase for card headers)
CATEGORY_DISPLAY = {
    "m_and_a": "M&A",
    "earnings_results": "EARNINGS",
    "guidance_update": "GUIDANCE",
    "exec_change": "EXEC CHANGE",
    "dividend_change": "DIVIDEND",
    "financing": "FINANCING",
    "ratings_action": "RATINGS",
    "portfolio_strategic": "PORTFOLIO",
    "sensitive": "NEWS",
    "scheduling_call": "SCHEDULING",
    "other": "NEWS"
}

# Color palette
COLORS = {
    "background": "#0A1628",      # Dark navy background
    "headline": "#FFFFFF",         # White headline text
    "metadata": "#8FA3BC",         # Muted blue-gray for metadata
    "category": "#8FA3BC",         # Same muted color for category
}

# Font size rules based on headline length
# Each rule: max_chars, font_size, max_lines
IG_SIZE_RULES = [
    {"max_chars": 40, "size": 88, "max_lines": 3},
    {"max_chars": 80, "size": 72, "max_lines": 4},
    {"max_chars": 140, "size": 60, "max_lines": 5},
    {"max_chars": 999, "size": 52, "max_lines": 5}
]

X_SIZE_RULES = [
    {"max_chars": 40, "size": 64, "max_lines": 3},
    {"max_chars": 80, "size": 52, "max_lines": 4},
    {"max_chars": 140, "size": 44, "max_lines": 4},
    {"max_chars": 999, "size": 38, "max_lines": 4}
]

CARD_TEMPLATES = {
    "ig_portrait_default": {
        "variant_id": "ig_portrait_default",
        "canvas": {
            "width": 1080,
            "height": 1350,
            "background_color": COLORS["background"]
        },
        "elements": [
            {
                "type": "text",
                "field": "category_display",
                "x": 60,
                "y": 80,
                "font": "Inter-Medium.ttf",
                "size": 20,
                "color": COLORS["category"],
                "letter_spacing": 2,
                "transform": "uppercase"
            },
            {
                "type": "text",
                "field": "headline",
                "x": 60,
                "y": 480,
                "max_width": 960,
                "font": "PlayfairDisplay-SemiBold.ttf",
                "color": COLORS["headline"],
                "line_height": 1.15,
                "size_rules": IG_SIZE_RULES,
                "truncate_with": "..."
            },
            {
                "type": "image",
                "file": "reitsheet-wordmark.png",
                "x": 60,
                "y": 1230,
                "width": 220
            },
            {
                "type": "text",
                "field": "ticker_sector_display",
                "x_anchor": "right",
                "x_offset": 60,
                "y": 1245,
                "font": "Inter-Medium.ttf",
                "size": 22,
                "color": COLORS["metadata"],
                "letter_spacing": 1
            }
        ]
    },
    "x_summary_default": {
        "variant_id": "x_summary_default",
        "canvas": {
            "width": 1200,
            "height": 628,
            "background_color": COLORS["background"]
        },
        "elements": [
            {
                "type": "text",
                "field": "category_display",
                "x": 60,
                "y": 60,
                "font": "Inter-Medium.ttf",
                "size": 18,
                "color": COLORS["category"],
                "letter_spacing": 2,
                "transform": "uppercase"
            },
            {
                "type": "text",
                "field": "headline",
                "x": 60,
                "y": 180,
                "max_width": 1080,
                "font": "PlayfairDisplay-SemiBold.ttf",
                "color": COLORS["headline"],
                "line_height": 1.15,
                "size_rules": X_SIZE_RULES,
                "truncate_with": "..."
            },
            {
                "type": "image",
                "file": "reitsheet-wordmark.png",
                "x": 60,
                "y": 540,
                "width": 180
            },
            {
                "type": "text",
                "field": "ticker_sector_display",
                "x_anchor": "right",
                "x_offset": 60,
                "y": 555,
                "font": "Inter-Medium.ttf",
                "size": 20,
                "color": COLORS["metadata"]
            }
        ]
    }
}
