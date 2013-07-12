"""
The ``agar.django.decorators`` module contains functions and decorators to help validate `django forms`_,
to be used to wrap :py:class:`agar.json.JsonRequestHandler` methods that accept input.
"""
import logging
from functools import wraps

from agar.auth import config as agar_auth_config
from agar.django import config

def create_error_dict(error_list):
    from django.forms.util import ErrorList
    text_errors = {}
    for key, value in error_list.items():
        if isinstance(value, ErrorList):
            text_errors[key] = value.as_text()
        else:
            text_errors[key] = value
    return text_errors

def validate_service(form_class,
    pass_handler=False,
    log_errors=config.LOG_SERVICE_VALIDATION_ERRORS,
    log_values=config.LOG_SERVICE_VALIDATION_VALUES,
):
    """
    A decorator that validates input matches with a `django form class`_.

    If the form is valid with the given request parameters, the decorator will add the bound form to the request under
    the ``form`` attribute and pass control on to the wrapped handler method.

    If the form doesn't validate, it will return a well-formed JSON response with a status code of ``400`` including an
    error dictionary describing the input errors.

    :param form_class: The `django form class`_ to use for input validation.
    :param pass_handler: If `True`, the decorated handler will be passed to the form `__init__` method in the `kwargs` under the key `handler`.
    :param log_errors: The logging level for form validation errors.  Defaults to `agar_django_LOG_SERVICE_VALIDATION_ERRORS` (off).
    :param log_values: `True` if the raw request parameter values should be logged for fields with validation errors. Defaults to 
        `agar_django_LOG_SERVICE_VALIDATION_VALUE`.
    """

    def log(handler, error_dict):
        if log_errors:
            log_template = 'Invalid api call: %(errors)s'
            if hasattr(handler.request, agar_auth_config.AUTHENTICATION_PROPERTY):
                log_template = 'Invalid api call from "%(user)s": %(errors)s'
            error_template = 'field "%(field)s" has error "%(error)s"'
            if log_values:
                error_template += ' for value "%(value)s"'
            logging.log(log_errors, log_template % { 
                'errors': ' and '.join([ 
                    error_template % {'field': key, 'error': value, 'value': handler.request.params.get(key)} 
                    for key, value in error_dict.items()
                ]),
                'user': str(getattr(handler.request, agar_auth_config.AUTHENTICATION_PROPERTY, None))
            })

    def decorator(request_method):
        @wraps(request_method)
        def wrapped(handler, *args, **kwargs):
            if pass_handler:
                form = form_class(handler.request.params, handler=handler)
            else:
                form = form_class(handler.request.params)
            if form.is_valid():
                handler.request.form = form
                request_method(handler, *args, **kwargs)
                return
            else:
                error_dict = create_error_dict(form.errors)
                log(handler, error_dict)
                status_text = "BAD_REQUEST"
                handler.json_response({}, status_code=400, status_text=status_text, errors=error_dict)
                return
        return wrapped
    return decorator
