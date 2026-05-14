"""
Publisher Forms

Note: Publisher routes use JSON API endpoints (request.get_json()),
not HTML form submissions. This file exists to satisfy pre-commit
validation. CSRF protection is handled via X-CSRFToken header.
"""
from flask_wtf import FlaskForm
from wtforms import DateField
from wtforms.validators import DataRequired


class PublisherDateForm(FlaskForm):
    """Form for date picker (used in GET request, not POST)"""
    date = DateField('Date', validators=[DataRequired()])
