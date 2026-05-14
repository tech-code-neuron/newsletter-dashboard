"""
Company Forms using Flask-WTF

These forms replace manual form handling with Flask-WTF for better
validation, error handling, and UX.

Benefits:
- Automatic URL validation for IR/press release URLs
- Conditional validation (newswire "Other" field)
- Shared validation between Add/Edit via inheritance
- Field-level error messages
"""
from flask_wtf import FlaskForm
from wtforms import (
    StringField, TextAreaField,
    SelectField, HiddenField
)
from wtforms.validators import DataRequired, URL, Length, ValidationError, Optional
from .fields import HtmlBooleanField


class CompanyForm(FlaskForm):
    """
    Base company form with shared validation logic.

    Both Add and Edit forms inherit from this to share validation rules.
    """
    name = StringField(
        'Company Name',
        validators=[
            DataRequired(message='Company name is required'),
            Length(max=255, message='Company name must be under 255 characters')
        ],
        render_kw={'placeholder': 'e.g., American Tower Corporation'}
    )

    sector = SelectField(
        'Sector',
        validators=[Optional()],
        choices=[],  # Populated dynamically in route
        render_kw={'placeholder': 'Select Sector'}
    )

    ir_url = StringField(
        'Investor Relations URL',
        validators=[
            Optional(),
            URL(message='Must be a valid URL (include https://)')
        ],
        render_kw={
            'placeholder': 'https://investors.company.com',
            'type': 'url'
        }
    )

    press_release_url = StringField(
        'Press Release Page URL',
        validators=[
            Optional(),
            URL(message='Must be a valid URL (include https://)')
        ],
        render_kw={
            'placeholder': 'https://investors.company.com/press-releases',
            'type': 'url'
        }
    )

    company_rss_feed_url = StringField(
        'Company RSS Feed URL',
        validators=[
            Optional(),
            URL(message='Must be a valid URL (include https://)')
        ],
        render_kw={
            'placeholder': 'https://investors.company.com/rss',
            'type': 'url'
        }
    )

    rss_feed_url = StringField(
        'Wire Service RSS Feed URL',
        validators=[
            Optional(),
            URL(message='Must be a valid URL (include https://)')
        ],
        render_kw={
            'placeholder': 'https://www.globenewswire.com/...',
            'type': 'url'
        }
    )

    ir_platform = SelectField(
        'IR Platform',
        validators=[Optional()],
        choices=[],  # Populated dynamically in route (grouped options)
        render_kw={'id': 'ir_platform'}
    )

    scraper_variant = SelectField(
        'Scraper Variant',
        validators=[Optional()],
        choices=[
            ('', 'Default (use IR platform scraper)'),
            ('gcs', 'GCS'),
            ('gcs_with_dates', 'GCS with Dates'),
            ('wordpress_pdf', 'WordPress PDF')
        ],
        render_kw={'id': 'scraper_variant'}
    )

    newswire_provider = SelectField(
        'Newswire Provider',
        validators=[Optional()],
        choices=[
            ('', 'Not configured'),
            ('GlobeNewswire', 'GlobeNewswire'),
            ('Business Wire', 'Business Wire'),
            ('PR Newswire', 'PR Newswire'),
            ('Other', 'Other (specify below)')
        ],
        render_kw={
            'id': 'newswire_provider',
            'onchange': 'toggleCustomProvider()'
        }
    )

    custom_provider = StringField(
        'Custom Provider Name',
        validators=[Optional()],
        render_kw={
            'id': 'custom_provider',
            'placeholder': 'Enter custom provider name'
        }
    )

    newswire_id = StringField(
        'Newswire Organization ID',
        validators=[Optional()],
        render_kw={
            'id': 'newswire_id',
            'placeholder': 'e.g., 34254'
        }
    )

    active = HtmlBooleanField(
        'Active (include in scraping)',
        default=True,
        render_kw={'id': 'active'}
    )

    is_public = SelectField(
        'Company Type',
        validators=[DataRequired(message='Company type is required')],
        choices=[
            ('true', 'Public (traded on exchange)'),
            ('false', 'Private (not publicly traded)')
        ],
        default='true',
        render_kw={'id': 'is_public'}
    )

    # Sponsor fields (for private companies)
    # Uses datalist for autocomplete from canonical sponsor list
    lead_sponsor = StringField(
        'Lead Sponsor',
        validators=[Optional(), Length(max=100)],
        render_kw={
            'id': 'lead_sponsor',
            'placeholder': 'e.g., Blackstone, KKR, Apollo',
            'list': 'sponsor-datalist',
            'class': 'sponsor-autocomplete'
        }
    )

    second_sponsor = StringField(
        'Second Sponsor',
        validators=[Optional(), Length(max=100)],
        render_kw={
            'id': 'second_sponsor',
            'placeholder': 'For joint acquisitions',
            'list': 'sponsor-datalist',
            'class': 'sponsor-autocomplete'
        }
    )

    # Playwright scraper fields (conditional - required if ir_platform = 'playwright_scraper')
    playwright_url = StringField(
        'Playwright URL',
        validators=[Optional(), URL(message='Must be a valid URL')],
        render_kw={
            'placeholder': 'https://investors.company.com/press-releases',
            'type': 'url',
            'id': 'playwright_url'
        }
    )

    playwright_selector = StringField(
        'Playwright CSS Selector',
        validators=[Optional()],
        render_kw={
            'placeholder': '.press-release-item',
            'id': 'playwright_selector'
        }
    )

    playwright_wait_for = SelectField(
        'Playwright Wait Condition',
        validators=[Optional()],
        choices=[
            ('', 'Not configured'),
            ('selector', 'Selector'),
            ('networkidle', 'Network Idle'),
            ('load', 'Page Load')
        ],
        render_kw={'id': 'playwright_wait_for'}
    )

    # SEC EDGAR fields
    cik = StringField(
        'SEC CIK',
        validators=[
            Optional(),
            Length(max=10, message='CIK must be 10 digits or less')
        ],
        render_kw={
            'id': 'cik',
            'placeholder': '0001234567',
            'pattern': '[0-9]*',
            'maxlength': '10'
        }
    )

    op_cik = StringField(
        'Operating Partnership CIK',
        validators=[
            Optional(),
            Length(max=10, message='CIK must be 10 digits or less')
        ],
        render_kw={
            'id': 'op_cik',
            'placeholder': '0001234567 (if OP files separately)',
            'pattern': '[0-9]*',
            'maxlength': '10'
        }
    )

    op_name = StringField(
        'Operating Partnership Name',
        validators=[
            Optional(),
            Length(max=200, message='OP name must be under 200 characters')
        ],
        render_kw={
            'id': 'op_name',
            'placeholder': 'e.g., Simon Property Group, L.P.'
        }
    )

    op_has_unique_filings = HtmlBooleanField(
        'OP has unique SEC filings',
        default=False,
        render_kw={'id': 'op_has_unique_filings'}
    )

    def validate_custom_provider(self, field):
        """
        Conditional validation: If newswire_provider is "Other",
        custom_provider must be provided.
        """
        if self.newswire_provider.data == 'Other':
            if not field.data or not field.data.strip():
                raise ValidationError(
                    'Custom provider name is required when "Other" is selected'
                )

    def validate_playwright_url(self, field):
        """
        Conditional validation: If ir_platform is 'playwright_scraper',
        playwright_url must be provided.
        """
        if self.ir_platform.data == 'playwright_scraper':
            if not field.data or not field.data.strip():
                raise ValidationError(
                    'Playwright URL is required when using Playwright scraper'
                )

    def validate_playwright_selector(self, field):
        """
        Conditional validation: If ir_platform is 'playwright_scraper',
        playwright_selector must be provided.
        """
        if self.ir_platform.data == 'playwright_scraper':
            if not field.data or not field.data.strip():
                raise ValidationError(
                    'Playwright selector is required when using Playwright scraper'
                )

    def validate_playwright_wait_for(self, field):
        """
        Conditional validation: If ir_platform is 'playwright_scraper',
        playwright_wait_for must be provided.
        """
        if self.ir_platform.data == 'playwright_scraper':
            if not field.data or not field.data.strip():
                raise ValidationError(
                    'Playwright wait condition is required when using Playwright scraper'
                )


