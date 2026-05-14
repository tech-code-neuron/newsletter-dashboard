"""
Form pre-population helpers following Flask-WTF best practices.

Centralizes form field population logic to prevent:
1. GET/POST bugs (accidentally overwriting submitted data on POST)
2. Code duplication across routes
"""

from flask import request
from core.title_utils import get_display_title


def populate_press_release_form(form, release):
    """
    Populate EditPressReleaseForm on GET requests only.

    On POST requests, this does nothing - letting WTForms use the submitted data.
    This prevents the bug where user edits get overwritten with old DB values.

    Args:
        form: EditPressReleaseForm instance
        release: PressReleaseDTO object
    """
    if request.method != 'GET':
        return

    form.title.data = get_display_title(release)
    if not form.url.data:
        form.url.data = release.url
