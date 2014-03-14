from datetime import datetime, timedelta
import logging
import time

from google.appengine.ext import ndb

from application.constants import ENTRY_STATE, OVERFLOW_REASON, DEFAULT_PERIOD_SCHEDULE, MAX_STORIES_PER_PERIOD
from application.fetcher import fetch_parsed_feed_for_url, fetch_parsed_feed_for_feed
from application.poster import build_html_from_post, broadcast_format_for_adn, prepare_entry_from_item
from application.process import process_parsed_feed
from application.utils import fit_to_box, find_feed_url, get_language
from application.publisher.entry import publish_entry

logger = logging.getLogger(__name__)


def format_date(dt):
    logger.info('dt: %s', dt)
    return dt.strftime('%a %b %d %I:%M %p')


def get_endpoint(kind, feed):
    if kind == 'channel':
        return 'channels/%s/messages' % (feed.channel_id)
    else:
        return 'posts'


class Entry(ndb.Model):
    guid = ndb.StringProperty(required=True)
    creating = ndb.BooleanProperty(default=False)
    title = ndb.StringProperty(indexed=False)
    summary = ndb.TextProperty(indexed=False)
    link = ndb.StringProperty()
    short_url = ndb.StringProperty()
    added = ndb.DateTimeProperty(auto_now_add=True)
    published = ndb.BooleanProperty(default=False)
    published_post = ndb.BooleanProperty(default=False)
    published_channel = ndb.BooleanProperty(default=False)
    overflow = ndb.BooleanProperty(default=False)
    overflow_reason = ndb.IntegerProperty(default=0)
    published_at = ndb.DateTimeProperty()
    status = ndb.IntegerProperty(default=ENTRY_STATE.ACTIVE)
    language = ndb.StringProperty()
    extra_info = ndb.JsonProperty(indexed=False)

    image_url = ndb.StringProperty()
    image_width = ndb.IntegerProperty()
    image_height = ndb.IntegerProperty()

    thumbnail_image_url = ndb.StringProperty()
    thumbnail_image_width = ndb.IntegerProperty()
    thumbnail_image_height = ndb.IntegerProperty()
    video_oembed = ndb.PickleProperty(indexed=False)

    tags = ndb.StringProperty(repeated=True)
    author = ndb.StringProperty(indexed=False)

    feed_item = ndb.PickleProperty(indexed=False)
    meta_tags = ndb.JsonProperty(indexed=False)
    images_in_html = ndb.JsonProperty(repeated=True, indexed=False)

    def to_json(self, feed=None, format=False):
        include = ['title', 'link', 'published', 'published_at', 'added']
        data = {}
        for attr in include:
            data[attr] = getattr(self, attr, None)

        for dt in ['published_at', 'added_at']:
            if data.get(dt):
                data['%s_in_secs' % (dt)] = time.mktime(data[dt].timetuple())
                data[dt] = format_date(data[dt])

        if self.overflow:
            data['overflow_reason'] = OVERFLOW_REASON.for_display(self.overflow_reason)

        if self.key:
            data['id'] = self.key.urlsafe()

        feed = feed or self.key.parent().get()
        if format:
            data['html'] = {}
            for post, kind in feed.format_entry_for_adn(self).get_result():
                data['html'][kind] = build_html_from_post(post)

            if feed and feed.channel_id:
                data['alert'] = broadcast_format_for_adn(feed, self)

            width = None
            height = None
            if feed.include_thumb and self.thumbnail_image_url:
                data['thumbnail_image_url'] = self.thumbnail_image_url
                width = self.thumbnail_image_width
                height = self.thumbnail_image_height

            if feed.include_video and self.video_oembed:
                data['thumbnail_image_url'] = self.video_oembed['thumbnail_url']
                width = self.video_oembed['thumbnail_width']
                height = self.video_oembed['thumbnail_height']

            if width and height:
                width, height = fit_to_box(width, height, 100, 100)
                data['thumbnail_image_width'] = width
                data['thumbnail_image_height'] = height

        return data

    @classmethod
    def entry_preview(cls, entries, feed, format=False):
        return [entry.to_json(feed=feed, format=format) for entry in entries]

    @classmethod
    @ndb.synctasklet
    def entry_preview_for_feed(cls, feed):
        parsed_feed, resp = yield fetch_parsed_feed_for_url(feed.feed_url)

        # Try and fix bad feed_urls on the fly
        new_feed_url = find_feed_url(resp, feed.feed_url)
        if new_feed_url:
            parsed_feed, resp = yield fetch_parsed_feed_for_url(new_feed_url)

        entries = []
        futures = []
        for item in parsed_feed.entries[0:3]:
            futures.append((item, prepare_entry_from_item(item, feed=feed)))

        for item, future in futures:
            entry = cls(**(yield future))
            if entry:
                entries.append(entry)

        raise ndb.Return(cls.entry_preview(entries, feed, format=True))

    @classmethod
    @ndb.tasklet
    def drain_queue(cls, feed):
        more = True
        cursor = None
        while more:
            entries, cursor, more = yield cls.latest_unpublished(feed).fetch_page_async(25, start_cursor=cursor)
            for entry in entries:
                entry.overflow = True
                entry.published = True
                entry.overflow_reason = OVERFLOW_REASON.FEED_OVERFLOW
                yield entry.put_async()

    @classmethod
    @ndb.tasklet
    def publish_for_feed(cls, feed, skip_queue=False):
        if not feed:
            logger.info("Asked to publish for a non-exsistant feed")
            raise ndb.Return(0)

        minutes_schedule = DEFAULT_PERIOD_SCHEDULE
        max_stories_to_publish = MAX_STORIES_PER_PERIOD
        if feed.manual_control:
            minutes_schedule = feed.schedule_period
            max_stories_to_publish = feed.max_stories_per_period

        if feed.dump_excess_in_period:
            max_stories_to_publish = 1

        # How many stories have been published in the last period_length
        now = datetime.now()
        period_ago = now - timedelta(minutes=minutes_schedule)
        lastest_published_entries = yield cls.latest_published(feed, since=period_ago).count_async()
        max_stories_to_publish = max_stories_to_publish - lastest_published_entries
        entries_posted = 0
        # If we still have time left in this period publish some more.
        if max_stories_to_publish > 0 or skip_queue:
            # If we are skipping the queue
            if skip_queue:
                max_stories_to_publish = max_stories_to_publish or 1

            latest_entries = yield cls.latest_unpublished(feed).fetch_async(max_stories_to_publish + 1)

            more_to_publish = False
            if len(latest_entries) > max_stories_to_publish:
                more_to_publish = True
                latest_entries = latest_entries[0: max_stories_to_publish]

            for entry in latest_entries:
                yield publish_entry(entry, feed)
                entries_posted += 1

            if not more_to_publish:
                feed.is_dirty = False
                yield feed.put_async()

            if more_to_publish and feed.dump_excess_in_period:
                yield cls.drain_queue(feed)

        raise ndb.Return(entries_posted)

    @classmethod
    @ndb.tasklet
    def process_parsed_feed(cls, parsed_feed, feed, overflow, overflow_reason=OVERFLOW_REASON.BACKLOG):
        raise ndb.Return(process_parsed_feed(cls, parsed_feed, feed, overflow, overflow_reason))

    @classmethod
    @ndb.tasklet
    def update_for_feed(cls, feed, publish=False, skip_queue=False, overflow=False, overflow_reason=OVERFLOW_REASON.BACKLOG):
        parsed_feed, resp, feed = yield fetch_parsed_feed_for_feed(feed)
        num_new_items = 0
        drain_queue = False
        # There should be no data in here anyway
        if resp.status_code != 304:
            etag = resp.headers.get('ETag')

            modified_feed = False
            # Update feed location
            if resp.was_permanente_redirect:
                feed.feed_url = resp.final_url
                modified_feed = True
                publish = False
            elif etag and feed.etag != etag:
                feed.etag = etag
                modified_feed = True

            if 'language' in parsed_feed.feed:
                lang = get_language(parsed_feed.feed.language)
                if lang != feed.language:
                    feed.language = lang
                    modified_feed = True

            if modified_feed:
                yield feed.put_async()

            new_guids, old_guids = yield cls.process_parsed_feed(parsed_feed, feed, overflow, overflow_reason)
            num_new_items = len(new_guids)
            if len(new_guids + old_guids) >= 5 and len(new_guids) == len(new_guids + old_guids):
                drain_queue = True

        if publish:
            yield cls.publish_for_feed(feed, skip_queue)

        if drain_queue:
            yield cls.drain_queue(feed)

        raise ndb.Return((parsed_feed, num_new_items))

    @classmethod
    @ndb.tasklet
    def delete_for_feed(cls, feed):
        more = True
        cursor = None
        while more:
            entries, cursor, more = yield cls.latest_for_feed(feed).fetch_page_async(25, start_cursor=cursor)
            entries_keys = [x.key for x in entries]
            ndb.delete_multi_async(entries_keys)

    @classmethod
    def latest_for_feed(cls, feed):
        return cls.query(cls.creating == False, ancestor=feed.key)

    @classmethod
    def latest_for_feed_by_added(cls, feed):
        return cls.query(cls.creating == False, ancestor=feed.key).order(-cls.added)

    @classmethod
    def latest_unpublished(cls, feed,):
        query = cls.query(cls.published == False, cls.creating == False, ancestor=feed.key).order(-cls.added)
        return query

    @classmethod
    def latest(cls, feed, include_overflow=False, overflow_cats=None, order_by='added'):
        q = cls.query(cls.published == True, cls.creating == False, ancestor=feed.key)
        logger.info('Order by: %s', order_by)
        if order_by == 'added':
            q = q.order(cls.added)

        if order_by == '-published_at':
            q = q.order(-cls.published_at)

        if overflow_cats is None:
            overflow_cats = [OVERFLOW_REASON.MALFORMED, OVERFLOW_REASON.FEED_OVERFLOW]

        if include_overflow:
            overflow_and_in_cat = ndb.AND(cls.overflow_reason.IN(overflow_cats), cls.overflow == True)
            not_overflow_or_overflow_in_cat = ndb.OR(cls.overflow == False, overflow_and_in_cat)
            q = q.filter(not_overflow_or_overflow_in_cat)
        else:
            q = q.filter(cls.overflow == False)

        return q

    @classmethod
    def latest_published(cls, feed, since=None):
        q = cls.query(cls.published == True, cls.creating == False, ancestor=feed.key).order(-cls.published_at).order(-cls.added)
        if since:
            q = q.filter(cls.published_at >= since)

        return q
