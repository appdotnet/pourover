import urllib

from django.utils.encoding import smart_str


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
