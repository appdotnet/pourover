"""
models.py

App Engine datastore models

"""
import logging
import uuid
from datetime import datetime, timedelta

from google.appengine.ext import ndb
from google.appengine.api import urlfetch
from django.utils.text import Truncator
import urllib

import feedparser
import json

from bs4 import BeautifulSoup
from flask import url_for
from .utils import append_query_string

logger = logging.getLogger(__name__)


class DjangoEnum(object):
    def __init__(self, *string_list):
        self.__dict__.update([(string, number) for (number, string, friendly)
                              in string_list])
        self.int_to_display = {number: friendly for (number, string, friendly) in string_list}

    def get_choices(self):
        return tuple(enumerate(self.__dict__.keys()))

    def __iter__(self):
        return self.__dict__.values().__iter__()

    def next(self):
        return self.__dict__.values().next()

    def for_display(self, index):
        return self.int_to_display[index]


ENTRY_STATE = DjangoEnum(
    (1, 'ACTIVE', 'Active'),
    (10, 'INACTIVE', 'Inactive'),
)


FEED_STATE = DjangoEnum(
    (1, 'ACTIVE', 'Active'),
    (10, 'INACTIVE', 'Inactive'),
)


UPDATE_INTERVAL = DjangoEnum(
    (5, 'MINUTE_1', '1 min'),
    (1, 'MINUTE_5', '5 mins'),
    (2, 'MINUTE_15', '15 mins'),
    (3, 'MINUTE_30', '30 mins'),
    (4, 'MINUTE_60', '60 mins'),
)


PERIOD_SCHEDULE = DjangoEnum(
    (1, 'MINUTE_1', '1 min'),
    (5, 'MINUTE_5', '5 mins'),
    (15, 'MINUTE_15', '15 mins'),
    (30, 'MINUTE_30', '30 mins'),
    (60, 'MINUTE_60', '60 mins'),
)


OVERFLOW_REASON = DjangoEnum(
    (1, 'BACKLOG', 'Added from feed backlog'),
    (2, 'FEED_OVERFLOW', 'Feed backed up'),
)

MAX_CHARS = 256
VALID_STATUS = (200, 300, 301, 302, 304, 307)


def strip_html_tags(html):
    if html is None:
        return None
    else:
        return ''.join(BeautifulSoup(html).findAll(text=True))


def ellipse_text(text, max_chars):
    truncate = Truncator(text)

    return truncate.chars(max_chars, u"\u2026")


def build_html_from_post(post):

    def entity_text(e):
        return post['text'][e['pos']:e['pos'] + e['len']]

    link_builder = lambda l: "<a href='%s'>%s</a>" % (l['url'], entity_text(l))

    # map starting position, length of entity placeholder to the replacement html
    entity_map = {}
    for entity_key, builder in [('links', link_builder)]:
        for entity in post.get('entities', {}).get(entity_key, []):
            entity_map[(entity['pos'], entity['len'])] = builder(entity)

    # replace strings with html
    html_pieces = []
    text_idx = 0  # our current place in the original text string
    for entity_start, entity_len in sorted(entity_map.keys()):
        if text_idx != entity_start:
            # if our current place isn't the start of an entity, bring in text until the next entity
            html_pieces.append(post.get('text', "")[text_idx:entity_start])

        # pull out the entity html
        entity_html = entity_map[(entity_start, entity_len)]
        html_pieces.append(entity_html)

        # move past the entity we just added
        text_idx = entity_start + entity_len

    # clean up any remaining text
    html_pieces.append(post.get('text', "")[text_idx:])
    # TODO: link to schema
    return '<span>%s</span>' % (''.join(html_pieces), )


def fetch_feed_url(feed_url, etag=None):
    logger.info('Fetching feed feed_url:%s etag:%s', feed_url, etag)
    return feedparser.parse(feed_url, agent='PourOver/1.0 +https://pour-over.appspot.com/', etag=etag)


class User(ndb.Model):
    access_token = ndb.StringProperty()

    @classmethod
    def key_from_adn_user(cls, adn_user):
        return 'adn_user_id=%d' % int(adn_user.id)


