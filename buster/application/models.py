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
from urlparse import urlparse
import feedparser
import json

from bs4 import BeautifulSoup
from flask import url_for
from .utils import append_query_string

logger = logging.getLogger(__name__)

# Monkeypatch feedparser
feedparser._HTMLSanitizer.acceptable_elements = set(list(feedparser._HTMLSanitizer.acceptable_elements) + ["object", "embed", "iframe", "param"])

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
    (2, 'NEEDS_REAUTH', 'Needs reauth'),
    (10, 'INACTIVE', 'Inactive'),
)

FORMAT_MODE = DjangoEnum(
    (1, 'LINKED_TITLE', 'Linked Title'),
    (2, 'TITLE_THEN_LINK', 'Title then Link'),
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
VALID_STATUS = (200, 304)

# From here https://github.com/appdotnet/api-spec/wiki/Language-codes
VALID_LANGUAGES = 'ar az bg bn bs ca cs cy da de el en en_GB es es_AR es_MX es_NI et eu fa fi fr fy_NL ga gl he hi hr hu id is it ja ka kk km kn ko lt lv mk ml mn nb ne nl nn no pa pl pt pt_BR ro ru sk sl sq sr sr_Latn sv sw ta te th tr tt uk ur vi zh_CN zh_TW'.split(' ')


def get_language(lang=None):
    if not lang:
        return lang

    if '-' in lang:
        lang = lang.replace('-', '_')

    if lang == 'en_US':
        lang = 'en'

    if lang in VALID_LANGUAGES:
        return lang

    return None


class FetchException(Exception):
    pass


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
    html = ''.join(html_pieces)
    html = html.replace('\n', '<br>')
    # TODO: link to schema
    return '<span>%s</span>' % (html)


def _prepare_request(feed_url, etag, async=False, follow_redirects=True):
    # logger.info('Fetching feed feed_url:%s etag:%s', feed_url, etag)
    kwargs = {
        'url': feed_url,
        'headers': {
            'User-Agent': 'PourOver/1.0 +https://adn-pourover.appspot.com/'
        },
        'follow_redirects': follow_redirects
    }

    if etag:
        kwargs['headers']['If-None-Match'] = etag

    if async:
        rpc = urlfetch.create_rpc(deadline=20)
        urlfetch.make_fetch_call(rpc, **kwargs)

        return rpc
    else:
        return urlfetch.fetch(**kwargs)


def find_feed_url(feed, resp):
    if feed.bozo == 1 and len(feed.entries) == 0:
        content_type = resp.headers.get('Content-Type')
        logger.info('Feed failed bozo detection feed_url:%s content_type:%s', resp.final_url, content_type)
        if content_type and content_type.startswith('text/html'):
            # If we have this lets try and find a feed
            logger.info('Feed might be a web page trying to find feed_url:%s', resp.final_url)
            soup = BeautifulSoup(resp.content)
            # The thinking here is that the main RSS feed will be shorter in length then any others
            links = [x.get('href') for x in soup.findAll('link', type='application/rss+xml')]
            links += [x.get('href') for x in soup.findAll('link', type='application/atom+xml')]
            shortest_link = None
            for link in links:
                if shortest_link is None:
                    shortest_link = link
                elif len(link) < len(shortest_link):
                    shortest_link = link

            return shortest_link

    return None


def fetch_feed_url(feed_url, etag=None, update_url=False, rpc=None):
    # Handle network issues here, handle other exceptions where this is called from

    # GAE's built in urlfetch doesn't expose what HTTP Status caused a request to follow
    # a redirect. Which is important in this case because on 301 we are suppose to update the
    # feed URL in our database. So, we have to write our own follow redirect path here.

    max_redirects = 5
    redirects = 0
    try:
        while redirects < max_redirects:
            redirects += 1
            if rpc is None:
                resp = _prepare_request(feed_url, etag, async=False)
            else:
                resp = rpc.get_result()

            if resp.status_code not in (301, 302, 307):
                break

            rpc = None
            location = resp.headers.get('Location')
            if not location:
                logger.info('Failed to follow redirects for %s', feed_url)
                raise FetchException('Feed URL has a bad redirect')

            feed_url = location

            # On permanent redirect update the feed_url
            if resp.status_code == 301:
                update_url = feed_url

    except urlfetch.DownloadError:
        logger.info('Failed to download feed: %s', feed_url)
        raise FetchException('Failed to fetch that URL.')
    except urlfetch.DeadlineExceededError:
        logger.info('Feed took too long: %s', feed_url)
        raise FetchException('URL took to long to fetch.')
    except urlfetch.InvalidURLError:
        logger.info('Invalud URL: %s', feed_url)
        raise FetchException('The URL for this feeds seems to be invalid.')

    if resp.status_code not in VALID_STATUS:
        raise FetchException('Could not fetch feed. feed_url:%s status_code:%s final_url:%s' % (feed_url, resp.status_code, resp.final_url))

    # Feed hasn't been updated so there isn't a feed
    if resp.status_code == 304:
        return None, resp

    feed = feedparser.parse(resp.content)

    feed.update_url = update_url

    return feed, resp


def guid_for_item(item):
    return item.get('guid', item.get('link'))


def parse_style_tag(text):
    if not text:
        return text
    text = text.strip()
    attrs = text.split(';')
    attrs = filter(None, map(lambda x: x.strip(), attrs))
    attrs = map(lambda x: x.split(':'), attrs)
    # logger.info('attrs: %s', attrs)
    return {x[0].strip(): x[1].strip() for x in attrs}


def find_thumbnail(item):
    min_d = 200
    max_d = 1000
    media_thumbnails = item.get('media_thumbnail') or []
    for thumb in media_thumbnails:
        w = int(thumb.get('width', 0))
        h = int(thumb.get('height', 0))
        if all([w, h, w >= min_d, w <= max_d, h >= min_d, w <= max_d]):
            return {
                'thumbnail_image_url': thumb['url'],
                'thumbnail_image_width': int(thumb['width']),
                'thumbnail_image_height': int(thumb['height'])
            }

    soup = BeautifulSoup(item.get('summary', ''))
    for image in soup.findAll('img'):
        w = image.get('width', 0)
        h = image.get('height', 0)
        if not (w and h):
            style = parse_style_tag(image.get('style'))
            if style:
                w = style.get('width', w)
                h = style.get('height', h)

        if not(w and h):
            continue

        w, h = map(lambda x: x.replace('px', ''), (w, h))

        try:
            w = int(w)
            h = int(h)
        except:
            continue

        if all([w, h, w >= min_d, w <= max_d, h >= min_d, w <= max_d]):
            return {
                'thumbnail_image_url': image['src'],
                'thumbnail_image_width': w,
                'thumbnail_image_height': h,
            }

    return None


def find_video_src_url(item):
    summary = item.get('summary', item.get('content'))
    if not summary:
        return None, None

    soup = BeautifulSoup(summary)

    possible_embeds = soup.findAll('iframe')
    possible_embeds += soup.findAll('embed')

    for embed in possible_embeds:
        src_url = embed.get('src')
        urlparts = urlparse(src_url)
        logger.info('Potnetial vidoe: %s', src_url)
        if urlparts.netloc.endswith('youtube.com'):
            return src_url, 'youtube'

        if urlparts.netloc.endswith('vimeo.com'):
            return src_url, 'vimeo'

    return None, None

# http://stackoverflow.com/questions/4356538/how-can-i-extract-video-id-from-youtubes-link-in-python
def normalize_youtube_link(url):
    """
    Examples:
    - http://youtu.be/SA2iWivDJiE
    - http://www.youtube.com/watch?v=_oPAwA_Udwc&feature=feedu
    - http://www.youtube.com/embed/SA2iWivDJiE
    - http://www.youtube.com/v/SA2iWivDJiE?version=3&amp;hl=en_US
    """
    video_id = None
    query = urlparse(url)
    if query.hostname == 'youtu.be':
        video_id = query.path[1:]
    if query.hostname in ('www.youtube.com', 'youtube.com'):
        if query.path == '/watch':
            p = parse_qs(query.query)
            video_id = p['v'][0]
        if query.path[:7] == '/embed/':
            video_id = query.path.split('/')[2]
        if query.path[:3] == '/v/':
            video_id = query.path.split('/')[2]
    # fail?
    return 'http://www.youtube.com/watch?v=%s' % (video_id)


OEMBED_ENDPOINTS = {
    'vimeo': 'http://vimeo.com/api/oembed.json',
    'youtube': 'http://www.youtube.com/oembed',
}


def find_video_oembed(item):
    url, oembed_provider = find_video_src_url(item)
    if not url or not oembed_provider:
        return None

    if url.startswith('//'):
        url = 'http:' + url

    if oembed_provider == 'youtube':
        url = normalize_youtube_link(url)

    if not url:
        return None

    params = {
        'url': url
    }

    query_string = urllib.urlencode(params)
    resp = urlfetch.fetch(url='%s?%s' % (OEMBED_ENDPOINTS[oembed_provider], query_string), method='GET')
    # logger.info('Trying to fetch oembed data url:%s status_code:%s', url, resp.status_code)
    if resp.status_code != 200:
        return None
    # logger.info('Found video provider:%s url:%s embed:%s', oembed_provider, url, json.loads(resp.content))
    return json.loads(resp.content)


def get_link_for_item(feed, item):
    feed_link = feed.feed_url
    main_item_link = item.get('link')

    # If the user hasn't turned on linked list mode
    # return the main_item_link
    if not feed.linked_list_mode:
        return main_item_link

    # if the feed is so malformed it doesn't link to it's self then
    # just return the main item link
    if not feed_link:
        return main_item_link

    parsed_feed_link = urlparse(feed_link)
    parsed_item_link = urlparse(main_item_link)

    # If the main link has the same root domain as the feed
    # This is linking back to the blog already so return
    # The main link.
    if parsed_feed_link.netloc == parsed_item_link.netloc:
        return main_item_link

    # If we are still here, we should now look through the alternate links
    links = item.get('links', [])
    for link in links:
        href = link.get('href')
        if not href:
            continue

        parsed_link = urlparse(href)
        # If we find an alternate link that matches domains
        # we make the assumption that this is the permalink back to the blog
        if parsed_link.netloc == parsed_feed_link.netloc:
            return href

    # If we are still here we now need to look through the links that are in the content
    soup = BeautifulSoup(item.get('summary', ''))
    links = soup.findAll('a')

    # No links, then we are out of look return the main_item_link
    if not links:
        return main_item_link

    # Right now lets just try this on the last link
    last_link = links[-1]
    # logger.info('Last link: %s', last_link)
    href = last_link.get('href')
    parsed_link = urlparse(href)
    # logger.info('Last link parsed: %s %s %s', parsed_link.netloc, parsed_feed_link.netloc, parsed_link)
    # If the domains match lets use this as the URL
    if parsed_link.netloc == parsed_feed_link.netloc:
        return href

    # Finally lets try a last ditch custom method
    # we can just ask the user to change up their content so we can find something in it
    permalink = soup.find('a', {'rel': 'permalink'})
    if permalink:
        href = permalink.get('href')
        if href:
            return href

    return main_item_link


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

    def to_json(self, include=None, feed=None, format=False):
        include = include or []
        data = {}
        for attr in include:
            data[attr] = getattr(self, attr, None)

        if self.overflow:
            data['overflow_reason'] = OVERFLOW_REASON.for_display(self.overflow_reason)

        if self.key:
            data['id'] = self.key.id()

        feed = feed or self.key.parent().get()
        if format:
            data['html'] = build_html_from_post(self.format_for_adn(feed))
            if feed.include_thumb and self.thumbnail_image_url:
                data['thumbnail_image_url'] = self.thumbnail_image_url

            if feed.include_video and self.video_oembed:
                data['thumbnail_image_url'] = self.video_oembed['thumbnail_url']

        return data

    def get_short_url(self, link, feed):
        if self.short_url:
            return self.short_url

        params = {
            'login': feed.bitly_login,
            'apiKey': feed.bitly_api_key,
            'longUrl': link,
        }

        query_string = urllib.urlencode(params)
        resp = urlfetch.fetch(url='https://api-ssl.bitly.com/v3/shorten?%s' % (query_string), method='GET')
        if resp.status_code == 200:
            logger.info('url: %s Resp content: %s', 'https://api-ssl.bitly.com/v3/shorten?%s' % (query_string), resp.content)
            resp_json = json.loads(resp.content)
            if resp_json['status_code'] == 200:
                link = resp_json['data']['url']
                self.short_url = link
                self.put()
                return link

        return None

    def format_for_adn(self, feed):
        post_text = self.title
        links = []
        summary_text = ''
        if feed.include_summary:
            summary_text = strip_html_tags(self.summary)
            summary_text = ellipse_text(summary_text, 140)

        if self.feed_item:
            link = get_link_for_item(feed, self.feed_item)
        else:
            link = self.link

        link = append_query_string(link, params={'utm_source': 'PourOver', 'utm_medium': 'App.net'})

        # If viewing feed from preview don't shorten urls
        preview = getattr(feed, 'preview', False)
        if feed.bitly_login and feed.bitly_api_key and not preview:
            short_url = self.get_short_url(link, feed)
            if short_url:
                link = short_url

        # Starting out it should be as long as it can be
        max_chars = MAX_CHARS
        max_link_chars = 40
        ellipse_link_text = ellipse_text(link, max_link_chars)
        # If the link is to be included in the text we need to make sure we reserve enough space at the end
        if feed.format_mode == FORMAT_MODE.TITLE_THEN_LINK:
            max_chars -= len(' ' + ellipse_link_text)

        # Should be some room for a description
        if len(post_text) < (max_chars - 40) and summary_text:
            post_text = u'%s\n%s' % (post_text, summary_text)

        post_text = ellipse_text(post_text, max_chars)
        if feed.format_mode == FORMAT_MODE.TITLE_THEN_LINK:
            post_text += ' ' + ellipse_link_text

        if feed.format_mode == FORMAT_MODE.TITLE_THEN_LINK:
            links.insert(0, (link, ellipse_link_text))
        else:
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

        media_annotation = None
        # logger.info('Info %s, %s', include_thumb, self.thumbnail_image_url)
        if feed.include_thumb and self.thumbnail_image_url:
            media_annotation = {
                "type": "net.app.core.oembed",
                "value": {
                    "version": "1.0",
                    "type": "photo",
                    "title": self.title,
                    "width": self.thumbnail_image_width,
                    "height": self.thumbnail_image_height,
                    "url": self.thumbnail_image_url,
                    "thumbnail_width": self.thumbnail_image_width,
                    "thumbnail_height": self.thumbnail_image_height,
                    "thumbnail_url": self.thumbnail_image_url,
                    "embeddable_url": self.link,
                }
            }

        if feed.include_video and self.video_oembed:
            oembed = self.video_oembed
            oembed['embeddable_url'] = self.link
            media_annotation = {
                "type": "net.app.core.oembed",
                "value": oembed
            }

        if media_annotation:
            post['annotations'].append(media_annotation)

        lang = get_language(self.language)
        if lang:
            post['annotations'].append({
                "type": "net.app.core.language",
                "value": {
                    "language": lang,
                }
            })

        if self.author:
            post['annotations'].append({
                "type": "com.appspot.pourover-adn.item.author",
                "value": {
                    "author": self.author,
                }
            })

        if self.tags:
            post['annotations'].append({
                "type": "com.appspot.pourover-adn.item.tags",
                "value": {
                    "tags": self.tags,
                }
            })

        return post

    @classmethod
    def entry_preview(cls, entries, feed, format=False):
        return [entry.to_json(feed=feed, format=format) for entry in entries]

    @classmethod
    def entry_preview_for_feed(cls, feed):
        parsed_feed, resp = fetch_feed_url(feed.feed_url)

        # Try and fix bad feed_urls on the fly
        new_feed_url = find_feed_url(parsed_feed, resp)
        if new_feed_url:
            parsed_feed, resp = fetch_feed_url(new_feed_url, update_url=new_feed_url)

        entries = []
        for item in parsed_feed.entries:
            entry = cls.prepare_entry_from_item(parsed_feed, item, feed=feed)
            if entry:
                entries.append(entry)

        return cls.entry_preview(entries, feed, format=True)

    @classmethod
    def prepare_entry_from_item(cls, rss_feed, item, feed, overflow=False, overflow_reason=None, published=False):
        title_detail = item.get('title_detail')
        title = item.get('title', 'No Title')

        # If the title is HTML then we need to decode it to some kind of usable text
        # Definitely need to decode any entities
        if title_detail:
            if title_detail['type'] == u'text/html':
                title = BeautifulSoup(title).text

        feed_link = rss_feed.get('feed') and rss_feed.feed.get('link')
        link = get_link_for_item(feed, item)

        # We can only store a title up to 500 chars
        title = title[0:499]
        guid = guid_for_item(item)
        if len(guid) > 500:
            logger.warn('Found a guid > 500 chars link: %s item: %s', guid, item)
            return None

        if not link:
            logger.warn("Item found without link skipping item: %s", item)
            return None

        if len(link) > 500:
            logger.warn('Found a link > 500 chars link: %s item: %s', link, item)
            return None

        if not guid:
            logger.warn("Item found without guid skipping item: %s", item)
            return None

        summary = item.get('summary', '')
        kwargs = dict(guid=guid, title=title, summary=summary, link=link,
                      published=published, overflow=overflow, overflow_reason=overflow_reason)

        if feed:
            kwargs['parent'] = feed.key

        try:
            thumbnail = find_thumbnail(item)
            if thumbnail:
                kwargs.update(thumbnail)
        except Exception, e:
            logger.info("Exception while trying to find thumbnail %s", e)

        if feed.language:
            kwargs['language'] = feed.language

        if 'tags' in item:
            kwargs['tags'] = filter(None, [x['term'] for x in item.tags])

        if 'author' in item and item.author:
            kwargs['author'] = item.author

        if feed.include_video:
            embed = find_video_oembed(item)
            if embed:
                kwargs['video_oembed'] = embed

        kwargs['feed_item'] = item

        entry = cls(**kwargs)

        return entry

    @classmethod
    def create_from_feed_and_item(cls, feed, item, overflow=False, overflow_reason=None, rss_feed=None):
        entry = cls.query(cls.guid == guid_for_item(item), ancestor=feed.key).get()
        published = False
        created = False
        if overflow:
            published = True
        if not entry:
            entry = cls.prepare_entry_from_item(rss_feed, item, feed, overflow, overflow_reason, published)
            if entry:
                entry.put()
                created = True

        return entry, created

    def publish_entry(self, feed):
        feed = self.key.parent().get()
        user = feed.key.parent().get()
        # logger.info('Feed settings include_summary:%s, include_thumb: %s', feed.include_summary, feed.include_thumb)
        post = self.format_for_adn(feed)
        try:
            resp = urlfetch.fetch('https://alpha-api.app.net/stream/0/posts', payload=json.dumps(post), deadline=30, method='POST', headers={
                'Authorization': 'Bearer %s' % (user.access_token, ),
                'Content-Type': 'application/json',
            })
        except Exception, e:
            logger.exception('Failed to post Post: %s' % (post))
            return

        if resp.status_code == 401:
            feed.status = FEED_STATE.NEEDS_REAUTH
            feed.put()
        elif resp.status_code == 200:
            post_obj = json.loads(resp.content)
            logger.info('Published entry key=%s -> post_id=%s: %s', self.key.urlsafe(), post_obj['data']['id'], post)
        else:
            logger.warn("Couldn't post entry key=%s. Error: %s Post:%s", self.key.urlsafe(), resp.content, post)
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
        parsed_feed, resp = fetch_feed_url(feed.feed_url, feed.etag, rpc=getattr(feed, 'rpc', None))
        if getattr(feed, 'first_time', None):
            # Try and fix bad feed_urls on the fly
            new_feed_url = find_feed_url(parsed_feed, resp)
            if new_feed_url:
                parsed_feed, resp = fetch_feed_url(new_feed_url, update_url=new_feed_url)

        drain_queue = False
        # There should be no data in here anyway
        if resp.status_code != 304:
            etag = resp.headers.get('ETag')

            modified_feed = False
            # Update feed location
            if parsed_feed.update_url:
                feed.feed_url = parsed_feed.update_url
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
                feed.put()

            num_created_entries = 0
            for item in parsed_feed.entries:
                entry, created = cls.create_from_feed_and_item(feed, item, overflow=overflow, overflow_reason=overflow_reason,
                                                               rss_feed=parsed_feed)
                if created:
                    num_created_entries += 1

            if len(parsed_feed.entries) >= 5 and len(parsed_feed.entries) == num_created_entries:
                # could be a pretty epic fail
                drain_queue = True

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
                    entry.publish_entry(feed)

        if drain_queue:
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
    def reauthorize(cls, user):
        for feed in cls.query(cls.status == FEED_STATE.NEEDS_REAUTH, ancestor=user.key):
            feed.status = FEED_STATE.ACTIVE
            feed.put()

    def subscribe_to_hub(self):
        subscribe_data = {
            "hub.callback": url_for('feed_subscribe', feed_key=self.key.urlsafe(), _external=True),
            "hub.mode": 'subscribe',
            "hub.topic": self.feed_url,
            # 'hub.verify_token': self.verify_token, apparently this is no longer apart of PuSH v0.4
        }

        if self.hub_secret:
            subscribe_data['hub.secret'] = self.hub_secret

        logger.info('Hub: %s Subscribe Data: %s', self.hub, subscribe_data)
        form_data = urllib.urlencode(subscribe_data)
        resp = urlfetch.fetch(self.hub, method='POST', payload=form_data)
        logger.info('PuSH Subscribe request hub:%s status_code:%s response:%s', self.hub, resp.status_code, resp.content)

    @classmethod
    def process_new_feed(cls, feed, overflow, overflow_reason):
        # Sync pull down the latest feeds

        parsed_feed = Entry.update_for_feed(feed, overflow=overflow, overflow_reason=overflow_reason)
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
                feed.put()
                feed.subscribe_to_hub()

        return feed

    @classmethod
    def create_feed_from_form(cls, user, form):
        feed = cls(parent=user.key)
        form.populate_obj(feed)
        feed.put()

        # This triggers special first time behavior when fetching the feed
        feed.first_time = True

        return cls.process_new_feed(feed, overflow=True, overflow_reason=OVERFLOW_REASON.BACKLOG)

    @classmethod
    def create_feed(cls, user, feed_url, include_summary, schedule_period=PERIOD_SCHEDULE.MINUTE_5, max_stories_per_period=1):
        feed = cls(parent=user.key, feed_url=feed_url, include_summary=include_summary)
        feed.put()
        return cls.process_new_feed(feed)

    def prepare_request(self):
        self.rpc = _prepare_request(self.feed_url, self.etag, async=True)

    def to_json(self):
        return {
            'feed_url': self.feed_url,
            'feed_id': self.key.id(),
            'include_summary': self.include_summary,
            'format_mode': self.format_mode,
            'include_thumb': self.include_thumb,
            'linked_list_mode': self.linked_list_mode,
            'schedule_period': self.schedule_period,
            'max_stories_per_period': self.max_stories_per_period,
            'bitly_login': self.bitly_login,
            'bitly_api_key': self.bitly_api_key,
        }
