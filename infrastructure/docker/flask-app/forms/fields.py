"""
Custom WTForms fields for Flask-WTF.
"""
from wtforms import BooleanField
from wtforms.utils import unset_value


class HtmlBooleanField(BooleanField):
    """
    BooleanField that correctly handles unchecked checkboxes when obj= is used.

    Problem: HTML checkboxes don't send any value when unchecked. WTForms
    only calls process_formdata() when the field IS in formdata. So when
    using obj= with an existing object, unchecking leaves the original value.

    Solution: When formdata is present but the field is absent, set data=False.
    """
    def process(self, formdata, data=unset_value, extra_filters=None):
        if formdata is not None and self.name not in formdata:
            self.data = False
            return
        super().process(formdata, data, extra_filters)
