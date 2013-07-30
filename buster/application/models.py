"""
models.py

App Engine datastore models

"""
import logging
import uuid
from datetime import datetime, timedelta


from bs4 import BeautifulSoup
from google.appengine.ext import ndb
from google.appengine.api import urlfetch
import urllib
from urlparse import urlparse, parse_qs
import json


from flask import url_for
from fetcher import fetch_parsed_feed_for_url, fetch_parsed_feed_for_feed
from constants import ENTRY_STATE, FEED_STATE, FORMAT_MODE, UPDATE_INTERVAL, PERIOD_SCHEDULE, OVERFLOW_REASON
from poster import build_html_from_post, format_for_adn, prepare_entry_from_item
from utils import get_language, guid_for_item, find_feed_url


logger = logging.getLogger(__name__)

# Don't complain about this
ndb.add_flow_exception(urlfetch.DeadlineExceededError)


class User(ndb.Model):
    access_token = ndb.StringProperty()

    @classmethod
    def key_from_adn_user(cls, adn_user):
        return 'adn_user_id=%d' % int(adn_user.id)


class Entry(ndb.Model):
    guid = ndb.StringProperty(required=True)
    creating = ndb.BooleanProperty(default=False)
    title = ndb.StringProperty()
    summary = ndb.TextProperty()
    link = ndb.StringProperty()
    short_url = ndb.StringProperty()
    added = ndb.DateTimeProperty(auto_now_add=True)
    published = ndb.BooleanProperty(default=False)
    overflow = ndb.BooleanProperty(default=False)
    overflow_reason = ndb.IntegerProperty(default=0)
    published_at = ndb.DateTimeProperty()
    status = ndb.IntegerProperty(default=ENTRY_STATE.ACTIVE)
    language = ndb.StringProperty()
    extra_info = ndb.JsonProperty()

    image_url = ndb.StringProperty()
    image_width = ndb.IntegerProperty()
    image_height = ndb.IntegerProperty()

    thumbnail_image_url = ndb.StringProperty()
    thumbnail_image_width = ndb.IntegerProperty()
    thumbnail_image_height = ndb.IntegerProperty()
    video_oembed = ndb.PickleProperty()

    tags = ndb.StringProperty(repeated=True)
    author = ndb.StringProperty()

    feed_item = ndb.PickleProperty()
    meta_tags = ndb.JsonProperty()

    def to_json(self, include=None, feed=None, format=False):
        include = include or []
        data = {}
        for attr in include:
            data[attr] = getattr(self, attr, None)

        if self.overflow:
            data['overflow_reason'] = OVERFLOW_REASON.for_display(self.overflow_reason)

        if self.key:
            data['id'] = self.key.urlsafe()

        feed = feed or self.key.parent().get()
        if format:
            data['html'] = build_html_from_post(format_for_adn(self, feed).get_result())
            if feed.include_thumb and self.thumbnail_image_url:
                data['thumbnail_image_url'] = self.thumbnail_image_url

            if feed.include_video and self.video_oembed:
                data['thumbnail_image_url'] = self.video_oembed['thumbnail_url']

        return data

    @classmethod
    def entry_preview(cls, entries, feed, format=False):
        return [entry.to_json(feed=feed, format=format) for entry in entries]

    @classmethod
    @ndb.synctasklet
    def entry_preview_for_feed(cls, feed):
        parsed_feed, resp = yield fetch_parsed_feed_for_url(feed.feed_url)

        # Try and fix bad feed_urls on the fly
        new_feed_url = find_feed_url(parsed_feed, resp)
        if new_feed_url:
            parsed_feed, resp = yield fetch_parsed_feed_for_url(new_feed_url)

        entries = []
        futures = []
        for item in parsed_feed.entries[0:3]:
            futures.append((item, prepare_entry_from_item(parsed_feed, item, feed=feed)))

        for item, future in futures:
            entry = cls(**(yield future))
            if entry:
                entries.append(entry)

        raise ndb.Return(cls.entry_preview(entries, feed, format=True))

    @ndb.tasklet
    def publish_entry(self, feed):
        feed = yield self.key.parent().get_async()
        user = yield feed.key.parent().get_async()
        # logger.info('Feed settings include_summary:%s, include_thumb: %s', feed.include_summary, feed.include_thumb)
        post = yield format_for_adn(self, feed)
        ctx = ndb.get_context()
        try:
            resp = yield ctx.urlfetch('https://alpha-api.app.net/stream/0/posts', payload=json.dumps(post), deadline=30,
                                      method='POST', headers={
                                          'Authorization': 'Bearer %s' % (user.access_token, ),
                                          'Content-Type': 'application/json',
                                      })
        except:
            logger.exception('Failed to post Post: %s' % (post))
            return

        if resp.status_code == 401:
            feed.status = FEED_STATE.NEEDS_REAUTH
            yield feed.put_async()
        elif resp.status_code == 200:
            post_obj = json.loads(resp.content)
            logger.info('Published entry key=%s -> post_id=%s: %s', self.key.urlsafe(), post_obj['data']['id'], post)
        else:
            logger.warn("Couldn't post entry key=%s. Error: %s Post:%s", self.key.urlsafe(), resp.content, post)
            raise Exception(resp.content)

        self.published = True
        self.published_at = datetime.now()
        yield self.put_async()

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
        # How many stories have been published in the last period_length
        now = datetime.now()
        period_ago = now - timedelta(minutes=feed.schedule_period)
        lastest_published_entries = yield cls.latest_published(feed, since=period_ago).count_async()
        max_stories_to_publish = feed.max_stories_per_period - lastest_published_entries
        entries_posted = 0
        # If we still have time left in this period publish some more.
        if max_stories_to_publish > 0 or skip_queue:
            # If we are skipping the queue
            if skip_queue:
                max_stories_to_publish = max_stories_to_publish or 1

            latest_entries = yield cls.latest_unpublished(feed).fetch_async(max_stories_to_publish)
            for entry in latest_entries:
                yield entry.publish_entry(feed)
                entries_posted += 1

        raise ndb.Return(entries_posted)

    @classmethod
    @ndb.tasklet
    def process_parsed_feed(cls, parsed_feed, feed, overflow, overflow_reason=OVERFLOW_REASON.BACKLOG):
        keys_by_guid = {guid_for_item(item): ndb.Key(cls, guid_for_item(item), parent=feed.key) for item in parsed_feed.entries}
        entries = yield ndb.get_multi_async(keys_by_guid.values())
        old_guids = [x.key.id() for x in entries if x]
        new_guids = filter(lambda x: x not in old_guids, keys_by_guid.keys())
        new_entries_by_guid = {x: cls(key=keys_by_guid.get(x), guid=x, creating=True) for x in new_guids}
        new_entries = yield ndb.put_multi_async(new_entries_by_guid.values())

        published = overflow
        futures = []
        for item in parsed_feed.entries:
            entry = new_entries_by_guid.get(guid_for_item(item))
            if not entry:
                continue

            futures.append((entry, prepare_entry_from_item(parsed_feed, item, feed, overflow, overflow_reason, published)))

        for entry, future in futures:
            entry_kwargs = yield future
            entry_kwargs.pop('parent')
            entry_kwargs['creating'] = False
            entry.populate(**entry_kwargs)

        saved_entries = yield ndb.put_multi_async(new_entries_by_guid.values())

        raise ndb.Return((new_guids, old_guids))

    @classmethod
    @ndb.tasklet
    def update_for_feed(cls, feed, publish=False, skip_queue=False, overflow=False, overflow_reason=OVERFLOW_REASON.BACKLOG):
        parsed_feed, resp = yield fetch_parsed_feed_for_feed(feed)
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
    def latest_unpublished(cls, feed):
        published = False
        return cls.query(cls.published == published, cls.creating == False, ancestor=feed.key).order(-cls.added)

    @classmethod
    def latest_published(cls, feed, since=None):
        published = True
        q = cls.query(cls.published == published, cls.creating == False, ancestor=feed.key).order(-cls.published_at).order(-cls.added)
        if since:
            q = q.filter(cls.published_at >= since)

        return q


