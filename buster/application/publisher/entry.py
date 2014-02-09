from datetime import datetime
import logging
import json

from application.constants import FEED_STATE, OVERFLOW_REASON
from application.poster import format_for_adn, broadcast_format_for_adn, instagram_format_for_adn

from google.appengine.ext import ndb

logger = logging.getLogger(__name__)


class PublishException(Exception):
    pass


class EntryPublisher(object):

    def __init__(self, entry, feed, user):
        self.entry = entry
        self.feed = feed
        self.user = user

    @classmethod
    @ndb.tasklet
    def from_data(cls, entry, feed):
        user = yield feed.key.parent().get_async()
        raise ndb.Return(cls(entry, feed, user))

    @ndb.tasklet
    def send_to_api(self, path, post, access_token):
        ctx = ndb.get_context()

        try:
            resp = yield ctx.urlfetch('https://alpha-api.app.net/stream/0/%s' % path, payload=json.dumps(post), deadline=30,
                                      method='POST', headers={
                                          'Authorization': 'Bearer %s' % access_token,
                                          'Content-Type': 'application/json',
                                      })
        except Exception, e:
            logger.exception('Failed to post path: %s data: %s' % (path, post))
            raise PublishException(e.message)

        parsed_resp = json.loads(resp.content)
        if resp.status_code == 401:
            yield self.handle_unauthorized(parsed_resp, post)
        elif resp.status_code == 200:

            self.handle_success(parsed_resp, post)
        elif resp.status_code == 400:
            yield self.handle_bad_response(parsed_resp, post)
        elif resp.status_code == 403:
            yield self.handle_forbidden(parsed_resp, post)
        else:
            logger.warn("Couldn't post entry key=%s. Error: %s Post:%s", self.entry.key.urlsafe(), parsed_resp, post)
            raise PublishException(resp.content)

    @ndb.tasklet
    def handle_unauthorized(self, resp, post_data):
        logger.warning("Disabling feed authorization has been pulled: %s", self.feed.key.urlsafe())
        self.feed.status = FEED_STATE.NEEDS_REAUTH
        yield self.feed.put_async()

    def handle_success(self, resp, post_data):
        logger.info('Published entry key=%s -> post_id=%s: %s', self.entry.key.urlsafe(), resp['data']['id'], post_data)

    @ndb.tasklet
    def handle_bad_response(self, resp, post_data):
        logger.warn("Couldn't post entry key=%s. Error: %s Post:%s putting on the backlog", self.entry.key.urlsafe(), resp, post_data)
        self.entry.overflow = True
        self.entry.overflow_reason = OVERFLOW_REASON.MALFORMED
        yield self.entry.put_async()

    @ndb.tasklet
    def handle_forbidden(self, resp, post_data):
        if resp.get('meta').get('error_message') == 'Forbidden: This channel is inactive':
            logger.info('Trying to post to an inactive channel: %s shutting this channel down for this feed: %s', self.feed.channel_id, self.feed.key.urlsafe())
            if not self.feed.publish_to_stream:
                logger.info('Feed wasnt set to publish publicly deleting channel all together %s %s %s', self.feed.channel_id, self.feed.key.urlsafe(), self.feed.feed_url)
                yield self.feed.key.delete_async()
            else:
                self.feed.channel_id = None
                yield self.feed.put_async()

    @ndb.tasklet
    def publish(self):
        published = True
        if not self.entry.published_post and (self.feed.publish_to_stream or not self.feed.channel_id):
            data = yield format_for_adn(self.feed, self.entry)
            path = 'posts'

            try:
                yield self.send_to_api(path, data, self.user.access_token)
                self.entry.published_post = True
                yield self.entry.put_async()
            except PublishException:
                published = False

        if not self.entry.published_channel and self.feed.channel_id:
            data = broadcast_format_for_adn(self.feed, self.entry)
            path = 'channels/%s/messages' % self.feed.channel_id

            try:
                yield self.send_to_api(path, data, self.user.access_token)
                self.entry.published_channel = True
                yield self.entry.put_async()
            except PublishException:
                published = False

        # The hope here is that if we encounter a temporary error above ^
        # That this process will die, but the pieces that are finished
        # will not be attempted again. Once they are done the entire
        # entry will be marked as published.
        if published:
            self.entry.published = True
            self.entry.published_at = datetime.now()
            yield self.entry.put_async()


class InstagramEntryPublisher(EntryPublisher):
    @ndb.tasklet
    def publish(self):
        if not self.entry.published:
            data = instagram_format_for_adn(self.feed, self.entry)
            path = 'posts'

            yield self.send_to_api(path, data, self.user.access_token)
            self.entry.published_post = True
            yield self.entry.put_async()

        self.entry.published = True
        self.entry.published_at = datetime.now()
        yield self.entry.put_async()


@ndb.tasklet
def publish_entry(entry, feed):
    if feed.__class__.__name__ == 'Feed':
        publisher = yield EntryPublisher.from_data(entry, feed)
    else:
        publisher = yield InstagramEntryPublisher.from_data(entry, feed)

    yield publisher.publish()
