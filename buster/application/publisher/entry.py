from datetime import datetime
import logging
import json

from google.appengine.ext import deferred
from google.appengine.ext import ndb
from google.appengine.api.taskqueue import TaskRetryOptions

from application.constants import FEED_STATE, OVERFLOW_REASON
from application.poster import format_for_adn, broadcast_format_for_adn, instagram_format_for_adn

logger = logging.getLogger(__name__)


class PublishException(Exception):
    pass


class ApiPublisher(object):

    def __init__(self, entry_key, feed_key):
        self.entry_key = entry_key
        self.feed_key = feed_key

    @ndb.tasklet
    def send_to_api(self, path, post, access_token):
        ctx = ndb.get_context()
        try:
            resp = yield ctx.urlfetch('https://alpha-api.app.net/stream/0/%s' % path, payload=json.dumps(post), deadline=30,
                                      method='POST', headers={
                                          'Authorization': 'Bearer %s' % access_token,
                                          'Content-Type': 'application/json',
                                      })
        except:
            logger.exception('Failed to post path: %s data: %s' % (path, post))
            raise deferred.SingularTaskFailure()

        parsed_resp = json.loads(resp.content)
        if resp.status_code == 401:
            logger.info('unauthorized')
            yield self.handle_unauthorized(parsed_resp, post)
            raise deferred.PermanentTaskFailure()
        elif resp.status_code == 200:
            self.handle_success(parsed_resp, post)
        elif resp.status_code == 400:
            yield self.handle_bad_response(parsed_resp, post)
            raise deferred.PermanentTaskFailure()
        elif resp.status_code == 403:
            yield self.handle_forbidden(parsed_resp, post)
            raise deferred.PermanentTaskFailure()
        else:
            logger.warn("Couldn't post entry key=%s. Error: %s Post:%s", self.entry_key, parsed_resp, post)
            raise deferred.SingularTaskFailure()

    @ndb.tasklet
    def handle_unauthorized(self, resp, post_data):
        logger.warning("Disabling feed authorization has been pulled: %s", self.feed_key)
        feed = yield ndb.Key(urlsafe=self.feed_key).get_async()
        feed.status = FEED_STATE.NEEDS_REAUTH
        yield feed.put_async()

    def handle_success(self, resp, post_data):
        logger.info('Published entry key=%s -> post_id=%s: %s', self.entry_key, resp['data']['id'], post_data)

    @ndb.tasklet
    def handle_bad_response(self, resp, post_data):
        logger.warn("Couldn't post entry key=%s. Error: %s Post:%s putting on the backlog", self.entry_key, resp, post_data)
        entry = yield ndb.Key(urlsafe=self.entry_key).get_async()
        entry.overflow = True
        entry.overflow_reason = OVERFLOW_REASON.MALFORMED
        yield entry.put_async()

    @ndb.tasklet
    def handle_forbidden(self, resp, post_data):
        if resp.get('meta').get('error_message') == 'Forbidden: This channel is inactive':
            feed = yield ndb.Key(urlsafe=self.feed_key).get_async()
            logger.info('Trying to post to an inactive channel: %s shutting this channel down for this feed: %s', feed.channel_id, feed.key.urlsafe())
            if not feed.publish_to_stream:
                logger.info('Feed wasnt set to publish publicly deleting channel all together %s %s %s', feed.channel_id, feed.key.urlsafe(), feed.feed_url)
                yield feed.key.delete_async()
            else:
                feed.channel_id = None
                yield feed.put_async()


@ndb.synctasklet
def publish_to_api(entry_key, feed_key, path, post, access_token):
    api_publisher = ApiPublisher(entry_key, feed_key)
    api_publisher.send_to_api(path, post, access_token)
    logger.info('publishing to the api')
api_publish_opts = TaskRetryOptions(task_retry_limit=3)


class EntryPublisher(object):

    def __init__(self, entry, feed, user, ignore_publish_state=False):
        self.entry = entry
        self.feed = feed
        self.user = user
        self.ignore_publish_state = ignore_publish_state

    @classmethod
    @ndb.tasklet
    def from_data(cls, entry, feed, ignore_publish_state=False):
        user = yield feed.key.parent().get_async()
        raise ndb.Return(cls(entry, feed, user, ignore_publish_state))

    @ndb.transactional_tasklet(retries=0)
    def publish(self):
        entry = self.entry = yield self.entry.key.get_async()

        if self.feed.publish_to_stream or not self.feed.channel_id:
            entry.published_post = True
            data = yield format_for_adn(self.feed, entry)
            path = 'posts'
            logger.info('Deffering post')
            deferred.defer(publish_to_api, entry.key.urlsafe(), self.feed.key.urlsafe(), path, data,
                           self.user.access_token, _transactional=True, _retry_options=api_publish_opts)

        if self.feed.channel_id:
            entry.published_channel = True
            data = broadcast_format_for_adn(self.feed, entry)
            path = 'channels/%s/messages' % self.feed.channel_id
            logger.info('Deffering message')
            deferred.defer(publish_to_api, entry.key.urlsafe(), self.feed.key.urlsafe(), path, data,
                           self.user.access_token, _transactional=True, _retry_options=api_publish_opts)

        entry.published = True
        entry.published_at = datetime.now()
        yield entry.put_async()


class InstagramEntryPublisher(EntryPublisher):
    @ndb.transactional_tasklet(retries=0)
    def publish(self):
        entry = self.entry = yield self.entry.key.get_async()
        if not self.entry.published:
            self.entry.published_post = True
            self.entry.published = True
            self.entry.published_at = datetime.now()
            yield self.entry.put_async()
            data = instagram_format_for_adn(self.feed, self.entry)
            path = 'posts'

            deferred.defer(publish_to_api, entry.key.urlsafe(), self.feed.key.urlsafe(), path, data,
                           self.user.access_token, _transactional=True, _retry_options=api_publish_opts)


@ndb.tasklet
def publish_entry(entry, feed, ignore_publish_state=False):
    if feed.__class__.__name__ == 'Feed':
        publisher = yield EntryPublisher.from_data(entry, feed, ignore_publish_state=ignore_publish_state)
    else:
        publisher = yield InstagramEntryPublisher.from_data(entry, feed, ignore_publish_state=ignore_publish_state)

    yield publisher.publish()
