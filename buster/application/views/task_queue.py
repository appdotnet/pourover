import logging
import uuid

import feedparser
from flask import request, url_for
from google.appengine.ext import deferred
from google.appengine.api.taskqueue import Task, Queue
from google.appengine.ext import ndb

from application import app
from application.constants import BATCH_SIZE, UPDATE_INTERVAL_TO_MINUTES
from application.models import FEED_TYPE_TO_CLASS, Entry, Feed, Stat
from application.prospective import RssFeed
from application.utils import write_epoch_to_stat

from view_utils import jsonify, jsonify_error

logger = logging.getLogger(__name__)


@app.route('/api/feeds/poll', methods=['POST'])
@app.route('/api/backend/feeds/poll', methods=['POST'], endpoint="tq_feed_poll-canonical")
@ndb.synctasklet
def tq_feed_poll():
    """Poll some feeds feed"""
    if not request.headers.get('X-AppEngine-QueueName'):
        raise ndb.Return(jsonify_error(message='Not a Task call'))

    keys = request.form.get('keys')
    if not keys:
        logger.info('Task Queue poll no keys')
        raise ndb.Return(jsonify_error(code=500))

    success = 0
    errors = 0
    entries_created = 0
    ndb_keys = [ndb.Key(urlsafe=key) for key in keys.split(',')]
    feeds = yield ndb.get_multi_async(ndb_keys)
    feeds = filter(lambda x: not getattr(x, 'use_external_poller', False), feeds)
    logger.info('Got %d feed(s) for polling', len(feeds))
    futures = []

    for i, feed in enumerate(feeds):
        if not feed:
            errors += 1
            logger.info("Couldn't find feed for key: %s", ndb_keys[i])
            continue
        futures.append((i, feed.process_feed(None, None)))

    for i, future in futures:
        parsed_feed = None
        try:
            parsed_feed, num_new_entries = yield future
            entries_created += num_new_entries
            success += 1
        except:
            errors += 1
            feed = feeds[i]
            logger.exception('Failed to update feed:%s, i=%s' % (feed.feed_url, i))

    yield write_epoch_to_stat(Stat, 'poll_job')
    logger.info('Polled feeds entries_created: %s success: %s errors: %s', entries_created, success, errors)

    raise ndb.Return(jsonify(status='ok'))

tq_feed_poll.login_required = False


@ndb.tasklet
def inbound_feed_process(feed_key, feed_data, etag, last_hash):
    feed = ndb.Key(urlsafe=feed_key).get()

    parsed_feed = feedparser.parse(feed_data)

    new_guids, old_guids = yield feed.process_inbound_feed(parsed_feed, overflow=False)
    yield feed.publish_inbound_feed(skip_queue=False)

    if etag:
        feed.etag = etag
    else:
        logger.info('Missing an updated etag for feed: %s', feed_key)

    if last_hash:
        feed.last_fetched_content_hash = last_hash
    else:
        logger.info('Missing an updated hash for feed: %s', feed_key)

    yield feed.clear_error()
    yield feed.put_async()

    logger.info(u'Saving feed: %s new_items: %s old_items: %s', feed_key, len(new_guids), len(old_guids))
    raise ndb.Return()


@app.route('/api/backend/feeds/subscribe/app/task', methods=['POST'], endpoint="tq_inbound_feed")
@ndb.synctasklet
def tq_inbound_feed():
    if request.headers.get('X-Appengine-Queuename') != 'inbound-posts':
        raise ndb.Return(jsonify_error(message='Not a cron call'))

    feed_key = request.form.get('feed_key')
    feed_data = request.form.get('feed_data')
    etag = request.form.get('etag')
    last_hash = request.form.get('last_hash')

    logger.info('Task to process inbound feed: %s', feed_key)
    yield inbound_feed_process(feed_key, feed_data, etag, last_hash)
    raise ndb.Return(jsonify(status='ok'))

tq_inbound_feed.login_required = False


@app.route('/api/feeds/<feed_key>/subscribe/app', methods=['POST'])
@app.route('/api/backend/feeds/<feed_key>/subscribe/app', methods=['POST'])
@ndb.synctasklet
def feed_push_update_app(feed_key):
    feed = ndb.Key(urlsafe=feed_key).get()
    if not feed:
        raise ndb.Return(jsonify_error('Unknown feed'))

    noop = request.args.get('noop')
    if noop:
        logger.info('Noop feed publish %s because off testing', feed_key)
        raise ndb.Return(jsonify(status='ok'))

    post_data = {
        'feed_key': feed_key,
        'feed_data': request.stream.read(),
        'etag': request.args.get('etag'),
        'last_hash': request.args.get('last_hash'),
    }

    yield inbound_feed_process(**post_data)
    # yield Queue('inbound-posts').add_async(Task(url=url_for('tq_inbound_feed'), method='POST', params=post_data))
    yield write_epoch_to_stat(Stat, 'external_poll_post_feed')
    raise ndb.Return(jsonify(status='ok'))

