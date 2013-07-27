import logging

import feedparser
from google.appengine.ext import ndb

from constants import VALID_STATUS

logger = logging.getLogger(__name__)

# Monkeypatch feedparser
feedparser._HTMLSanitizer.acceptable_elements = set(list(feedparser._HTMLSanitizer.acceptable_elements) + ["object", "embed", "iframe", "param"])

class FetchException(Exception):
    pass


# Don't complain about this
ndb.add_flow_exception(FetchException)


@ndb.tasklet
def fetch_feed_url(feed_url, etag=None, update_url=False, rpc=None):
    # Handle network issues here, handle other exceptions where this is called from

    # GAE's built in urlfetch doesn't expose what HTTP Status caused a request to follow
    # a redirect. Which is important in this case because on 301 we are suppose to update the
    # feed URL in our database. So, we have to write our own follow redirect path here.

    max_redirects = 5
    redirects = 0
    ctx = ndb.get_context()
    try:
        while redirects < max_redirects:
            redirects += 1

            # logger.info('Fetching feed feed_url:%s etag:%s', feed_url, etag)
            kwargs = {
                'url': feed_url,
                'headers': {
                    'User-Agent': 'PourOver/1.0 +https://adn-pourover.appspot.com/'
                },
                'follow_redirects': True
            }

            if etag:
                kwargs['headers']['If-None-Match'] = etag

            resp = yield ctx.urlfetch(**kwargs)

            if resp.status_code not in (301, 302, 307):
                break

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
        raise ndb.Return((None, resp))

    feed = feedparser.parse(resp.content)

    feed.update_url = update_url

    raise ndb.Return((feed, resp))