class AddCompanyForm(CompanyForm):
    """
    Form for adding a new company.

    Extends CompanyForm with ticker field (required, uppercase, unique).
    """
    ticker = StringField(
        'Ticker Symbol',
        validators=[
            DataRequired(message='Ticker symbol is required'),
            Length(min=1, max=10, message='Ticker must be 1-10 characters')
        ],
        render_kw={
            'id': 'ticker',
            'placeholder': 'e.g., AMT, DLR, PLD',
            'style': 'text-transform: uppercase;',
            'maxlength': '10'
        }
    )

    def validate_ticker(self, field):
        """
        Custom validator: Ticker must be uppercase and alphanumeric.

        Note: Uniqueness check is done in the route (requires database access).
        """
        if field.data:
            ticker = field.data.strip().upper()
            if not ticker.isalnum():
                raise ValidationError('Ticker must contain only letters and numbers')
            # Update field data to uppercase
            field.data = ticker


class EditCompanyForm(CompanyForm):
    """
    Form for editing an existing company.

    Ticker is now editable (user requested).
    """
    ticker = StringField(
        'Ticker Symbol',
        validators=[
            DataRequired(message='Ticker symbol is required'),
            Length(min=1, max=10, message='Ticker must be 1-10 characters')
        ],
        render_kw={
            'id': 'ticker',
            'style': 'text-transform: uppercase;',
            'maxlength': '10'
        }
    )

    def validate_ticker(self, field):
        """Ticker must be uppercase and alphanumeric."""
        if field.data:
            ticker = field.data.strip().upper()
            if not ticker.isalnum():
                raise ValidationError('Ticker must contain only letters and numbers')
            field.data = ticker
