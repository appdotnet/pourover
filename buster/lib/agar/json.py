"""
The ``agar.json`` module contains classes to assist with creating json web service handlers.
"""

import datetime
import logging

from google.appengine.ext.db import BadRequestError, BadValueError

from agar.config import Config
from agar.models import ModelException

from pytz.gae import pytz

from restler.serializers import json_response as restler_json_response

from webapp2 import RequestHandler, HTTPException


INVALID_CURSOR = 'INVALID_CURSOR'


class JsonConfig(Config):
    """
    :py:class:`~agar.config.Config` settings for the ``agar.json`` library.
    Settings are under the ``agar_json`` namespace.

    The following settings (and defaults) are provided::

        agar_url_DEFAULT_PAGE_SIZE = 10
        agar_url_MAX_PAGE_SIZE = 100
        agar_url_USE_DATA_ROOT_NODE = True
        agar_url_ADD_SUCCESS_FLAG = False

    To override ``agar.json`` settings, define values in the ``appengine_config.py`` file in the root of your project.
    """
    _prefix = 'agar_json'

    DEFAULT_PAGE_SIZE = 10
    MAX_PAGE_SIZE = 100
    USE_DATA_ROOT_NODE = True
    ADD_SUCCESS_FLAG = False

config = JsonConfig.get_config()


def string_to_int(s, default=10):
    try:
        return int(s)
    except:
        return default

class JsonRequestHandler(RequestHandler):
    """
    A `webapp2.RequestHandler`_ implementation to help with json web service handlers, including error handling.
    """
    def _setup_context(self, context):
        if not context:
            context = {}
        context['request'] = self.request
        return context
    
    def _setup_data(self, model_or_query, status_code, status_text, errors=None):
        data = dict()
        data['status_code'] = status_code
        data['status_text'] = status_text
        data['timestamp'] = datetime.datetime.now(pytz.utc)
        if config.ADD_SUCCESS_FLAG:
            if status_code < 400:
                data['sucess'] = True
            else:
                data['sucess'] = False
        if errors is not None:
            data['errors'] = errors
        if config.USE_DATA_ROOT_NODE:
            data['data'] = model_or_query
        else:    
            data.update(model_or_query)
        return data

    def json_response(self, model_or_query, strategy=None, status_code=200, status_text='OK', errors=None, context=None):
        """
        Fills in the `webapp2.Response`_ with the contents of the passed model or query serialized using the
        :py:mod:`restler` library.

        :param model_or_query: The `Model`_ or `Query`_ to serialize.
        :param strategy: The :py:class:`~restler.serializers.SerializationStrategy` to use to serialize.
        :param status_code: The HTTP status code to set in the `webapp2.Response`_.
        :param status_text: A text description of the status code.
        :param errors: A dictionary of errors to add to the response.
        :param context: The context to be used when serializing.
        :return: The serialized text to be used as the HTTP response data.
        """
        context = self._setup_context(context)
        data = self._setup_data(model_or_query, status_code, status_text, errors=errors)
        return restler_json_response(self.response, data, strategy=strategy, status_code=status_code, context=context)

    def handle_exception(self, exception, debug_mode):
        """
        The `webapp2.RequestHandler`_ exception handler. Sets the `webapp2.Response`_ with appropriate settings.

        :param exception: The uncaught exception.
        :param debug_mode: Whether we're running in debug mode.
        """
        errors = None
        status_text = exception.message
        if isinstance(exception, HTTPException):
            code = exception.code
            status_text = "BAD_REQUEST"
            errors = exception.message
        elif isinstance(exception, ModelException):
            code = 400
            status_text = "BAD_REQUEST"
            errors = exception.message
        else:
            code = 500
            status_text = "INTERNAL_SERVER_ERROR"
            errors = exception.message
            logging.error("API 500 ERROR: %s" % exception)
        if code == 401:
            status_text = 'UNAUTHORIZED'
        if code == 403:
            status_text = 'FORBIDDEN'
        if code == 404:
            status_text = 'NOT_FOUND'
        if code == 405:
            status_text = 'METHOD_NOT_ALLOWED'
        self.json_response({}, status_code=code, status_text=status_text, errors=errors)


class MultiPageHandler(JsonRequestHandler):
    """
    A :py:class:`~agar.json.JsonRequestHandler` class to help with ``page_size`` and ``cursor`` parsing and logic.
    """
    @property
    def page_size(self):
        """
        The requested ``page_size`` constrained between ``1`` and the configuration value ``agar_json_MAX_PAGE_SIZE``.
        If ``page_size`` isn't passed in, it will default to the configuration value ``agar_json_DEFAULT_PAGE_SIZE``.

        :return: The requested page size for fetching.
        """
        page_size = string_to_int(self.request.get('page_size', str(config.DEFAULT_PAGE_SIZE)))
        page_size = min(max(page_size, 1), config.MAX_PAGE_SIZE)
        return page_size

    def fetch_page(self, query):
        """
        Fetches a page of the passed ``query`` using the :py:attr:`~agar.json.MultiPageHandler.page_size` and the
        ``cursor`` request parameter.

        :param query: The `Query`_ to fetch from.
        :return: A two-tuple containing results of the paged fetch and the next page's cursor if there's more results.
        """
        cursor = self.request.get('cursor', None)
        if cursor is not None:
            try:
                query = query.with_cursor(cursor)
            except (BadValueError, BadRequestError):
                self.abort(400, INVALID_CURSOR)
        results = []
        try:
            results = query.fetch(self.page_size)
        except (BadValueError, BadRequestError):
            self.abort(400, INVALID_CURSOR)
        next_cursor = None
        if len(results) == self.page_size:
            next_cursor = query.cursor()
        return results, next_cursor


class CorsMultiPageHandler(MultiPageHandler):
    """
    A :py:class:`~agar.json.MultiPageHandler` to help with Cross-Origin Resource sharing .
    """
    def options(self):
        origin = self.request.headers.get('Origin', 'unknown origin')
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET, PUT, DELETE, OPTIONS'
        self.response.headers['Access-Control-Max-Age'] = 1728000 
        self.response.headers['Access-Control-Allow-Credentials'] = \
            self.request.headers.get('Access-Credentials', 'true')
        self.response.headers['Access-Control-Allow-Origin']= ':'.join(origin.split(':')[0:2])
        self.response.headers['Access-Control-Allow-Origin']= origin.strip()
        self.response.headers['Access-Control-Allow-Headers'] = \
            self.request.headers.get('Access-Control-Request-Headers', '') 

    def json_response(self, model_or_query, strategy=None, status_code=200, status_text='OK', errors=None, context=None):
        context = self._setup_context(context)
        data = self._setup_data(model_or_query, status_code, status_text, errors=errors)
        origin = self.request.headers.get('Origin', '') 
        if origin:
            self.response.headers['Access-Control-Allow-Origin'] = origin
        else:
            self.response.headers['Access-Control-Allow-Origin'] = "/".join(self.request.headers.get("Referer", "").split("/")[0:3]) 
        self.response.headers['Access-Control-Allow-Headers'] = "true"
        self.response.headers['Access-Control-Allow-Credentials'] = "true"

        return restler_json_response(self.response, data, strategy=strategy, status_code=status_code, context=context)

