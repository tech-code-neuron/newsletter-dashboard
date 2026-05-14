"""
Social Forms - Flask-WTF Forms for Social Media Pipeline
"""
from flask_wtf import FlaskForm


class SocialToggleForm(FlaskForm):
    """
    Empty form for CSRF protection on toggle actions.

    Used for pause/resume buttons that don't require additional input.
    """
    pass
