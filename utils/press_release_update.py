"""
Press release update logic (DRY)
Extracted from app.py to eliminate 100+ lines of duplication
"""
from flask import request, flash
from utils.datetime_utils import parse_edit_form_datetime
from utils.review_constants import MAX_PRESS_RELEASE_WORDS


def update_press_release_from_form(release, regenerate_slug=False):
    """
    Update press release from form data (Single Responsibility)

    Args:
        release: PressRelease object to update
        regenerate_slug: Whether to regenerate slug if title changes

    Returns:
        tuple: (success: bool, new_slug: str or None, error_message: str or None)

    Example:
        success, new_slug, error = update_press_release_from_form(release, regenerate_slug=True)
        if not success:
            flash(error, 'error')
            return redirect(...)
    """
    # Update basic fields
    release.title = request.form.get('title', '').strip()
    release.url = request.form.get('url', '').strip()
    release.category = request.form.get('category')
    release.summary = request.form.get('summary')
    release.included_in_newsletter = request.form.get('included_in_newsletter') == 'on'
    release.editor_notes = request.form.get('editor_notes')
    release.manually_edited = True

    # Update full text with word limit
    full_text = request.form.get('full_text', '').strip()
    if full_text:
        words = full_text.split()
        if len(words) > MAX_PRESS_RELEASE_WORDS:
            full_text = ' '.join(words[:MAX_PRESS_RELEASE_WORDS]) + '...'
        release.full_text = full_text

    # Update date and time
    date_str = request.form.get('date')
    time_str = request.form.get('time')

    if date_str and time_str:
        try:
            release.published_date = parse_edit_form_datetime(date_str, time_str)
        except ValueError as e:
            return False, None, f'Invalid date/time format: {e}'

    # Regenerate slug if requested and title changed
    new_slug = None
    if regenerate_slug:
        new_slug = release.generate_slug()

    return True, new_slug, None
