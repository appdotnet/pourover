import os
import hashlib
import unittest2
from google.appengine.api import memcache
from google.appengine.api import users
from google.appengine.ext import testbed


class BaseTest(unittest2.TestCase):
    """
    A base class for App Engine unit tests that sets up API proxy
    stubs for all available services using `testbed`_ and clears them
    between each test run.

    Note: the `images`_ stub is only set up if `PIL`_ is found.

    To use, simply inherit from ``BaseTest``::

        import agar

        from models import MyModel

        class MyTestCase(agar.test.BaseTest):

            def test_datastore(self):
                model = MyModel(foo='foo')
                model.put()

                # will always be true because the datastore is cleared
                # between test method runs.
                self.assertEqual(1, MyModel.all().count())

    :py:class:`BaseTest` is designed to be mostly API-compatable with
    `gaetestbed`_'s assertions. However, unlike `gaetestbed`_, the assertions are split
    into only two classes: :py:class:`BaseTest` and
    :py:class:`WebTest`.
    """

    def setUp(self):
        os.environ['HTTP_HOST'] = 'localhost'

        self.testbed = testbed.Testbed()
        self.testbed.activate()

        self.testbed.init_datastore_v3_stub()
        self.testbed.init_memcache_stub()
        self.testbed.init_taskqueue_stub()
        self.testbed.init_urlfetch_stub()
        self.testbed.init_user_stub()
        self.testbed.init_xmpp_stub()
        self.testbed.init_mail_stub()
        self.testbed.init_blobstore_stub()

        try:
            from google.appengine.api.images import images_stub
            self.testbed.init_images_stub()
        except ImportError:
            pass

    def tearDown(self):
        # deactivate testbed; also has effect of clearning any
        # environment variables set during the test.
        self.testbed.deactivate()

    def clear_datastore(self):
        """
        Clear the Data Store of all its data.

        This method can be used inside your tests to clear the Data Store mid-test.

        For example::

            import unittest

            from agar.test import BaseTest

            class MyTestCase(BaseTest):
                def test_clear_datastore(self):
                    # Add something to the Data Store
                    models.MyModel(field="value").put()
                    self.assertLength(models.MyModel.all(), 1)

                    # And then empty the Data Store
                    self.clear_datastore()
                    self.assertLength(models.MyModel.all(), 0)
        """
        self.testbed.get_stub('datastore_v3').Clear()

    def log_in_user(self, email):
        """
        Log in a `User`_ with the given email address. This will cause
        `users.get_current_user`_ to return a `User`_ with the same
        email address and user_id as if it was entered into the SDK's
        log in prompt.
        """
        # stolen from dev_appserver_login
        user_id_digest = hashlib.md5(email.lower()).digest()
        user_id = '1' + ''.join(['%02d' % ord(x) for x in user_id_digest])[:20]

        os.environ['USER_EMAIL'] = email
        os.environ['USER_ID'] = user_id

        return users.User(email=email, _user_id=user_id)

    def get_sent_messages(self, to=None, sender=None, subject=None, body=None, html=None):
        """
        Return a list of email messages matching the given criteria.

        :param to: the ``To:`` email address.
        :param sender: the ``From:`` email address.
        :param subject: the value of the ``Subject:``.
        :param body: the value of the body of the email.
        :param html: the value of the HTML body of the email.
        """
        return self.testbed.get_stub('mail').get_sent_messages(to=to, sender=sender, subject=subject, body=body, html=html)

    def assertEmailSent(self, to=None, sender=None, subject=None, body=None, html=None):
        """
        Assert that at least one email was sent with the specified criteria.

        Note that App Engine does not allow emails to be sent from
        non-administrative users of the application. This method
        cannot check for that.

        Examples::

            mail.send_mail(to='test@example.com',
                           subject='hello world',
                           sender='foobar@example.com',
                           body='I can has email?')
            self.assertEmailSent()
            self.assertEmailSent(to='test@example.com')
            # this will fail
            self.assertEmailSent(to='foobar@example.com')

        :param to: the ``To:`` email address.
        :param sender: the ``From:`` email address.
        :param subject: the value of the ``Subject:``.
        :param body: the value of the body of the email.
        :param html: the value of the HTML body of the email.
        """
        messages = self.get_sent_messages(to=to, sender=sender, subject=subject, body=body, html=html)
        self.assertNotEqual(0, len(messages),
                            "No matching email messages were sent.")

    def assertEmailNotSent(self, to=None, sender=None, subject=None, body=None, html=None):
        """
        Assert that no email was sent with the specified criteria.

        :param to: the ``To:`` email address.
        :param sender: the ``From:`` email address.
        :param subject: the value of the ``Subject:``.
        :param body: the value of the body of the email.
        :param html: the value of the HTML body of the email.
        """
        messages = self.get_sent_messages(to=to, sender=sender, subject=subject, body=body, html=html)
        self.assertLength(0, messages, "Expected no emails to be sent, but %s were sent." % len(messages))

    def assertLength(self, expected, iterable, message=None):
        """
        Assert that ``iterable`` is of length ``expected``.

        NOTE: This assertion uses the standard xUnit (expected,
        actual) order for parameters. However, this is the reverse of
        `gaetestbed`_.

        :param expected: an integer representing the expected length
        :param iterable: an iterable which will be converted to a list.
        :param message: optional message for assertion.
        """
        length = len(list(iterable))
        message = message or 'Expected length: %s but was length: %s' % (expected, length)
        self.assertEqual(expected, length, message)

    def assertEmpty(self, iterable):
        """
        Assert that ``iterable`` is of length 0. Equivalent to
        ``self.assertLength(0, iterable)``.
        """
        self.assertLength(0, iterable)

    def assertTasksInQueue(self, n=None, url=None, name=None, queue_names=None):
        """
        Search for `Task`_ objects matching the given criteria and assert that there are ``n`` tasks.

        Example::

           deferred.defer(some_task, _name='some_task')
           self.assertTasksInQueue(n=1, name='some_task')

        :param n: the number of tasks in the queue. If not specified, ``n`` defaults to 0.
        :param url: URL criteria tasks must match. If ``url`` is ``None``, all tasks will be matched.
        :param name: name criteria tasks must match. If ``name`` is ``None``, all tasks will be matched.
        :param queue_names: queue name criteria tasks must match. If ``queue_name`` is ``None`` tasks in all queues will be matched.
        """
        tasks = self.get_tasks(url=url, name=name, queue_names=queue_names)

        self.assertEqual(n or 0, len(tasks))

    def get_tasks(self, url=None, name=None, queue_names=None):
        """
        Returns a list of `Task`_ objects with the specified criteria.

        :param url: URL criteria tasks must match. If ``url`` is ``None``, all tasks will be matched.
        :param name: name criteria tasks must match. If ``name`` is ``None``, all tasks will be matched.
        :param queue_names: queue name criteria tasks must match. If ``queue_name`` is ``None`` tasks in all queues will be matched.

        """
        return self.testbed.get_stub('taskqueue').get_filtered_tasks(url=url, name=name, queue_names=queue_names)

    def assertMemcacheHits(self, hits):
        """
        Asserts that the memcache API has had ``hits`` successful lookups.

        :param hits: number of memcache hits
        """
        self.assertEqual(hits, memcache.get_stats()['hits'])

    def assertMemcacheItems(self, items):
        """
        Asserts that the memcache API has ``items`` key-value pairs.

        :param items: number of items in memcache
        """
        self.assertEqual(items, memcache.get_stats()['items'])

