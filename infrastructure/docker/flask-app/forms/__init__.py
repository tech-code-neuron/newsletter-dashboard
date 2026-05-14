"""
Flask-WTF Forms Module

This module contains all Flask-WTF form definitions for the application.
Forms centralize validation logic and provide better UX through automatic
field-level error handling.

Migration Status:
- ✅ Press Release Forms (add, edit)
- ✅ Company Forms (add, edit) - Phase 2 Complete
"""
from .press_release_forms import AddPressReleaseForm, EditPressReleaseForm
from .company_forms import AddCompanyForm, EditCompanyForm
from .fields import HtmlBooleanField

__all__ = [
    'AddPressReleaseForm',
    'EditPressReleaseForm',
    'AddCompanyForm',
    'EditCompanyForm',
    'HtmlBooleanField'
]