class Feed(ndb.Model):
    """Keep track of users"""
    feed_url = ndb.StringProperty()
    hub = ndb.StringProperty()
    subscribed_at_hub = ndb.BooleanProperty(default=False)
    verify_token = ndb.StringProperty()
    status = ndb.IntegerProperty(default=FEED_STATE.ACTIVE)
    include_summary = ndb.BooleanProperty(default=False)
    include_thumb = ndb.BooleanProperty(default=False)
    include_video = ndb.BooleanProperty(default=False)
    linked_list_mode = ndb.BooleanProperty(default=False)
    format_mode = ndb.IntegerProperty(default=FORMAT_MODE.LINKED_TITLE)
    template = ndb.TextProperty(default='')
    added = ndb.DateTimeProperty(auto_now_add=True)
    update_interval = ndb.IntegerProperty(default=UPDATE_INTERVAL.MINUTE_5)
    extra_info = ndb.JsonProperty()
    schedule_period = ndb.IntegerProperty(default=PERIOD_SCHEDULE.MINUTE_5)
    max_stories_per_period = ndb.IntegerProperty(default=1)
    etag = ndb.StringProperty()
    language = ndb.StringProperty()
    hub_secret = ndb.StringProperty()
    bitly_login = ndb.StringProperty()
    bitly_api_key = ndb.StringProperty()
    last_fetched_content_hash = ndb.StringProperty()
    last_successful_fetch = ndb.DateTimeProperty()
    feed_disabled = ndb.BooleanProperty(default=False)

    @classmethod
    def for_user(cls, user):
        return cls.query(ancestor=user.key)

    @classmethod
    def for_user_and_url(cls, user, feed_url):
        return cls.query(cls.feed_url == feed_url, ancestor=user.key)

    @classmethod
    def for_interval(cls, interval_id):
        return cls.query(cls.update_interval == interval_id, cls.status == FEED_STATE.ACTIVE)

    @classmethod
    @ndb.tasklet
    def reauthorize(cls, user):
        qit = cls.query(cls.status == FEED_STATE.NEEDS_REAUTH, ancestor=user.key).iter()
        while (yield qit.has_next_async()):
            feed = qit.next()
            feed.status = FEED_STATE.ACTIVE
            yield feed.put_async()

    @ndb.tasklet
    def subscribe_to_hub(self):
        subscribe_data = {
            "hub.callback": url_for('feed_subscribe', feed_key=self.key.urlsafe(), _external=True),
            "hub.mode": 'subscribe',
            "hub.topic": self.feed_url,
            'hub.verify_token': self.verify_token, # apparently this is no longer apart of PuSH v0.4, but it is apart of v3 so lets try and do both
            'hub.verify': self.verify_token,  # apparently this is no longer apart of PuSH v0.4, but it is apart of v3 so lets try and do both
        }

        if self.hub_secret:
            subscribe_data['hub.secret'] = self.hub_secret

        logger.info('Hub: %s Subscribe Data: %s', self.hub, subscribe_data)
        form_data = urllib.urlencode(subscribe_data)
        ctx = ndb.get_context()
        resp = yield ctx.urlfetch(self.hub, method='POST', payload=form_data)
        logger.info('PuSH Subscribe request hub:%s status_code:%s response:%s', self.hub, resp.status_code, resp.content)

    @classmethod
    @ndb.tasklet
    def process_new_feed(cls, feed, overflow, overflow_reason):
        # Sync pull down the latest feeds

        parsed_feed, num_new_entries = yield Entry.update_for_feed(feed, overflow=overflow, overflow_reason=overflow_reason)
        hub_url = None
        feed_links = parsed_feed.feed.links if 'links' in parsed_feed.feed else []
        for link in feed_links:
            if link['rel'] == 'hub':
                hub_url = link['href']
                feed.hub = hub_url

                if hub_url.startswith('https://'):
                    feed.hub_secret = uuid.uuid4().hex
                else:
                    feed.hub_secret = None

                feed.verify_token = uuid.uuid4().hex
                yield feed.put_async()
                feed.subscribe_to_hub()

        raise ndb.Return(feed)

    @classmethod
    @ndb.tasklet
    def create_feed_from_form(cls, user, form):
        feed = cls(parent=user.key)
        form.populate_obj(feed)
        yield feed.put_async()

        # This triggers special first time behavior when fetching the feed
        feed.first_time = True

        feed = yield cls.process_new_feed(feed, overflow=True, overflow_reason=OVERFLOW_REASON.BACKLOG)
        raise ndb.Return(feed)

    @classmethod
    @ndb.tasklet
    def create_feed(cls, user, feed_url, include_summary, schedule_period=PERIOD_SCHEDULE.MINUTE_5, max_stories_per_period=1):
        feed = cls(parent=user.key, feed_url=feed_url, include_summary=include_summary)
        yield feed.put_async()
        feed = yield cls.process_new_feed(feed)
        raise ndb.Return(feed)

    def to_json(self):
        return {
            'feed_url': self.feed_url,
            'feed_id': self.key.id(),
            'include_summary': self.include_summary,
            'format_mode': self.format_mode,
            'include_thumb': self.include_thumb,
            'include_video': self.include_video,
            'linked_list_mode': self.linked_list_mode,
            'schedule_period': self.schedule_period,
            'max_stories_per_period': self.max_stories_per_period,
            'bitly_login': self.bitly_login,
            'bitly_api_key': self.bitly_api_key,
        }
