from datetime import datetime

from django.utils.encoding import iri_to_uri
from google.appengine.ext import db
from google.appengine.ext import ndb
from google.appengine.api import prospective_search

from process import filter_entries
from poster import prepare_title_from_item, get_link_for_item


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

    last_successful_fetch = ndb.DateTimeProperty()

    initial_error = ndb.DateTimeProperty()
    feed_disabled = ndb.BooleanProperty(default=False)
    topics = ndb.StringProperty(repeated=True, indexed=False)

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
    def process_inbound_feed(self, parsed_feed, overflow=False):
        entries = filter_entries(parsed_feed.entries)
        rss_items = map(lambda x: RssItem.from_rss_item(x, self), entries)
        for item in rss_items:
            for topic in self.topics:
                prospective_search.match(item, topic, result_relative_url='/api/backend/queries/matched')

        raise ndb.Return(([], []))


@ndb.tasklet
def create_query_and_subscribe(topic, query):
    saved_query = RssSearchSubscription(query=query, topic=topic)
    yield saved_query.put_async()

    raise ndb.Return(prospective_search.subscribe(RssItem, saved_query.query, saved_query.urlsafe(), topic=topic, lease_duration_sec=0))
