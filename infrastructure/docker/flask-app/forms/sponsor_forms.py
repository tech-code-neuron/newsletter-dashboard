"""
Sponsor Forms using Flask-WTF

Forms for sponsor management operations.
"""
from flask_wtf import FlaskForm
from wtforms import StringField
from wtforms.validators import DataRequired, Length


class RenameSponsorForm(FlaskForm):
    """Form for renaming a sponsor across all companies."""

    old_name = StringField(
        'Current Name',
        validators=[
            DataRequired(message='Current sponsor name is required'),
            Length(max=255, message='Sponsor name must be under 255 characters')
        ],
        render_kw={'readonly': True}
    )

    new_name = StringField(
        'New Name',
        validators=[
            DataRequired(message='New sponsor name is required'),
            Length(max=255, message='Sponsor name must be under 255 characters')
        ]
    )
