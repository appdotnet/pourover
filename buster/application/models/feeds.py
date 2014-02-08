"""
models.py

App Engine datastore models

"""
import logging
import uuid
from datetime import datetime, timedelta
import hashlib
import itertools

from google.appengine.ext import ndb
from google.appengine.api import urlfetch
import urllib
from urlparse import urlparse
import json


from flask import url_for
from application.forms import FeedUpdate, FeedCreate, FeedPreview, InstagramFeedCreate, NoOpForm
from application.fetcher import fetch_url
from application.constants import (FEED_STATE, FORMAT_MODE, UPDATE_INTERVAL, PERIOD_SCHEDULE, OVERFLOW_REASON,
                                   FEED_TYPE, INBOUND_EMAIL_VERSION)
from application.poster import format_for_adn, instagram_format_for_adn, broadcast_format_for_adn
from entry import Entry

logger = logging.getLogger(__name__)

# Don't complain about this
ndb.add_flow_exception(urlfetch.DeadlineExceededError)


class InstagramFeed(ndb.Model):
    """
    Feed URL can just be the API call that we make
    https://api.instagram.com/v1/users/3/media/recent/
    """

    access_token = ndb.StringProperty()
    user_id = ndb.IntegerProperty()
    username = ndb.StringProperty()
    description = ndb.StringProperty()
    added = ndb.DateTimeProperty(auto_now_add=True)

    # Posting Schedule By Default will be auto controlled
    manual_control = ndb.BooleanProperty(default=False)
    schedule_period = ndb.IntegerProperty(default=PERIOD_SCHEDULE.MINUTE_5)
    max_stories_per_period = ndb.IntegerProperty(default=1)
    user_agent = ndb.StringProperty(default=None)

    status = ndb.IntegerProperty(default=FEED_STATE.ACTIVE)
    is_dirty = ndb.BooleanProperty(default=True)
    include_thumb = True
    include_video = True

    # Class variables
    create_form = InstagramFeedCreate
    update_form = NoOpForm
    preview_form = NoOpForm
    alpha_api_path = 'posts'
    visible = True
    # Custom user_agent

    @property
    def link(self):
        return 'https://instagram.com/%s' % (self.username)

    @property
    def title(self):
        return self.username

    @property
    def feed_url(self):
        return "https://api.instagram.com/v1/users/self/media/recent/?access_token=%s" % (self.access_token)

    @classmethod
    def for_user(cls, user):
        return cls.query(ancestor=user.key)

    @classmethod
    def for_user_and_form(cls, user, form):
        user_id = form.data['user_id']
        return cls.query(cls.user_id == user_id, ancestor=user.key)

    @classmethod
    def for_interval(cls, interval_id):
        if interval_id != 4:
            return

        return cls.query(cls.status == FEED_STATE.ACTIVE)

    @classmethod
    @ndb.tasklet
    def create_feed_from_form(cls, user, form):
        feed = cls()
        form.populate_obj(feed)
        feed.key = ndb.Key(cls, int(feed.user_id), parent=user.key)
        yield feed.put_async()
        feed, new_entries = yield feed.process_feed(overflow=True, overflow_reason=OVERFLOW_REASON.BACKLOG)
        raise ndb.Return(feed)

    @ndb.tasklet
    def process_feed(self, overflow, overflow_reason):
        # Sync pull down the latest feeds
        resp = yield fetch_url(self.feed_url, user_agent=self.user_agent)
        parsed_feed = json.loads(resp.content)

        posts = parsed_feed.get('data', [])
        new_entries = 0
        for post in posts:
            key = ndb.Key(Entry, post.get('id'), parent=self.key)
            entry = yield key.get_async()
            if not entry:
                standard_resolution = post.get('images', {}).get('standard_resolution')
                kwargs = {}
                kwargs['image_url'] = standard_resolution.get('url')
                kwargs['image_width'] = standard_resolution.get('width')
                kwargs['image_height'] = standard_resolution.get('height')
                low_resolution = post.get('images', {}).get('low_resolution')
                kwargs['thumbnail_image_url'] = low_resolution.get('url')
                kwargs['thumbnail_image_width'] = low_resolution.get('width')
                kwargs['thumbnail_image_height'] = low_resolution.get('height')
                caption = post.get('caption')
                if not caption:
                    kwargs['title'] = '.'
                else:
                    kwargs['title'] = caption.get('text', '')
                kwargs['link'] = post.get('link')
                kwargs['feed_item'] = post
                kwargs['creating'] = False
                if overflow:
                    kwargs['overflow'] = overflow
                    kwargs['overflow_reason'] = overflow_reason
                    kwargs['published'] = True

                entry = Entry(key=key, guid=post.get('id'), **kwargs)
                new_entries += 1
                yield entry.put_async()

        raise ndb.Return((self, new_entries))

    @ndb.tasklet
    def format_entry_for_adn(self, entry, for_publish=False):
        post = instagram_format_for_adn(self, entry)
        raise ndb.Return([(post, 'post')])

    def to_json(self):
        feed_info = {
            'username': self.username,
            'title': self.title,
            'link': self.link,
            'feed_id': int(self.key.id()),
            'feed_type': FEED_TYPE.INSTAGRAM,
            'feed_url': self.link,
        }

        return feed_info


