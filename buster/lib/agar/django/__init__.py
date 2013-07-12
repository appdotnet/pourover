"""The ``agar.django`` package contains a number of general purpose utility modules containing classes, functions, and
decorators to help develop with `Google App Engine python`_ and `django`_."""

import logging

from agar.config import Config

class DjangoConfig(Config):
    """
    :py:class:`~agar.config.Config` settings for the ``agar.django`` library.
    Settings are under the ``agar_django`` namespace.

    The following settings (and defaults) are provided::
    
        agar_django_LOG_SERVICE_VALIDATION_ERRORS = logging.NOTSET
        agar_django_LOG_SERVICE_VALIDATION_VALUES = False

    To override ``agar.django`` settings, define values in the ``appengine_config.py`` file in the root of your app.
    """
    _prefix = 'agar_django'

    #: The global logging level for api service validation errors (Default: ``logging.NOTSET``)
    LOG_SERVICE_VALIDATION_ERRORS = logging.NOTSET
    #: True if raw values should be logged for fields with validation errors (Default: ``False``)
    LOG_SERVICE_VALIDATION_VALUES = False

#: The configuration object for ``agar.django`` settings.
config = DjangoConfig.get_config()
