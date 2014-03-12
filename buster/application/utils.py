import logging
import hashlib
import urllib
from urlparse import urljoin
import time

from bs4 import BeautifulSoup
from django.utils.encoding import smart_str
from django.utils.text import Truncator
from google.appengine.ext import ndb


logger = logging.getLogger(__name__)


def smart_urlencode(params, force_percent=False):
    if force_percent:
        qf = urllib.quote
    else:
        qf = urllib.quote_plus

    parts = ('='.join((qf(smart_str(k)), qf(smart_str(v)))) for k, v in params.iteritems())

    return '&'.join(parts)


def append_query_string(url, params=None, force_percent=False):
    if not params:
        return url

    if '#' in url:
        parts = url.split('#', 1)
        parts[1] = '#' + parts[1]
    else:
        parts = [url]

    if '?' in url:
        parts.insert(1, '&')
    else:
        parts.insert(1, '?')

    parts.insert(2, smart_urlencode(params, force_percent=force_percent))

    return ''.join(parts)


def guid_for_item(item):
    guid = item.get('guid')
    if guid:
        return guid

    guid = item.get('link')
    if guid:
        return guid

    guid = item.get('published')
    if guid:
        return guid

    summary = item.get('summary', u'No content')
    summary = summary.encode('utf-8', 'replace')
    return hashlib.sha224(summary).hexdigest()


def strip_html_tags(html):
    if html is None:
        return None
    else:
        return ''.join(BeautifulSoup(html).findAll(text=True))


def ellipse_text(text, max_chars):
    truncate = Truncator(text)

    return truncate.chars(max_chars, u"\u2026")


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


def find_feed_url(resp, feed_url):
    content_type = resp.headers.get('Content-Type')
    if content_type and content_type.startswith('text/html'):
        logger.info('Feed sent back content type html content_type:%s', content_type)
        soup = BeautifulSoup(resp.content)
        # The thinking here is that the main RSS feed will be shorter in length then any others
        links = [x.get('href') for x in soup.findAll('link', type='application/rss+xml')]
        links += [x.get('href') for x in soup.findAll('link', type='application/atom+xml')]
        shortest_link = None
        for link in links:
            link = urljoin(feed_url, link)
            if shortest_link is None:
                shortest_link = link
            elif len(link) < len(shortest_link):
                shortest_link = link

        return shortest_link

    return None


@ndb.tasklet
def write_epoch_to_stat(model, name):
    epoch_time = int(time.time())
    key = ndb.Key(model, name)
    stat = yield key.get_async()
    if not stat:
        stat = model(key=key, name=name)

    stat.value = unicode(epoch_time)
    yield stat.put_async()
    raise ndb.Return(stat)


@ndb.tasklet
def get_epoch_from_stat(model, name):
    key = ndb.Key(model, name)
    stat = yield key.get_async()
    if not stat:
        value = None
    else:
        value = stat.value

    raise ndb.Return(value)


def fit_to_box(w, h, max_w, max_h, expand=False):
    # proportionately scale a box defined by (w,h) so that it fits within a box defined by (max_w, max_h)
    # by default, only scaling down is allowed, unless expand=True, in which case scaling up is allowed
    if w < max_w and h < max_h and not expand:
        return (w, h)
    largest_ratio = max(float(w) / max_w, float(h) / max_h)
    new_height = int(float(h) / largest_ratio)
    new_width = int(float(w) / largest_ratio)
    return (new_width, new_height)


def dict_hash(_dict):
    _dict_items = _dict.items()
    _dict_items = sorted(_dict_items, key=lambda x: x[0])
    _dict_items = u''.join([unicode(item) for sublist in _dict_items for item in sublist])
    _dict_items = _dict_items.encode('utf-8', 'replace')
    return hashlib.sha224(_dict_items).hexdigest()
