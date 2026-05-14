"""
Newsletter generation for press releases
"""
from core.models import get_session, PressRelease, Newsletter, Company
from config.paths import NEWSLETTERS_DIR
from datetime import datetime, timedelta
from collections import defaultdict
import pytz
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class NewsletterGenerator:
    """Generate HTML newsletters from categorized press releases"""

    # Category display order and names
    CATEGORY_ORDER = [
        ('M&A', 'Mergers & Acquisitions'),
        ('Property Transactions', 'Property Transactions'),
        ('Equity Offerings', 'Equity & Equity-Linked Offerings'),
        ('Debt Offerings', 'Debt Offerings'),
        ('Credit Facilities', 'Credit Facilities'),
        ('Board Changes', 'Board Changes'),
        ('Personnel Changes', 'Personnel Changes'),
        ('Earnings', 'Earnings Releases'),
        ('Dividends', 'Dividend Announcements'),
        ('Conference Call', 'Earnings Calendar Announcements'),
        ('Other', 'Other News')
    ]

    # Theme configurations (SOLID: Extract constants)
    THEMES = {
        'morning': {
            'primary_color': '#0066cc',
            'heading_color': '#1a1a1a',
            'title': 'Morning Brief',
            'badge': None,
            'empty_message': 'No press releases in the past 24 hours.',
            'subtitle_singular': 'press release',
            'subtitle_plural': 'press releases'
        },
        'breaking': {
            'primary_color': '#d32f2f',
            'heading_color': '#d32f2f',
            'title': 'Breaking News',
            'badge': '9:00 AM Brief',
            'empty_message': 'No breaking announcements overnight or this morning.',
            'subtitle_singular': 'breaking announcement',
            'subtitle_plural': 'breaking announcements'
        }
    }

    def __init__(self):
        self.db_session = get_session()
    
    def get_press_releases_for_period(self, start_date, end_date, breaking_only=False):
        """
        Get press releases for a specific time period
        """
        query = self.db_session.query(PressRelease).join(Company).filter(
            PressRelease.published_date >= start_date,
            PressRelease.published_date < end_date,
            PressRelease.included_in_newsletter == True,
            Company.active == True
        )
        
        if breaking_only:
            query = query.filter(PressRelease.is_breaking == True)
        
        return query.order_by(PressRelease.published_date.desc()).all()
    
    def group_by_category(self, press_releases):
        """
        Group press releases by category in the correct order
        """
        grouped = defaultdict(list)
        
        for pr in press_releases:
            category = pr.category or 'Other'
            grouped[category].append(pr)
        
        # Return in priority order
        ordered = []
        for category_key, _ in self.CATEGORY_ORDER:
            if category_key in grouped and grouped[category_key]:
                ordered.append((category_key, grouped[category_key]))
        
        return ordered
    
    def _get_display_name(self, category):
        """
        SOLID: Single Responsibility - Get display name for category

        Args:
            category: Category key

        Returns:
            str: Display name for category
        """
        for key, display in self.CATEGORY_ORDER:
            if key == category:
                return display
        return category

    def _generate_css(self, theme_name):
        """
        SOLID: Single Responsibility - Generate CSS with theme colors

        Args:
            theme_name: 'morning' or 'breaking'

        Returns:
            str: CSS stylesheet
        """
        theme = self.THEMES[theme_name]
        primary = theme['primary_color']
        heading = theme['heading_color']

        css = f"""
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: {heading};
            border-bottom: 3px solid {primary};
            padding-bottom: 10px;
            margin-bottom: 20px;
        }}"""

        # Add breaking badge style if needed
        if theme_name == 'breaking':
            css += f"""
        .breaking-badge {{
            background-color: {primary};
            color: white;
            padding: 4px 8px;
            border-radius: 3px;
            font-size: 0.8em;
            font-weight: 600;
            text-transform: uppercase;
            margin-left: 10px;
        }}"""

        css += f"""
        h2 {{
            color: {primary};
            margin-top: 30px;
            margin-bottom: 15px;
            font-size: 1.3em;
        }}
        .release {{
            margin-bottom: 25px;
            padding-bottom: 20px;
            border-bottom: 1px solid #eee;
        }}
        .release:last-child {{
            border-bottom: none;
        }}
        .company {{
            font-weight: 600;
            color: {primary};
            font-size: 1.1em;
            margin-bottom: 5px;
        }}
        .ticker {{
            background-color: #f0f0f0;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: monospace;
            font-size: 0.9em;
            margin-left: 5px;
        }}
        .title {{
            font-weight: 500;
            color: #333;
            margin-bottom: 8px;
        }}
        .summary {{
            color: #666;
            margin-bottom: 8px;
            line-height: 1.5;
        }}
        .meta {{
            font-size: 0.9em;
            color: #999;
        }}
        .date {{
            margin-right: 15px;
        }}
        a {{
            color: {primary};
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
        .footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
            font-size: 0.9em;
            color: #666;
            text-align: center;
        }}
        .count {{
            color: #999;
            font-weight: normal;
            font-size: 0.9em;
        }}
    """
        return css

    def _build_newsletter_html(self, newsletter_type, press_releases, date):
        """
        SOLID: DRY - Single method to build newsletter HTML

        Args:
            newsletter_type: 'morning' or 'breaking'
            press_releases: List of press releases
            date: Newsletter date

        Returns:
            str: Complete HTML newsletter
        """
        theme = self.THEMES[newsletter_type]
        grouped = self.group_by_category(press_releases)

        # Build header with optional badge
        title_html = theme['title']
        if theme['badge']:
            title_html += f' <span class="breaking-badge">{theme["badge"]}</span>'

        # Count text
        count = len(press_releases)
        count_text = f"{count} {theme['subtitle_singular'] if count == 1 else theme['subtitle_plural']}"

        # Start HTML
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{theme['title']} - {date.strftime('%B %d, %Y')}</title>
    <style>
        {self._generate_css(newsletter_type)}
    </style>
