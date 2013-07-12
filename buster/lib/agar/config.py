"""
The ``agar.config`` module contains a class to help work with the `google.appengine.api.lib_config`_ configuration library.
"""

from google.appengine.api import lib_config


class Config(object):
    """
    Configurable constants base class for use with the excellent `google.appengine.api.lib_config`_
    configuration library.

    To use this class, create a subclass that redefines :py:attr:`~agar.config.Config._prefix` to the appengine_config prefix you'd like the
    configs to appear under.  Then, simply create class-level properties/functions/default values for each constant.

    When instantiating an instance of this class, you can override the default values for that instance by passing
    in new defaults via the constructor.  Of course, if there is an entry in ``appengine_config.py`` for your constant, that
    value will supersede any defined in the class or passed in via the constructor.

    Example subclass::

        class SampleConfig(Config):
            _prefix = 'test'

            STRING_CONFIG = 'defaultstring'

    Example usage::

        >>> config = SampleConfig.get_config()
        >>> custom_config = SampleConfig.get_config(STRING_CONFIG='customstring')

    Assuming there is no override for ``test_STRING_CONFIG`` in ``appengine_config.py``::

        >>> config.STRING_CONFIG == 'defaultstring'
        True
        >>> custom_config.STRING_CONFIG == 'customstring'
        True

    Assuming ``appengine_config.py`` contains the following line::

        test_STRING_CONFIG = 'settingstring'

    Then::

        >>> config.STRING_CONFIG == custom_config.STRING_CONFIG == 'settingstring'
        True
    """

    #: The appengine_config prefix that the configs should appear under. Override in subclasses. The default is ``agar``.
    _prefix = 'agar'

    def __init__(self, **kwargs):
        self.defaults = {}
        for setting in self.__class__.__dict__.keys():
            if not setting.startswith('_'):
                self.defaults[setting] = self.__class__.__dict__[setting]
        for key in kwargs.keys():
            if key in self.defaults.keys():
                self.defaults[key] = kwargs[key]
            else:
                raise AttributeError('Invalid config key: %s' % key)

    def __iter__(self):
        c = {}
        config = self.get_config()
        for key in config._defaults:
            c[key] = config.__getattr__(key)
        return c

    @classmethod
    def get_config(cls, **kwargs):
        """
        Registers and returns the `google.appengine.api.lib_config`_ ``ConfigHandle`` for the class. Keyword arguments
        will override default values defined in the :py:class:`~agar.config.Config` subclass (but, of course,
        will still defer to values in the ``appengine_config.py`` file).

        :param kwargs: Defaults to use for the config instance. Values in ``appengine_config.py`` will still override
            any values you specify.
        :return: The `google.appengine.api.lib_config`_ ``ConfigHandle`` for the class.
        """
        return lib_config.register(cls._prefix, cls(**kwargs).defaults)

    @classmethod
    def get_config_as_dict(cls, **kwargs):
        """
        Registers the `google.appengine.api.lib_config`_ ``ConfigHandle`` and returns its settings as a ``dict``.
        Keyword arguments will override default values defined in the :py:class:`~agar.config.Config` subclass
        (but, of course, will still defer to values in the ``appengine_config.py`` file).
        
        :param kwargs: Defaults to use for the config instance. Values in ``appengine_config.py`` will still override
            any values you specify.
        :return: A ``dict`` of the configurations.
        """
        c = {}
        config = cls.get_config(**kwargs)
        for key in config._defaults:
            c[key] = config.__getattr__(key)
        return c
