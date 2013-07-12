import webtest
from unittest2 import TestCase

class WebTest(TestCase):
    """
    A base class for testing web requests. Provides a wrapper around
    the `WebTest`_ package that is mostly compatable with `gaetestbed`_'s.

    To use, inherit from :py:class:`WebTest` and define a class-level
    variable called ``APPLICATION`` that is set to the WSGI application
    under test.

    :py:class:`WebTest` is usually used in conjuction with
    :py:class:`BaseTest` to set up the App Engine API proxy stubs.

    Example::

        from agar.test import BaseTest, WebTest
        import my_app
        
        class TestMyApp(BaseTest, WebTest):

            APPLICATION = my_app.application

            def test_get_home_page(self):
                response = self.get("/")
                self.assertOK(response)
    """

    @property
    def app(self):
        if not getattr(self, '_web_test_app', None):
            self._web_test_app = webtest.TestApp(self.APPLICATION)

        return self._web_test_app
            
    def get(self, url, params=None, headers=None):
        return self.app.get(url, params=params, headers=headers, status="*", expect_errors=True)

    def post(self, url, params='', headers=None, upload_files=None):
        return self.app.post(url, params, headers=headers, status="*", expect_errors=True, upload_files=upload_files)

    def put(self, url, params='', headers=None, upload_files=None):
        return self.app.put(url, params, headers=headers, status="*", expect_errors=True, upload_files=upload_files)

    def delete(self, url, headers=None):
        return self.app.delete(url, headers=headers, status="*", expect_errors=True)

    def assertOK(self, response):
        """
        Assert that ``response`` was 200 OK.
        """
        self.assertEqual(200, response.status_int)

    def assertRedirects(self, response, to=None):
        """
        Assert that ``response`` was a 302 redirect.

        :param to: an absolute or relative URL that the redirect must match.
        """
        self.assertEqual(302, response.status_int)
        
        if to:
            if not to.startswith("http"):
                to = 'http://localhost%s' % to

            self.assertEqual(response.headers['Location'], to)

    def assertForbidden(self, response):
        """
        Assert that ``response`` was 403 Forbidden.
        """
        self.assertEqual(403, response.status_int)

    def assertNotFound(self, response):
        """
        Assert that ``response`` was 404 Not Found.
        """
        self.assertEqual(404, response.status_int)

    def assertUnauthorized(self, response, challenge=None):
        """
        Assert that ``response`` was 401 Unauthorized.

        :param challenge: assert that the ``WWW-Authenticate`` header matches this value, if provided
        """
        self.assertEqual(401, response.status_int)
        if challenge:
            self.assertEqual(challenge, response.headers['WWW-Authenticate'])

    def assertBadRequest(self, response):
        """
        Assert that ``response`` was 400 Bad Request.
        """
        self.assertEqual(400, response.status_int)
        