feed_push_update_app.app_token_required = True
feed_push_update_app.login_required = False


@app.route('/api/feeds/<feed_key>/update/feed_url', methods=['POST'])
@app.route('/api/backend/feeds/<feed_key>/update/feed_url', methods=['POST'])
@ndb.synctasklet
def update_feed_url(feed_key):
    feed = ndb.Key(urlsafe=feed_key).get()
    if not feed:
        raise ndb.Return(jsonify_error('Unknown feed'))

    logger.info("Updating feed: %s old feed url: %s new feed url: %s", feed_key, feed.feed_url, request.form.get('feed_url'))
    feed.feed_url = request.form.get('feed_url')

    noop = request.form.get('noop')
    if noop:
        logger.info('Noop feed_url update: feed: %s because off testing', feed_key)
        raise ndb.Return(jsonify(status='ok'))

    yield feed.put_async()

    raise ndb.Return(jsonify(status='ok'))

update_feed_url.app_token_required = True
update_feed_url.login_required = False


@app.route('/api/feeds/<feed_key>/error', methods=['POST'])
@app.route('/api/backend/feeds/<feed_key>/error', methods=['POST'])
@ndb.synctasklet
def update_feed_for_error(feed_key):
    feed = ndb.Key(urlsafe=feed_key).get()
    if not feed:
        raise ndb.Return(jsonify_error('Unknown feed'))

    logger.info("Incrementing error count for feed: %s errors: %s", feed_key, feed.error_count)

    noop = request.form.get('noop')
    if noop:
        logger.info('Noop feed error feed: %s because off testing', feed_key)
        raise ndb.Return(jsonify(status='ok'))

    yield feed.track_error()

    raise ndb.Return(jsonify(status='ok'))

update_feed_for_error.app_token_required = True
update_feed_for_error.login_required = False

DEFAULT_POLLING_BUCKET = 0


@app.route('/api/feeds/all/update/<int:interval_id>')
@app.route('/api/backend/feeds/all/update/<int:interval_id>')
@ndb.synctasklet
def update_all_feeds(interval_id):
    """Update all feeds for a specific interval"""
    if request.headers.get('X-Appengine-Cron') != 'true':
        raise ndb.Return(jsonify_error(message='Not a cron call'))

    for feed_type, feed_class in FEED_TYPE_TO_CLASS.iteritems():
        feeds = Feed.for_interval(interval_id)
        success = 0
        more = True
        cursor = None
        futures = []
        while more:
            feeds_to_fetch, cursor, more = yield feeds.fetch_page_async(BATCH_SIZE, start_cursor=cursor)
            feeds_to_fetch = filter(lambda x: getattr(x, 'external_polling_bucket', DEFAULT_POLLING_BUCKET) == DEFAULT_POLLING_BUCKET, feeds_to_fetch)
            keys = ','.join([x.key.urlsafe() for x in feeds_to_fetch])
            if not keys:
                continue

            futures.append(Queue('poll').add_async(Task(url=url_for('tq_feed_poll-canonical'), method='POST', params={'keys': keys})))
            success += 1

    for future in futures:
        yield future

    logger.info('queued poll for %d feeds at interval_id=%s', success, interval_id)

    raise ndb.Return(jsonify(status='ok'))

update_all_feeds.login_required = False


@app.route('/api/feeds/post/job', methods=['POST'])
@app.route('/api/backend/feeds/post/job', methods=['POST'], endpoint="tq_feed_post-canonical")
@ndb.synctasklet
def tq_feed_post_job():
    """Post some feeds feed"""
    if not request.headers.get('X-AppEngine-QueueName'):
        raise ndb.Return(jsonify_error(message='Not a Task call'))

    keys = request.form.get('keys')
    if not keys:
        logger.info('Task Queue post no keys')
        raise ndb.Return(jsonify_error(code=500))

    success = 0
    errors = 0
    num_posted = 0
    ndb_keys = [ndb.Key(urlsafe=key) for key in keys.split(',')]
    feeds = yield ndb.get_multi_async(ndb_keys)
    logger.info('Got %d feed(s) for posting', len(feeds))
    futures = []

    for feed in feeds:
        futures.append((feed, Entry.publish_for_feed(feed)))

    for feed, future in futures:
        try:
            num_posts = yield future
            if num_posts is not None:
                num_posted += num_posts
            success += 1
        except:
            errors += 1
            if feed:
                logger.exception('Failed to Publish feed:%s' % (feed.feed_url, ))
            else:
                logger.exception('Failed to publish non-exsistant feed')

    logger.info('Post Feeds success:%s errors: %s num_posted: %s', success, errors, num_posted)
    raise ndb.Return(jsonify(status='ok'))