</head>
<body>
    <div class="container">
        <h1>{title_html}</h1>
        <p style="color: #666; margin-bottom: 30px;">
            {date.strftime('%A, %B %d, %Y')} • {count_text}
        </p>
"""

        # Empty state
        if not grouped:
            html += f"""
        <p style="color: #999; font-style: italic;">{theme['empty_message']}</p>
"""

        # Press releases by category
        for category, releases in grouped:
            display_name = self._get_display_name(category)
            html += f"""
        <h2>{display_name} <span class="count">({len(releases)})</span></h2>
"""

            for pr in releases:
                company = pr.company
                published = pr.published_date.strftime('%b %d, %I:%M %p ET')

                html += f"""
        <div class="release" data-release-id="{pr.id}">
            <div class="company">
                {company.name}<span class="ticker">{company.ticker}</span>
            </div>
            <div class="title">{pr.title}</div>
            <div class="summary">{pr.summary or ''}</div>
            <div class="meta">
                <span class="date">{published}</span>
                <a href="{pr.url}" target="_blank">(Source)</a>
            </div>
        </div>
"""

        # Footer
        html += f"""
        <div class="footer">
            Press Release Pipeline • Generated {datetime.now().strftime('%B %d, %Y at %I:%M %p ET')}
        </div>
    </div>
</body>
</html>
"""

        return html

    def generate_html(self, newsletter_type, press_releases, date):
        """
        Generate HTML for newsletter

        SOLID: Now delegates to unified _build_newsletter_html method
        """
        return self._build_newsletter_html(newsletter_type, press_releases, date)
    
    
    def create_newsletter(self, newsletter_type='morning', date=None):
        """
        Create a newsletter for a specific date
        newsletter_type: 'morning' or 'breaking'
        date: datetime in ET timezone (defaults to now in ET)
        """
        # Get current time in ET
        et_tz = pytz.timezone('US/Eastern')
        
        if date is None:
            date = datetime.now(et_tz)
        elif date.tzinfo is None:
            # If date has no timezone, assume it's ET
            date = et_tz.localize(date)
        
        # Determine time period based on newsletter type
        if newsletter_type == 'morning':
            # Morning brief: Yesterday 12:01 AM to 11:59 PM ET
            end_date = date.replace(hour=0, minute=0, second=0, microsecond=0)  # Today midnight
            start_date = (end_date - timedelta(days=1)).replace(hour=0, minute=1)  # Yesterday 12:01 AM
            end_date = end_date - timedelta(microseconds=1)  # Yesterday 11:59:59.999999 PM
            
            subject = f"Morning Brief - {date.strftime('%B %d, %Y')}"
            
        else:  # breaking
            # Breaking brief: Today 12:01 AM to 8:00 AM ET
            start_date = date.replace(hour=0, minute=1, second=0, microsecond=0)  # Today 12:01 AM
            end_date = date.replace(hour=8, minute=0, second=0, microsecond=0)  # Today 8:00 AM
            
            subject = f"Breaking News - {date.strftime('%B %d, %Y')}"
        
        # Get press releases (convert to UTC for database query)
        press_releases = self.get_press_releases_for_period(
            start_date.astimezone(pytz.UTC).replace(tzinfo=None),
            end_date.astimezone(pytz.UTC).replace(tzinfo=None),
            breaking_only=(newsletter_type == 'breaking')
        )
        
        logger.info(f"Creating {newsletter_type} newsletter for {date.strftime('%Y-%m-%d')}")
        logger.info(f"  Time window: {start_date.strftime('%Y-%m-%d %I:%M %p %Z')} to {end_date.strftime('%Y-%m-%d %I:%M %p %Z')}")
        logger.info(f"  Found {len(press_releases)} press releases")
        
        # Generate HTML
        html_content = self.generate_html(newsletter_type, press_releases, date)
        
        # Create newsletter record
        newsletter = Newsletter(
            newsletter_type=newsletter_type,
            date=date.replace(tzinfo=None),  # Store as naive datetime
            status='draft',
            html_content=html_content,
            subject_line=subject
        )
        
        self.db_session.add(newsletter)
        self.db_session.commit()
        
        logger.info(f"  Created newsletter ID: {newsletter.id}")
        
        return newsletter
    
    def save_newsletter_to_file(self, newsletter, output_dir=NEWSLETTERS_DIR):
        """
        Save newsletter HTML to a file
        """
        import os
        
        os.makedirs(output_dir, exist_ok=True)
        
        date_str = newsletter.date.strftime('%Y-%m-%d')
        filename = f"{date_str}_{newsletter.newsletter_type}.html"
        filepath = os.path.join(output_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(newsletter.html_content)
        
        logger.info(f"  Saved to: {filepath}")
        
        return filepath
    
    def close(self):
        """Clean up resources"""
        self.db_session.close()


if __name__ == "__main__":
    generator = NewsletterGenerator()
    
    # Generate morning brief
    morning = generator.create_newsletter('morning')
    generator.save_newsletter_to_file(morning)
    
    # Generate breaking brief
    breaking = generator.create_newsletter('breaking')
    generator.save_newsletter_to_file(breaking)
    
    generator.close()
    
    print("\nNewsletters generated successfully!")
