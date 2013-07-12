"""
The ``agar.django.forms`` module contains form classes to help using `django forms`_ with a `webapp2.Request`_.
"""

from webapp2 import get_request as get_webapp2_request

from django import forms


class RequestForm(forms.Form):
    """
    A `django form class`_ that holds a reference to the current `webapp2.Request`_.
    """
    def __init__(self, *args, **kwargs):
        self._request = None
        super(RequestForm, self).__init__(*args, **kwargs)

    def get_request(self):
        if self._request is None:
            self._request = get_webapp2_request()
        return self._request
    def set_request(self, request):
        self._request = request
    request = property(get_request, set_request, doc="The form's `webapp2.Request`_.")


class StrictRequestForm(RequestForm):
    """
    A :py:class:`~agar.django.forms.RequestForm` that validates all passed parameters are expected by the form.
    """
    def clean(self):
        field_keys = self.fields.keys()
        if self.request is not None:
            param_keys = self.request.params.keys()
            for key in param_keys:
                if key not in field_keys:
                    self._errors[key] = self.error_class(["Not a recognized parameter"])
        return self.cleaned_data
