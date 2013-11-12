import datetime
import hashlib
import logging


import feedparser
from google.appengine.ext import ndb
from google.appengine.api import urlfetch
from constants import VALID_STATUS
from utils import find_feed_url

logger = logging.getLogger(__name__)

# Monkeypatch feedparser
feedparser._HTMLSanitizer.acceptable_elements = set(list(feedparser._HTMLSanitizer.acceptable_elements) + ["object", "embed", "iframe", "param"])


class FetchException(Exception):
    pass


# Don't complain about this
ndb.add_flow_exception(FetchException)


@ndb.tasklet
def fetch_url(url, etag=None, user_agent=None):
    # Handle network issues here, handle other exceptions where this is called from

    # GAE's built in urlfetch doesn't expose what HTTP Status caused a request to follow
    # a redirect. Which is important in this case because on 301 we are suppose to update the
    # feed URL in our database. So, we have to write our own follow redirect path here.
    max_redirects = 5
    redirects = 0
    was_permanente_redirect = False
    ctx = ndb.get_context()
    try:
        while redirects < max_redirects:
            redirects += 1

            # logger.info('Fetching feed feed_url:%s etag:%s', feed_url, etag)
            kwargs = {
                'url': url,
                'headers': {
                    'User-Agent': user_agent or 'ADN Pour-Over/1.0 +https://adn-pourover.appspot.com/',
                },
                'follow_redirects': True,
                'deadline': 30,
                'headers': {
                    'Cache-Control': 'no-cache, must-revalidate'
                }
            }

            if etag:
                kwargs['headers']['If-None-Match'] = etag

            resp = yield ctx.urlfetch(**kwargs)

            if resp.status_code not in (301, 302, 307):
                break

            if resp.status_code == 301:
                was_permanente_redirect = True

            location = resp.headers.get('Location')
            if not location:
                logger.info('Failed to follow redirects for %s', url)
                raise FetchException('Feed URL has a bad redirect')

            url = location

    except urlfetch.DownloadError, e:
        logger.info('Failed to download feed: %s', url)
        logger.exception(e)
        raise FetchException('Failed to fetch that URL.')
    except urlfetch.DeadlineExceededError:
        logger.info('Feed took too long: %s', url)
        raise FetchException('URL took to long to fetch.')
    except urlfetch.InvalidURLError:
        logger.info('Invalid URL: %s', url)
        raise FetchException('The URL for this feeds seems to be invalid.')

    if resp.status_code not in VALID_STATUS:
        raise FetchException('Could not fetch url. url:%s status_code:%s final_url:%s resp:%s' % (url, resp.status_code, resp.final_url, resp.content))

    # Let upstream consumers know if they need to update their URL or not
    resp.was_permanente_redirect = was_permanente_redirect
    if was_permanente_redirect:
        # This replicates the behavior of the official urlfetch interface
        resp.final_url = location
    raise ndb.Return(resp)


@ndb.tasklet
def fetch_parsed_feed_for_url(feed_url, etag=None, user_agent=None):
    resp = yield fetch_url(feed_url, etag, user_agent)

    # Feed hasn't been updated so there isn't a feed
    if resp.status_code == 304:
        raise ndb.Return((None, resp))

    feed = feedparser.parse(resp.content)

    raise ndb.Return((feed, resp))


def hash_content(text):
    return hashlib.sha256(text).hexdigest()


# Rubber duck debugging for fetch_parsed_feed_for_feed
# We want to fetch a feed with an etag if we have one.
# If we get back a 304 we don't need to do anything we can just return None, resp
# Next, if the code wasn't a 304, we should still hash the content and check it against the saved content hash
# If they are the same, we should mock a 304 by changing status code. This will trigger the fast fail path upstream
# Finally, if the content hashes don't match. Lets save the new content hash and carry on as normal
@ndb.tasklet
def fetch_parsed_feed_for_feed(feed):
    now = datetime.datetime.now()
    if feed.feed_url == 'http://blog.app.net/feed/':
        logger.info('debugblogpoll: Fetching %s', feed.feed_url)

    try:
        resp = yield fetch_url(feed.feed_url, feed.etag, feed.user_agent)
    except FetchException, e:
        # If we haven't been able to fetch this feed in the last 24 hours lets disable it
        # This doesn't do anything right now, just want to make sure we are doing this correctly
        # logger.info('Failed fetch url: %s Last last_successful_fetch: %s', feed.feed_url, feed.last_successful_fetch)
        # if feed.last_successful_fetch and feed.last_successful_fetch < now - datetime.timedelta(days=1):
        #     feed.feed_disabled = True
        #     logging.warning('Would have deleted feed:%s', feed.key.urlsafe())
        #     yield feed.put_async()

        raise e

    feed_preview = getattr(feed, 'preview', None)

    # Trying to reduce the number of writes per fetch
    # feed.last_successful_fetch = now
    # if feed_preview is None:
    #    yield feed.put_async()

    if feed.feed_url == 'http://blog.app.net/feed/':
        logger.info('debugblogpoll: fetched blog content: %s', resp.content)

    if resp.status_code == 304:
        if feed.feed_url == 'http://blog.app.net/feed/':
            logger.info('debugblogpoll: got 304 from the blog')

        raise ndb.Return((None, resp, feed))

    content_hash = hash_content(resp.content)
    if feed.feed_url == 'http://blog.app.net/feed/':
        logger.info('debugblogpoll: comparing content hash old: %s new: %s', feed.last_fetched_content_hash, content_hash)

    if feed.last_fetched_content_hash == content_hash:
        # Trigger 304 path
        resp.status_code = 304
        if feed.feed_url == 'http://blog.app.net/feed/':
            logger.info('debugblogpoll: matched on hash nothing new')

        raise ndb.Return((None, resp, feed))

    # No mater what happens after this point we are going to save the feed obj
    feed.last_fetched_content_hash = content_hash

    # parsed_feed, resp = yield fetch_parsed_feed_for_url(feed.feed_url, feed.etag)
    if getattr(feed, 'first_time', None) or feed_preview:
        # Try and fix bad feed_urls on the fly
        new_feed_url = find_feed_url(resp, feed.feed_url)
        logger.info('New feed trying to fetch the correct url old url: %s new_url: %s', feed.feed_url, new_feed_url)
        if new_feed_url:
            resp = yield fetch_url(new_feed_url)
            feed.feed_url = new_feed_url

    if feed_preview is None:
        yield feed.put_async()

    parsed_feed = feedparser.parse(resp.content)

    raise ndb.Return((parsed_feed, resp, feed))
