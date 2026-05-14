"""
Brave Review Forms - CSRF-protected forms for reviewing low-confidence Brave search results.
"""
from flask_wtf import FlaskForm
from wtforms import HiddenField


class BraveReviewActionForm(FlaskForm):
    """Form for approve/reject actions on Brave search results."""
    item_id = HiddenField('item_id')
