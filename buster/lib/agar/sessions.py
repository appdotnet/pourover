"""
The ``agar.sessions`` module contains classes to assist with creating `webapp2.RequestHandler`_ s.
"""

from webapp2 import RequestHandler, cached_property

from webapp2_extras import sessions

from agar.config import Config


class Webapp2ExtrasSessionsConfig(Config):
    """
    :py:class:`~agar.config.Config` settings for the `webapp2_extras.sessions`_ library.
    Settings are under the ``webapp2_extras_sessions`` namespace.
    
    The following settings (and defaults) are provided::
    
        cookie_args = {
            'max_age': None,
            'domain': None,
            'secure': None,
            'httponly': False,
            'path': '/'
        }
        secret_key = None,
        cookie_name = 'session'
        session_max_age = None
        backends = {
            'datastore': 'webapp2_extras.appengine.sessions_ndb.DatastoreSessionFactory',
            'memcache': 'webapp2_extras.appengine.sessions_memcache.MemcacheSessionFactory',
            'securecookie': 'webapp2_extras.sessions.SecureCookieSessionFactory'
        }
    
    To override `webapp2_extras.sessions`_ settings, define values in the ``appengine_config.py`` file in the root of
    your project.
    """
    _prefix = 'webapp2_extras_sessions'

    cookie_args = {
        'max_age': None,
        'domain': None,
        'secure': None,
        'httponly': False,
        'path': '/'
    }
    secret_key = None,
    cookie_name = 'session'
    session_max_age = None
    backends = {
        'datastore': 'webapp2_extras.appengine.sessions_ndb.DatastoreSessionFactory',
        'memcache': 'webapp2_extras.appengine.sessions_memcache.MemcacheSessionFactory',
        'securecookie': 'webapp2_extras.sessions.SecureCookieSessionFactory'
    }

    @classmethod
    def get_webapp2_config(cls, config=None, **kwargs):
        """
        Registers the `google.appengine.api.lib_config`_ ``ConfigHandle`` and returns its settings as a
        `webapp2 configuration`_ ``dict`` with the `webapp2_extras.sessions`_ configurations under the key
        ``webap2_extras.sessions``.
        Keyword arguments will override default values defined in the :py:class:`~agar.config.Config` subclass
        (but, of course, will still defer to values in the ``appengine_config.py`` file).

        :param config: If ``None`` (the default), the method will return a new ``dict`` with the single configuration
            key ``webap2_extras.sessions``. If this is parameter is a ``dict``, the new key will be added to the passed
            ``dict`` and returned.
        :param kwargs: Defaults to use for the config instance. Values in ``appengine_config.py`` will still override
            any values you specify.
        :return: A ``dict`` of the configurations.
        """
        if config is None:
            config = {}
        config['webapp2_extras.sessions'] = cls.get_config_as_dict(**kwargs)
        return config

#: The `google.appengine.api.lib_config`_ ``ConfigHandle`` for ``webapp2_extras_sessions`` settings.
config = Webapp2ExtrasSessionsConfig.get_config()


class SessionStore(sessions.SessionStore):
    """
    A `webapp2_extras.sessions.SessionStore`_ implementation that uses :py:class:`~agar.sessions.Webapp2ExtrasSessionsConfig`
    instead of the built-in webapp2 config library.
    """
    def __init__(self, request):
        """Initializes the session store.

        :param request:
            A :class:`webapp2.Request` instance.
        """
        super(SessionStore, self).__init__(request, config=Webapp2ExtrasSessionsConfig.get_config_as_dict())


class SessionRequestHandler(RequestHandler):
    """
    A `webapp2.RequestHandler`_ implementation that provides access to a session via the ``session`` attribute..
    """
    def dispatch(self):
        """
        Dispatches the request after grabbing the ``session_store`` and providing access to the current
        `webapp2.Request`_ 's session.

        This will first check if there's a handler_method defined in the matched route, and if not it'll use the
        method correspondent to the request method (``get()``, ``post()`` etc).
        """
        # Get a session store for this request.
        self.session_store = sessions.get_store(factory=SessionStore, request=self.request)

        try:
            # Dispatch the request.
            RequestHandler.dispatch(self)
        finally:
            # Save all sessions.
            self.session_store.save_sessions(self.response)

    @cached_property
    def session(self):
        """Returns a session using the default cookie key."""
        return self.session_store.get_session()