tq_feed_post_job.login_required = False


@app.route('/api/feeds/all/post')
@app.route('/api/backend/feeds/all/post')
@ndb.synctasklet
def post_all_feeds():
    """Post all new items for feeds for a specific interval"""
    if request.headers.get('X-Appengine-Cron') != 'true':
        raise ndb.Return(jsonify_error(message='Not a cron call'))

    logger.info('Starting a post job')
    futures = []
    for feed_type, feed_class in FEED_TYPE_TO_CLASS.iteritems():
        feeds = feed_class.query(feed_class.is_dirty == True)
        logger.info("Got some feeds_count: %s feeds_type: %s", feeds.count(), feed_type)
        success = 0
        more = True
        cursor = None
        while more:
            feeds_to_fetch, cursor, more = yield feeds.fetch_page_async(BATCH_SIZE, start_cursor=cursor)
            keys = ','.join([x.key.urlsafe() for x in feeds_to_fetch])
            if not keys:
                continue
            futures.append(Queue().add_async(Task(url=url_for('tq_feed_post-canonical'), method='POST', params={'keys': keys})))
            success += len(feeds_to_fetch)
        logger.info('queued post for %d feeds feed_type:%s', success, feed_type)

    for future in futures:
        yield future

    logger.info('Finished Post Job')
    yield write_epoch_to_stat(Stat, 'post_job')
    raise ndb.Return(jsonify(status='ok'))

post_all_feeds.login_required = False


@app.route('/api/feeds/all/try/subscribe')
@app.route('/api/backend/feeds/all/try/subscribe')
@ndb.synctasklet
def try_push_resub():
    """Post all new items for feeds for a specific interval"""
    if request.headers.get('X-Appengine-Cron') != 'true':
        raise ndb.Return(jsonify_error(message='Not a cron call'))

    unsubscribed_feeds = Feed.query(Feed.hub != None, Feed.subscribed_at_hub == False)  # noqa
    qit = unsubscribed_feeds.iter()

    errors = 0
    success = 0
    count = 0

    futures = []

    while (yield qit.has_next_async()):
        feed = qit.next()
        futures.append((feed, Feed.subscribe_to_hub(feed)))

    for feed, future in futures:
        count += 1
        try:
            yield future
            success += 1
        except:
            errors += 1
            logger.exception('Failed to PuSH subscribe feed:%s' % (feed.feed_url, ))

    logger.info('Tried to call hub for num_unsubscribed_feeds:%s success:%s, errors:%s', count, success, errors)

    raise ndb.Return(jsonify(status='ok'))

try_push_resub.login_required = False


@app.route('/api/feeds/all', methods=['GET'])
@app.route('/api/backend/feeds/all', methods=['GET'])
@ndb.synctasklet
def all_feeds():
    """Post all new items for feeds for a specific interval"""

    def feed_to_dict(feed):
        return {
            'feed_key': feed.key.urlsafe(),
            'feed_url': feed.feed_url,
            'etag': feed.etag,
            'last_hash': feed.last_fetched_content_hash,
            'update_interval': UPDATE_INTERVAL_TO_MINUTES.get(feed.update_interval)
        }

    bucket = int(request.args.get('bucket_id', 1))

    feed_clss = [Feed, RssFeed]

    feeds_response = []
    for feed_cls in feed_clss:
        qit = feed_cls.query(feed_cls.external_polling_bucket == bucket)
        more = True
        cursor = None
        while more:
            feeds_to_fetch, cursor, more = yield qit.fetch_page_async(1000, start_cursor=cursor)
            feeds_response.extend((feed_to_dict(feed) for feed in feeds_to_fetch))

    poller_run_id = uuid.uuid4().hex

    logger.info('Poller run %s dispatched with %d feeds', poller_run_id, len(feeds_response))

    response = {
        'poller_run_id': poller_run_id,
        'feeds': feeds_response,
    }

    yield write_epoch_to_stat(Stat, 'external_poll_get_all_feeds')

    raise ndb.Return(jsonify(status='ok', data=response))

all_feeds.app_token_required = True
all_feeds.login_required = False


@app.route('/api/deferred/task', methods=['POST'])
@app.route('/api/backend/deferred/task', methods=['POST'], endpoint="tq_deferred-task")
@ndb.synctasklet
def deferred_task():
    if not request.headers.get('X-AppEngine-QueueName'):
        raise ndb.Return(jsonify_error(message='Not a Task call'))

    data = request.stream.read()
    try:
        deferred.run(data)
    except deferred.SingularTaskFailure:
        logger.debug("Failure executing task, task retry forced")
        raise ndb.Return(jsonify_error(code=408))
    except deferred.PermanentTaskFailure:
        logger.debug("Permanent Failure")
        raise ndb.Return(jsonify_error(code=500))

    raise ndb.Return(jsonify(status='ok'))

deferred_task.login_required = False
