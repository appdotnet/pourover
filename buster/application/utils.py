import urllib

from bs4 import BeautifulSoup
from django.utils.encoding import smart_str
from django.utils.text import Truncator


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
    return item.get('guid', item.get('link'))


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
