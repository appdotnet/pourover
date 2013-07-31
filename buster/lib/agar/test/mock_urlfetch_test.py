from google.appengine.api import apiproxy_stub
from google.appengine.api import urlfetch
from google.appengine.api import urlfetch_service_pb
from google.appengine.api.urlfetch import DownloadError

from google.appengine.ext import testbed

from agar.test import BaseTest

class MockURLFetchServiceStub(apiproxy_stub.APIProxyStub):

    _responses = {}
    _method_map = {urlfetch_service_pb.URLFetchRequest.GET: 'GET',
                   urlfetch_service_pb.URLFetchRequest.POST: 'POST',
                   urlfetch_service_pb.URLFetchRequest.HEAD: 'HEAD',
                   urlfetch_service_pb.URLFetchRequest.PUT: 'PUT',
                   urlfetch_service_pb.URLFetchRequest.DELETE: 'DELETE'}

    def __init__(self, service_name='urlfetch'):
        super(MockURLFetchServiceStub, self).__init__(service_name)

    @classmethod
    def set_response(cls, url, content=None, status_code=None, headers=None, method=None):
        MockURLFetchServiceStub._responses[(url, method)] = {'content': content,
                                                             'status_code': status_code,
                                                             'headers': headers}
    @classmethod
    def clear_responses(cls):
        MockURLFetchServiceStub._responses.clear()

    def _decode_http_method(self, pb_method):
        """decode the method from the protocol buffer; stolen from urlfetch_stub.py"""
        method = self._method_map.get(pb_method)

        if not method:
            raise apiproxy_errors.ApplicationError(
                urlfetch_service_pb.URLFetchServiceError.UNSPECIFIED_ERROR)

        return method

    def _Dynamic_Fetch(self, request, response):
        url = request.url()
        method = self._decode_http_method(request.method())
        http_response = MockURLFetchServiceStub._responses.get((url, method)) or MockURLFetchServiceStub._responses.get((url, None))

        if http_response is None:
            raise Exception("No HTTP response was found for the URL '%s'" % (url))

        if isinstance(http_response['content'], DownloadError):
            raise http_response['content']

        response.set_statuscode(http_response.get('status_code') or 200)
        response.set_content(http_response.get('content'))

        if http_response.get('headers'):
            for header_key, header_value in http_response['headers'].items():
                header_proto = response.add_header()
                header_proto.set_key(header_key)
                header_proto.set_value(header_value)



class MockUrlfetchTest(BaseTest):
    """
    :py:class:`MockUrlfetchTest` replaces the `urlfetch`_ API stub with a mocked
    version that does not make real HTTP requests.

    To use it, inherit from :py:class:`MockUrlfetchTest` instead of
    :py:class:`BaseTest`, then register HTTP responses in your
    ``setUp`` method, or individual test case methods.

    If any of the code under test results in `urlfetch`_ call to an
    unregistered URL, it will raise an exception.

    Example::

       class MyHTTPTest(MockUrlfetchTest):
           def setUp(self):
               super(MyHTTPTest, self).setUp()

               self.set_response("http://www.google.com/blah", content="foobar", status_code=404)

           def test_get_google(self):
               result = urlfetch.fetch("http://www.google.com/blah")

               self.assertEqual(404, result.status_code)
               self.assertEqual("foobar", result.content)

           def test_this_will_fail(self):
               result = urlfetch.fetch("http://www.example.com/")
    """

    def setUp(self):
        super(MockUrlfetchTest, self).setUp()

        stub = MockURLFetchServiceStub()
        self.testbed._register_stub(testbed.URLFETCH_SERVICE_NAME, stub)

    def tearDown(self):
        MockURLFetchServiceStub.clear_responses()
        super(MockUrlfetchTest, self).tearDown()

    def set_response(self, url, content=None, status_code=None, headers=None, method=None):
        """
        Register an HTTP response for ``url`` with body containing ``content``.

        NOTE: MockUrlfetchTest does not follow redirects at this time.

        Examples::

            # Will cause a 200 OK response with no body for all HTTP methods:
            self.set_response("http://example.com")

            # Will cause a 404 Not Found for GET requests with 'gone fishing' as the body:
            self.set_response("http://example.com/404ed", content='gone fishing', status_code=404)

            # Will cause a 303 See Other for POST requests with a Location header and no body:
            self.set_response("http://example.com/posts", status_code=303, headers={'Location': 'http://example.com/posts/123'})

            # Will cause a DownloadError to be raised when the URL is requested:
            from google.appengine.api import urlfetch
            self.set_response("http://example.com/boom", content=urlfetch.DownloadError("Something Failed"))

        :param url: the URL for the HTTP request.
        :param content: the HTTP response's body, or an instance of DownloadError to simulate a failure.
        :param status_code: the expected status code. Defaults to 200 if not set.
        :param headers: a ``dict`` of headers for the HTTP response.
        :param method: the HTTP method that the response must match. If not set, all requests with the same URL will return the same thing.
        """
        MockURLFetchServiceStub.set_response(url, content=content, status_code=status_code, headers=headers, method=method)