class Feed(ndb.Model):
    """Keep track of users"""

    feed_url = ndb.StringProperty()
    title = ndb.StringProperty()
    description = ndb.StringProperty()
    added = ndb.DateTimeProperty(auto_now_add=True)
    update_interval = ndb.IntegerProperty(default=UPDATE_INTERVAL.MINUTE_5)

    # Posting Schedule By Default will be auto controlled
    manual_control = ndb.BooleanProperty(default=False)
    schedule_period = ndb.IntegerProperty(default=PERIOD_SCHEDULE.MINUTE_5)
    max_stories_per_period = ndb.IntegerProperty(default=1)

    status = ndb.IntegerProperty(default=FEED_STATE.ACTIVE)
    include_summary = ndb.BooleanProperty(default=False)
    include_thumb = ndb.BooleanProperty(default=False)
    include_video = ndb.BooleanProperty(default=False)
    linked_list_mode = ndb.BooleanProperty(default=False)
    format_mode = ndb.IntegerProperty(default=FORMAT_MODE.LINKED_TITLE)
    template = ndb.TextProperty(default='')

    etag = ndb.StringProperty()
    language = ndb.StringProperty()

    bitly_login = ndb.StringProperty()
    bitly_api_key = ndb.StringProperty()
    last_fetched_content_hash = ndb.StringProperty()
    last_successful_fetch = ndb.DateTimeProperty()
    feed_disabled = ndb.BooleanProperty(default=False)

    extra_info = ndb.JsonProperty()

    link = ndb.StringProperty()  # Link is a semantic thing, where as feed_url is a technical thing
    hub = ndb.StringProperty()
    subscribed_at_hub = ndb.BooleanProperty(default=False)
    verify_token = ndb.StringProperty()
    hub_secret = ndb.StringProperty()

    # Image finding strategies
    image_in_rss = ndb.BooleanProperty(default=True)
    image_in_content = ndb.BooleanProperty(default=True)
    image_in_meta = ndb.BooleanProperty(default=True)
    image_in_html = ndb.BooleanProperty(default=False)

    user_agent = ndb.StringProperty(default=None)
    channel_id = ndb.IntegerProperty()
    publish_to_stream = ndb.BooleanProperty(default=False)
    email = ndb.StringProperty()
    error_count = ndb.IntegerProperty(default=0)
    use_external_poller = ndb.BooleanProperty(default=False)
    external_polling_bucket = ndb.IntegerProperty(default=1)

    # Does this feed need to be processed
    is_dirty = ndb.IntegerProperty(default=True)

    # Error tracking tools
    initial_error = ndb.DateTimeProperty()

    # last image hash
    last_image_hash = ndb.StringProperty()

    # Class variables
    update_form = FeedUpdate
    create_form = FeedCreate
    preview_form = FeedPreview
    alpha_api_path = 'posts'
    visible = True

    @property
    def alpha_api_path(self):
        if self.channel_id:
            return 'channels/%s/messages' % (self.channel_id)
        else:
            return 'posts'

    @property
    def image_strategy_blacklist(self):
        blacklist = list()
        if not self.image_in_rss:
            blacklist.append('rss')
        if not self.image_in_content:
            blacklist.append('content')
        if not self.image_in_meta:
            blacklist.append('meta')
        if not self.image_in_html:
            blacklist.append('html')

        return set(blacklist)

    @ndb.tasklet
    def update_feed_from_parsed_feed(self, parsed_feed, save=False):
        if not parsed_feed:
            raise ndb.Return()

        feed_info = parsed_feed.get('feed', {})

        link = feed_info.get('link')
        if not link or not link.startswith('http'):
            try:
                urlparts = urlparse(self.feed_url)
                link = '%s://%s' % (urlparts.scheme, urlparts.netloc)
            except:
                link = None

        if link:
            link = link[0:499]

        title = feed_info.get('title')
        if title:
            title = title[0:499]

        description = feed_info.get('subtitle', feed_info.get('subtitle'))
        if description:
            description = description[0:499]

        if any([self.link != link, self.title != title, self.description != description]):
            self.link = link
            self.title = title
            self.description = description
            raise ndb.Return(True)

        raise ndb.Return(False)

    @property
    def effective_title(self):
        return self.title or self.link or self.feed_url

    @property
    def effective_description(self):
        return self.description or ''

    @property
    def effective_link(self):
        return self.link or self.feed_url

    @classmethod
    def for_user(cls, user):
        return cls.query(ancestor=user.key)

    @classmethod
    def for_user_and_channel(cls, user, channel_id):
        return cls.query(cls.channel_id == channel_id, ancestor=user.key)

    @classmethod
    def for_user_and_form(cls, user, form):
        feed_url = form.data['feed_url']
        return cls.query(cls.feed_url == feed_url, ancestor=user.key)

    @classmethod
    def for_interval(cls, interval_id):
        return cls.query(cls.update_interval == interval_id, cls.status == FEED_STATE.ACTIVE)

    @classmethod
    def for_email(cls, email):
        return cls.query(cls.email == email).get()

    @ndb.tasklet
    def process_feed(self, overflow, overflow_reason):
        parsed_feed, num_new_items = yield Entry.update_for_feed(self)
        raise ndb.Return((parsed_feed, num_new_items))

    @classmethod
    @ndb.synctasklet
    def reauthorize(cls, user):
        logger.info("Reauthorizing feeds for user: %s", user.key.urlsafe())
        qit = cls.query(ancestor=user.key).iter()
        while (yield qit.has_next_async()):
            feed = qit.next()
            if FEED_STATE.NEEDS_REAUTH:
                feed.status = FEED_STATE.ACTIVE
                yield feed.put_async()

    @ndb.tasklet
    def subscribe_to_hub(self):
        subscribe_data = {
            "hub.callback": url_for('feed_subscribe', feed_key=self.key.urlsafe(), _external=True),
            "hub.mode": 'subscribe',
            "hub.topic": self.feed_url,
            'hub.verify_token': self.verify_token,  # apparently this is no longer apart of PuSH v0.4, but it is apart of v3 so lets try and do both
            'hub.verify': self.verify_token,  # apparently this is no longer apart of PuSH v0.4, but it is apart of v3 so lets try and do both
        }

        if self.hub_secret:
            subscribe_data['hub.secret'] = self.hub_secret

        logger.info('Hub: %s Subscribe Data: %s', self.hub, subscribe_data)
        form_data = urllib.urlencode(subscribe_data)
        ctx = ndb.get_context()
        resp = yield ctx.urlfetch(self.hub, method='POST', payload=form_data)
        logger.info('PuSH Subscribe request hub:%s status_code:%s response:%s', self.hub, resp.status_code, resp.content)
        if resp.status_code == 402:
            logger.info('Removing %s because we got a 402', self.feed_url)
            self.hub = None
            yield self.put_async()

    @classmethod
    @ndb.tasklet
    def process_new_feed(cls, feed, overflow, overflow_reason):
        # Sync pull down the latest feeds

        parsed_feed, num_new_entries = yield Entry.update_for_feed(feed, overflow=overflow, overflow_reason=overflow_reason)
        logger.info('Processinge new feed num_new_entries:%s parsed_feed.entries:%s', num_new_entries, len(parsed_feed.entries))
        updated = False
        try:
            updated = yield feed.update_feed_from_parsed_feed(parsed_feed)
        except Exception, e:
            logger.exception(e)

        delattr(feed, "first_time")
        if updated:
            yield feed.put_async()

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
        feed.email = uuid.uuid4().hex
        feed = yield cls.process_new_feed(feed, overflow=True, overflow_reason=OVERFLOW_REASON.BACKLOG)
        raise ndb.Return(feed)

    @classmethod
    @ndb.tasklet
    def create_feed(cls, user, feed_url, include_summary, schedule_period=PERIOD_SCHEDULE.MINUTE_5, max_stories_per_period=1):
        feed = cls(parent=user.key, feed_url=feed_url, include_summary=include_summary)
        yield feed.put_async()
        feed = yield cls.process_new_feed(feed)
        raise ndb.Return(feed)

    @ndb.tasklet
    def format_entry_for_adn(self, entry, for_publish=False):
        posts = []
        if (not self.channel_id or (self.channel_id and self.publish_to_stream)):
            if for_publish and not entry.published_post or not for_publish:
                post = yield format_for_adn(self, entry)
                posts += [(post, 'post')]

        if self.channel_id and not entry.published_channel:
            if for_publish and not entry.published_channel or not for_publish:
                post = broadcast_format_for_adn(self, entry)
                posts += [(post, 'channel')]

        raise ndb.Return(posts)

    @property
    def inbound_email(self):
        return '%s_%s_%s@adn-pourover.appspotmail.com' % (self.email, FEED_TYPE.BROADCAST, INBOUND_EMAIL_VERSION)

    @ndb.tasklet
    def create_entry_from_mail(self, mail_message):
        plaintext_bodies = mail_message.bodies('text/plain')
        html_bodies = mail_message.bodies('text/html')

        msg = None
        for content_type, body in itertools.chain(plaintext_bodies, html_bodies):
            msg = body.decode()
            if msg:
                break
        # Hash the message content, and hour so we won't have the same message within the hour
        guid = hashlib.sha256(msg + datetime.now().strftime('%Y%m%d%H')).hexdigest()
        entry = Entry(title=mail_message.subject, summary=msg, guid=guid, parent=self.key)

        yield entry.put_async()

        raise ndb.Return(entry)

    @ndb.tasklet
    def track_error(self):
        now = datetime.utcnow()
        logger.info('initial error: %s', self.initial_error)
        if not self.initial_error:
            self.initial_error = now
            yield self.put_async()
            raise ndb.Return()
        logger.info("Now: %s - intial_error: %s > 2 days %s", now, self.initial_error, timedelta(days=2))
        if (now - self.initial_error) > timedelta(days=2):
            logger.info('Disabling a feed thats been bad for greater then two days: %s', self.key.urlsafe())
            self.feed_disabled = True
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
        result = yield Entry.process_parsed_feed(parsed_feed, self, overflow=False)
        raise ndb.Return(result)

    @ndb.tasklet
    def publish_inbound_feed(self, skip_queue=False):
        result = yield Entry.publish_for_feed(self, skip_queue=skip_queue)
        raise ndb.Return(result)

    def to_json(self):
        feed_info = {
            'feed_url': self.feed_url,
            'include_summary': self.include_summary,
            'format_mode': self.format_mode,
            'include_thumb': self.include_thumb,
            'include_video': self.include_video,
            'linked_list_mode': self.linked_list_mode,
            'schedule_period': self.schedule_period,
            'max_stories_per_period': self.max_stories_per_period,
            'bitly_login': self.bitly_login,
            'bitly_api_key': self.bitly_api_key,
            'title': self.effective_title,
            'link': self.effective_link,
            'description': self.effective_description,
            'feed_type': FEED_TYPE.RSS,
            'publish_to_stream': self.publish_to_stream,
        }

        if getattr(self, 'preview', None) is None:
            feed_info['feed_id'] = self.key.id()

        if self.channel_id:
            feed_info['channel_id'] = self.channel_id

        return feed_info


FEED_TYPE_TO_CLASS = {
    FEED_TYPE.RSS: Feed,
    FEED_TYPE.INSTAGRAM: InstagramFeed,
}