class Entry(ndb.Model):
    guid = ndb.StringProperty(required=True)
    title = ndb.StringProperty()
    summary = ndb.TextProperty()
    link = ndb.StringProperty()
    added = ndb.DateTimeProperty(auto_now_add=True)
    published = ndb.BooleanProperty(default=False)
    overflow = ndb.BooleanProperty(default=False)
    overflow_reason = ndb.IntegerProperty(default=0)
    published_at = ndb.DateTimeProperty()
    status = ndb.IntegerProperty(default=ENTRY_STATE.ACTIVE)
    extra_info = ndb.JsonProperty()

    def to_json(self, include=None):
        include = include or []
        data = {}
        for attr in include:
            data[attr] = getattr(self, attr, None)

        if self.overflow:
            data['overflow_reason'] = OVERFLOW_REASON.for_display(self.overflow_reason)

        data['id'] = self.key.id()

        return data

    def format_for_adn(self, include_summary):
        post_text = self.title
        links = []
        if include_summary:
            summary_text = strip_html_tags(self.summary)
            summary_text = ellipse_text(summary_text, 140)

        else:
            links = []
            summary_text = ''

        # Should be some room for a description
        if len(post_text) < (MAX_CHARS - 40) and summary_text:
            post_text = u'%s\n%s' % (post_text, summary_text)

        post_text = ellipse_text(post_text, MAX_CHARS)

        link = append_query_string(self.link, params={'utm_source': 'PourOver', 'utm_medium': 'App.net'})

        # logger.info(u'Text Len: %s text: %s entry_title:%s entry_title_len:%s', len(post_text), post_text, entry.title, len(entry.title))
        links.insert(0, (link, self.title))
        link_entities = []
        index = 0
        for href, link_text in links:
            # logger.info('Link info: %s %s %s', post_text, link_text, index)
            text_index = post_text.find(link_text, index)
            if text_index > -1:
                link_entities.append({
                    'url': href,
                    'text': link_text,
                    'pos': text_index,
                    'len': len(link_text),
                })
                index = text_index

        post = {
            'text': post_text,
            'annotations': [
                {
                    "type": "net.app.core.crosspost",
                    "value": {
                        "canonical_url": link
                    }
                }
            ]
        }

        if link_entities:
            post['entities'] = {
                'links': link_entities,
            }

        return post

    @classmethod
    def entry_preview_for_feed(cls, feed_url, include_summary):
        parsed_feed = fetch_feed_url(feed_url)
        feed_items = []
        for item in parsed_feed.entries:
            entry = cls(guid=item.guid, title=item.title, summary=item.get('summary', ''), link=item.link)
            feed_items.append(entry.format_for_adn(include_summary=include_summary))

        html = [build_html_from_post(x) for x in feed_items]

        return html

    @classmethod
    def create_from_feed_and_item(cls, feed, item, overflow=False, overflow_reason=None):
        entry = cls.query(cls.guid == item.guid, ancestor=feed.key).get()
        published = False
        if overflow:
            published = True
        if not entry:
            entry = cls(parent=feed.key, guid=item.guid, title=item.title, summary=item.get('summary', ''), link=item.link,
                        published=published, overflow=overflow, overflow_reason=overflow_reason)
            entry.put()

        return entry

    def publish_entry(self):
        feed = self.key.parent().get()
        user = feed.key.parent().get()
        post = self.format_for_adn(feed.include_summary)
        logger.info('Post: %s', post)
        resp = urlfetch.fetch('https://alpha-api.app.net/stream/0/posts', payload=json.dumps(post), method='POST', headers={
            'Authorization': 'Bearer %s' % (user.access_token, ),
            'Content-Type': 'application/json',
        })

        if resp.status_code != 200:
            raise Exception(resp.content)

        self.published = True
        self.published_at = datetime.now()
        self.put()

    @classmethod
    def drain_queue(cls, feed):
        more = True
        cursor = None
        while more:
            entries, cursor, more = cls.latest_unpublished(feed).fetch_page(25, start_cursor=cursor)
            for entry in entries:
                entry.overflow = True
                entry.published = True
                entry.overflow_reason = OVERFLOW_REASON.FEED_OVERFLOW
                entry.put()

    @classmethod
    def update_for_feed(cls, feed, publish=False, skip_queue=False, overflow=False, overflow_reason=OVERFLOW_REASON.BACKLOG):
        parsed_feed = fetch_feed_url(feed.feed_url, feed.etag)
        status = getattr(parsed_feed, 'status', None)
        if status and status not in VALID_STATUS:
            raise Exception('Could not fetch feed:%s status_code:%s' % (feed.feed_url, status))

        # logger.info('Parsed feed has not status href:%s status:%s', parsed_feed.href, status)

        # There should be no data in here anyway
        if parsed_feed.status == 304:
            return parsed_feed

        # Update feed location
        if parsed_feed.status == 301:
            feed.feed_url = parsed_feed.href
            feed.put()

        etag = getattr(parsed_feed, 'etag', None)
        if etag and feed.etag != etag:
            feed.etag = etag
            feed.put()

        for item in parsed_feed.entries:
            entry = cls.create_from_feed_and_item(feed, item, overflow=overflow, overflow_reason=overflow_reason)

        if publish:
            # How many stories have been published in the last period_length
            now = datetime.now()
            period_ago = now - timedelta(minutes=feed.schedule_period)
            lastest_published_entries = cls.latest_published(feed, since=period_ago)
            max_stories_to_publish = feed.max_stories_per_period - lastest_published_entries.count()

            # If we still have time left in this period publish some more.
            if max_stories_to_publish > 0 or skip_queue:
                # If we are skipping the queue
                if skip_queue:
                    max_stories_to_publish = max_stories_to_publish or 1

                latest_entries = cls.latest_unpublished(feed).fetch(max_stories_to_publish)

                for entry in latest_entries:
                    entry.publish_entry()
            else:
                cls.drain_queue(feed)

        return parsed_feed

    @classmethod
    def delete_for_feed(cls, feed):
        more = True
        cursor = None
        while more:
            entries, cursor, more = cls.latest_for_feed(feed).fetch_page(25, start_cursor=cursor)
            entries_keys = [x.key for x in entries]
            ndb.delete_multi(entries_keys)

    @classmethod
    def latest_for_feed(cls, feed):
        return cls.query(ancestor=feed.key)

    @classmethod
    def latest_unpublished(cls, feed):
        published = False
        return cls.query(cls.published == published, ancestor=feed.key).order(-cls.added)

    @classmethod
    def latest_published(cls, feed, since=None):
        published = True
        q = cls.query(cls.published == published, ancestor=feed.key).order(-cls.published_at).order(-cls.added)
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
    template = ndb.TextProperty(default='')
    added = ndb.DateTimeProperty(auto_now_add=True)
    update_interval = ndb.IntegerProperty(default=UPDATE_INTERVAL.MINUTE_5)
    extra_info = ndb.JsonProperty()
    schedule_period = ndb.IntegerProperty(default=PERIOD_SCHEDULE.MINUTE_5)
    max_stories_per_period = ndb.IntegerProperty(default=1)
    etag = ndb.StringProperty()
    hub_secret = ndb.StringProperty()

    @classmethod
    def for_user(cls, user):
        return cls.query(ancestor=user.key)

    @classmethod
    def for_user_and_url(cls, user, feed_url):
        return cls.query(cls.feed_url == feed_url, ancestor=user.key)

    @classmethod
    def for_interval(cls, interval_id):
        return cls.query(cls.update_interval == interval_id)

    @classmethod
    def process_new_feed(cls, feed, overflow, overflow_reason):
        # Sync pull down the latest feeds

        parsed_feed = Entry.update_for_feed(feed, overflow=overflow, overflow_reason=overflow_reason)
        hub_url = None
        for link in parsed_feed.feed.links:
            if link['rel'] == 'hub':
                hub_url = link['href']
                feed.hub = hub_url

                if hub_url.startswith('https://'):
                    feed.hub_secret = uuid.uuid4().hex
                else:
                    feed.hub_secret = None

                feed.verify_token = uuid.uuid4().hex
                feed.put()

                subscribe_data = {
                    "hub.callback": url_for('feed_subscribe', feed_key=feed.key.urlsafe(), _external=True),
                    "hub.mode": 'subscribe',
                    "hub.topic": feed.feed_url,
                    'hub.verify_token': feed.verify_token,
                }

                if feed.hub_secret:
                    subscribe_data['hub.secret'] = feed.hub_secret

                logger.info('Hub: %s Subscribe Data: %s', hub_url, subscribe_data)
                form_data = urllib.urlencode(subscribe_data)
                urlfetch.fetch(hub_url, method='POST', payload=form_data)

        return feed

    @classmethod
    def create_feed_from_form(cls, user, form):
        feed = cls(parent=user.key)
        form.populate_obj(feed)
        feed.put()
        return cls.process_new_feed(feed, overflow=True, overflow_reason=OVERFLOW_REASON.BACKLOG)

    @classmethod
    def create_feed(cls, user, feed_url, include_summary, schedule_period=PERIOD_SCHEDULE.MINUTE_5, max_stories_per_period=1):
        feed = cls(parent=user.key, feed_url=feed_url, include_summary=include_summary)
        feed.put()
        return cls.process_new_feed(feed)

    def to_json(self):
        return {
            'feed_url': self.feed_url,
            'feed_id': self.key.id(),
            'include_summary': self.include_summary,
            'schedule_period': self.schedule_period,
            'max_stories_per_period': self.max_stories_per_period,
        }
