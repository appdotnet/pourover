from datetime import datetime
import logging

from django.utils.encoding import iri_to_uri
from google.appengine.ext import db
from google.appengine.ext import ndb
from google.appengine.api import prospective_search

from process import filter_entries
from poster import prepare_title_from_item, get_link_for_item
from utils import guid_for_item


logger = logging.getLogger(__name__)


# Prospective Search Item
class RssItem(db.Model):
    title = db.StringProperty()
    link = db.StringProperty()
    author = db.StringProperty()
    body = db.TextProperty()
    tags = db.StringListProperty()

    @classmethod
    def from_rss_item(cls, item, feed):
        rss_item = cls()
        title = prepare_title_from_item(item)
        link = iri_to_uri(get_link_for_item(feed, item))
        body = item.get('summary', '')

        tags = []
        if 'tags' in item:
            tags = filter(None, [x['term'] for x in item.tags])

        author = ''
        if 'author' in item and item.author:
            author = item.author

        rss_item.title = title
        rss_item.link = link
        rss_item.body = body
        rss_item.tags = tags
        rss_item.author = author

        return rss_item


class RssSearchSubscription(ndb.Model):
    query = ndb.StringProperty(indexed=False)
    added = ndb.DateTimeProperty(auto_now_add=True)
    topic = ndb.StringProperty(indexed=False)
    channel_id = ndb.IntegerProperty()


class RssFeed(ndb.Model):
    feed_url = ndb.StringProperty()
    added = ndb.DateTimeProperty(auto_now_add=True)

    last_fetched_content_hash = ndb.StringProperty(indexed=False)
    etag = ndb.StringProperty()
    external_polling_bucket = ndb.IntegerProperty(default=1)

    linked_list_mode = ndb.BooleanProperty(default=False)

    last_successful_fetch = ndb.DateTimeProperty()
    last_guid = ndb.StringProperty()
    initial_error = ndb.DateTimeProperty()
    feed_disabled = ndb.BooleanProperty(default=False)
    topics = ndb.StringProperty(repeated=True, indexed=False)
    update_interval = 1

    @ndb.tasklet
    def track_error(self):
        if not self.initial_error:
            self.initial_error = datetime.now()
            yield self.put_async()

        raise ndb.Return()

    @ndb.tasklet
    def clear_error(self):
        if self.initial_error:
            self.initial_error = None
            yield self.put_async()

        raise ndb.Return()

    @ndb.tasklet
    def filter_entries(self, items):

        if not self.last_guid:
            self.last_guid = guid_for_item(items[0])
            yield self.put_async()
            logger.info('prospective: Feed is brand new recording latest guid and exiting %s %s', self.feed_url, self.key.urlsafe())
            raise ndb.Return([])

        entries = []
        seen_guid = False
        # iterate old to new
        for entry in reversed(items):
            if seen_guid:
                entries += [entry]
            logger.info('prospective: %s', guid_for_item(entry))
            if self.last_guid == guid_for_item(entry):
                seen_guid = True

        # Process newest to oldest
        raise ndb.Return(list(reversed(entries)))

    @ndb.tasklet
    def process_inbound_feed(self, parsed_feed, overflow=False):
        entries = filter_entries(parsed_feed.entries)
        entries = yield self.filter_entries(entries)

        if not entries:
            logger.info('prospective: Feed has seen all entries nothing new %s %s', self.feed_url, self.key.urlsafe())
            raise ndb.Return(([], []))

        last_guid = guid_for_item(entries[0])
        logger.info('prospective: entries before rss_items %s', len(entries))
        rss_items = map(lambda x: RssItem.from_rss_item(x, self), entries)
        logger.info('prospective: Processing inbound prospective search %s %s %s' % (self.feed_url, len(rss_items), self.key.urlsafe()))

        for item in rss_items:
            for topic in self.topics:
                logger.info('prospective: matching %s %s' % (item, topic))
                blah = prospective_search.match(item, topic, result_relative_url='/api/backend/queries/matched')
                logger.info('What do we get back %s', blah)

        self.last_guid = last_guid
        yield self.put_async()
        raise ndb.Return(([], []))

    @ndb.tasklet
    def publish_inbound_feed(self, skip_queue=False):
        logger.info('prospective: Noop publish inbound feed %s' % (self.key.urlsafe()))
        logger.last_successful_fetch = datetime.now()
        raise ndb.Return('')


@ndb.tasklet
def create_query_and_subscribe(topic, query, channel_id):
    saved_query = RssSearchSubscription(query=query, topic=topic)
    yield saved_query.put_async()

    raise ndb.Return(prospective_search.subscribe(RssItem, saved_query.query, saved_query.urlsafe(), topic=topic, lease_duration_sec=0))
