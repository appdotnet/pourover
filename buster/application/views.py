"""
views.py

URL route handlers
"""
import base64
import datetime
import hmac
import hashlib
import json
import logging
import uuid

from google.appengine.ext import ndb

import feedparser
from flask import request, render_template, g, Response, url_for, redirect
from google.appengine.api.taskqueue import Task, Queue
from google.appengine.api import mail
from flask_cache import Cache

from application import app
from constants import UPDATE_INTERVAL, FEED_TYPE, OVERFLOW_REASON, UPDATE_INTERVAL_TO_MINUTES, FEED_STATE
from models import Entry, Feed, Stat, Configuration, InstagramFeed, FEED_TYPE_TO_CLASS
from fetcher import FetchException, fetch_parsed_feed_for_feed
from utils import write_epoch_to_stat, get_epoch_from_stat

logger = logging.getLogger(__name__)

# Flask-Cache (configured to use App Engine Memcache API)
cache = Cache(app)
BATCH_SIZE = 50

class APIEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime.datetime, datetime.date)):
            return obj.ctime()
        elif isinstance(obj, datetime.time):
            return obj.isoformat()

        return json.JSONEncoder.default(self, obj)


def jsonify(**kwargs):
    return Response(json.dumps(kwargs, cls=APIEncoder), mimetype='application/json')


def jsonify_error(message='There was an error', code=404):
    resp = jsonify(status='error', message=message)
    resp.status_code = code

    return resp


@app.route('/', endpoint='index')
@app.route('/signup/', endpoint='signup')
@app.route('/login/', endpoint='login')
@app.route('/login/instagram/', endpoint='login_instagram')
@app.route('/logout/', endpoint='logout')
@app.route('/alerts_xyx/')
@app.route('/alerts_xyx/new/')
def index():
    return render_template('index.html')

index.login_required = False

@app.route('/alerts/', endpoint='channels')
def alerts():
    return redirect('https://directory.app.net/alerts/manage/')

alerts.login_required = False

@app.route('/alerts/new/', endpoint='channels')
def create_alerts():
    return redirect('https://directory.app.net/alerts/manage/create/')

create_alerts.login_required = False

@app.route('/feed/<feed_type>/<feed_id>/', endpoint='feed_point')
def feed_point(feed_type, feed_id=None):
    return render_template('index.html')

feed_point.login_required = False

@app.route('/alerts/<alert_id>/', endpoint='alerts_detail')
def alerts_detail(alert_id=None):
    return redirect('https://directory.app.net/alerts/manage/%s/' % alert_id)

alerts_detail.login_required = False

@app.route('/alerts_xyx/<alert_id>/')
def alerts_detail(alert_id=None):
    return render_template('index.html')

alerts_detail.login_required = False


@app.route('/api/me', methods=['GET'])
def me():
    """return current user"""
    return jsonify(status='ok', data=g.adn_user)


@app.route('/api/feeds', methods=['GET'])
def feeds():
    """List all examples"""
    users_feeds = []
    for feed_type in FEED_TYPE_TO_CLASS.values():
        users_feeds += [feed.to_json() for feed in feed_type.for_user(g.user) if feed.visible]
    return jsonify(status='ok', data=users_feeds)


@app.route('/api/feeds-for-channel/<int:channel_id>/', methods=['GET'])
def feeds_for_channel_id(channel_id):
    """List all examples"""

    users_feeds = [feed.to_json() for feed in FEED_TYPE_TO_CLASS[FEED_TYPE.RSS].for_user_and_channel(g.user, channel_id) if feed.visible]

    return jsonify(status='ok', data=users_feeds)


@app.route('/api/feeds', methods=['POST'])
def feed_create():
    """List all examples"""

    try:
        # Get feed type default to RSS feeds
        feed_type = int(request.form.get('feed_type', FEED_TYPE.RSS))
        feed_class = FEED_TYPE_TO_CLASS[feed_type]
        validation_form = feed_class.create_form
    except:
        return jsonify_error(status='error', message='Invalid feed type')

    form = validation_form(request.form)
    if not form.validate():
        return jsonify(status='error', message='The passed arguments failed validation')

    existing_feeds = feed_class.for_user_and_form(user=g.user, form=form)
    if existing_feeds.count():
        feed = existing_feeds.get()
        # Did we get a channel_id from the form
        channel_id = form.data.get('channel_id')
        # Update the channel id for this feed
        if channel_id:
            feed.channel_id = channel_id
            feed.put()
    else:
        feed = feed_class.create_feed_from_form(g.user, form).get_result()

    return jsonify(status='ok', data=feed.to_json())


@app.route('/api/feeds/validate', methods=['POST'])
@ndb.synctasklet
def feed_validate():
    """preview a feed"""
    feed_type = int(request.form.get('feed_type', 1))
    form = FEED_TYPE_TO_CLASS[feed_type].preview_form(request.form)
    if not form.validate():
        raise ndb.Return(jsonify(status='error', form_errors=form.errors))

    feed = Feed()
    form.populate_obj(feed)
    feed.preview = True
    error = None
    parsed_feed = None

    try:
        parsed_feed, resp, feed = yield fetch_parsed_feed_for_feed(feed)
        feed.update_feed_from_parsed_feed(parsed_feed)
        if len(parsed_feed.entries) == 0:
            error = 'The url you entred is not a valid feed.'
    except FetchException, e:
        error = unicode(e)
    except:
        error = 'Something went wrong while fetching your URL.'
        logger.exception('Feed Preview: Failed to update feed:%s' % (feed.feed_url, ))
    logger.info('Parsed feed: %s', parsed_feed)


    if error:
        raise ndb.Return(jsonify(status='error', message=error))

    raise ndb.Return(jsonify(status='ok', data=feed.to_json()))


@app.route('/api/feeds/<int:feed_type>/<int:feed_id>', methods=['GET'])
def feed(feed_type, feed_id):
    """Get a feed"""
    feed = FEED_TYPE_TO_CLASS[feed_type].get_by_id(feed_id, parent=g.user.key)
    if not feed:
        return jsonify_error(message="Can't find that feed")

    feed_data = feed.to_json()
    entries = [entry.to_dict(include=['guid', 'published', 'extra_info']) for entry in Entry.latest_for_feed(feed).fetch(10)]
    feed_data['entries'] = entries

    return jsonify(status='ok', data=feed_data)


@app.route('/api/feeds/<int:feed_type>/<int:feed_id>', methods=['POST'])
def feed_change(feed_type, feed_id):
    """Change a feed"""
    form = FEED_TYPE_TO_CLASS[feed_type].update_form(request.form)
    if not form.validate():
        return jsonify_error(message="Invalid update data")

    feed = FEED_TYPE_TO_CLASS[feed_type].get_by_id(feed_id, parent=g.user.key)
    if not feed:
        return jsonify_error(message="Can't find that feed")

    form.populate_obj(feed)
    feed.put()

    feed_data = feed.to_json()
    entries = [entry.to_dict(include=['title', 'link', 'published', 'published_at']) for entry in Entry.latest_for_feed(feed).fetch(10)]
    feed_data['entries'] = entries

    return jsonify(status='ok', data=feed_data)


@app.route('/api/feeds/<int:feed_type>/<int:feed_id>', methods=['DELETE'])
@ndb.synctasklet
def delete_feed(feed_type, feed_id):
    """Delete a feed"""
    feed = FEED_TYPE_TO_CLASS[feed_type].get_by_id(feed_id, parent=g.user.key)
    if not feed:
        raise ndb.Return(jsonify_error(message="Can't find that feed"))

    yield Entry.delete_for_feed(feed)
    yield feed.key.delete_async()
    raise ndb.Return(jsonify(status='ok'))


@app.route('/api/feeds/<int:feed_type>/<int:feed_id>/unpublished', methods=['GET'])
def unpublished_entries_for_feed(feed_type, feed_id):
    feed = FEED_TYPE_TO_CLASS[feed_type].get_by_id(feed_id, parent=g.user.key)
    if not feed:
        return jsonify_error(message="Can't find that feed")

    feed_data = feed.to_json()
    entries = [entry.to_json() for entry in Entry.latest_unpublished(feed).fetch(20)]
    feed_data['entries'] = entries

    return jsonify(status='ok', data=feed_data)


@app.route('/api/feeds/<int:feed_type>/<int:feed_id>/latest', methods=['GET'])
def published_entries_for_feed(feed_type, feed_id):
    feed = FEED_TYPE_TO_CLASS[feed_type].get_by_id(feed_id, parent=g.user.key)
    if not feed:
        return jsonify_error(message="Can't find that feed")

    feed_data = feed.to_json()
    entries = [entry.to_json() for entry in Entry.latest(feed, order_by='-published_at', include_overflow=True).fetch(20)]
    feed_data['entries'] = entries

    return jsonify(status='ok', data=feed_data)


@app.route('/api/feeds/<int:feed_type>/<int:feed_id>/preview', methods=['GET'])
def save_feed_preview(feed_type, feed_id):
    """preview a saved feed"""
    form = FEED_TYPE_TO_CLASS[feed_type].update_form(request.args)
    logger.info('form errors %s', form.errors)
    logger.info('form.publish_to_stream errors %s', form.publish_to_stream.errors)
    for errorMessages, fieldName in enumerate(form.errors):
        for err in errorMessages:
            logger.info("Feed errrors, %s", err)

    if not form.validate():
        return jsonify_error(message="Invalid update data")

    feed = FEED_TYPE_TO_CLASS[feed_type].get_by_id(feed_id, parent=g.user.key)
    if not feed:
        return jsonify_error(message="Can't find that feed")

    form.populate_obj(feed)
    feed.preview = True
    preview_entries = Entry.entry_preview(Entry.latest_for_feed_by_added(feed).fetch(3), feed, format=True)

    return jsonify(status='ok', data=preview_entries)


@app.route('/api/feeds/<int:feed_type>/<int:feed_id>/entries/<entry_id>/publish', methods=['POST'])
def feed_entry_publish(feed_type, feed_id, entry_id):
    """Get a feed"""
    logger.info('Manually publishing Feed:%s Entry: %s', feed_id, entry_id)

    key = ndb.Key(urlsafe=entry_id)
    feed = FEED_TYPE_TO_CLASS[feed_type].get_by_id(feed_id, parent=g.user.key)
    if not (feed and key.parent() == feed.key):
        return jsonify_error(message="Can't find that feed")

    entry = key.get()
    if not entry:
        return jsonify_error(message="Can't find that entry")

    entry.publish_entry(feed).get_result()
    entry.overflow = False
    entry.put()

    return jsonify(status='ok')

@app.route('/_ah/mail/<string:email>', methods=['POST'])
@ndb.synctasklet
def email_to_feed(email):
    logger.info('Email: %s', email)
    account, _ = email.split('@', 1)
    logger.info('Account: %s', account)
    unique_key, feed_type, version = account.split('_')
    feed_type, version = map(int, (feed_type, version))
    logger.info('unique_key: %s feed_type:%s version:%s', unique_key, feed_type, version)
    feed = FEED_TYPE_TO_CLASS[feed_type].for_email(unique_key)
    logger.info('Found feed: %s', feed)
    mail_message = mail.InboundEmailMessage(request.stream.read())
    entry = yield feed.create_entry_from_mail(mail_message)
    yield entry.publish_entry(feed)

    raise ndb.Return(jsonify(status='ok'))


email_to_feed.login_required = False


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


@app.route('/api/feeds/instagram/subscribe', methods=['GET'])
def instagram_subscribe():
    mode = request.args['hub.mode']
    challenge = request.args['hub.challenge']
    verify_token = request.args.get('hub.verify_token')

    if mode == 'subscribe':
        instagram_verify_token = Configuration.value_for_name('instagram_verify_token')
        if verify_token and verify_token != instagram_verify_token:
            logger.info('Failed verification feed.verify_token:%s GET verify_token:%s', instagram_verify_token, verify_token)
            return "Failed Verification", 400

        logger.info('Responding to instagram challange: %s', challenge)
        return challenge

instagram_subscribe.login_required = False


@app.route('/api/feeds/instagram/subscribe', methods=['POST'])
@ndb.synctasklet
def instagram_push_update():
    data = request.stream.read()
    instagram_client_secret = Configuration.value_for_name('instagram_client_secret')

    server_signature = request.headers.get('X-Hub-Signature', None)
    signature = hmac.new(str(instagram_client_secret), data, digestmod=hashlib.sha1).hexdigest()

    if server_signature != signature:
        logger.warn('Got PuSH subscribe POST from instagram w/o valid signature: sent=%s != expected=%s',
                    server_signature, signature)

        raise ndb.Return('')

    logger.info('Got PuSH body: %s', data)
    logger.info('Got PuSH headers: %s', request.headers)

    parsed_feed = json.loads(data)
    user_ids = [int(x.get('object_id')) for x in parsed_feed]
    feeds = InstagramFeed.query(InstagramFeed.user_id.IN(user_ids))

    cursor = None
    more = True
    keys = []
    while more:
        feed_keys, cursor, more = feeds.fetch_page(BATCH_SIZE, keys_only=True, start_cursor=cursor)
        keys += feed_keys

    keys = ','.join([x.urlsafe() for x in keys])
    if keys:
        yield Queue('poll').add_async(Task(url=url_for('tq_feed_poll-canonical'), method='POST', params={'keys': keys}))

    raise ndb.Return('ok')

instagram_push_update.login_required = False


@app.route('/api/feeds/<feed_key>/subscribe', methods=['GET'])
@app.route('/api/backend/feeds/<feed_key>/subscribe', methods=['GET'])
def feed_subscribe(feed_key):
    mode = request.args['hub.mode']
    challenge = request.args['hub.challenge']
    verify_token = request.args.get('hub.verify_token')

    if mode == 'subscribe':
        feed = ndb.Key(urlsafe=feed_key).get()
        # Only check this if they send back a verify token
        if verify_token and verify_token != feed.verify_token:
            logger.info('Failed verification feed.verify_token:%s GET verify_token:%s', feed.verify_token, verify_token)
            return "Failed Verification", 400

        if not feed:
            return "No feed", 404

        feed.subscribed_at_hub = True
        # If PuSH is enabled lets only poll these feeds every 15 minutes
        feed.update_interval = UPDATE_INTERVAL.MINUTE_15
        feed.put()
        logger.info('Responding to challange: %s', challenge)
        return challenge

feed_subscribe.login_required = False


@app.route('/api/feeds/<feed_key>/subscribe', methods=['POST'])
@app.route('/api/backend/feeds/<feed_key>/subscribe', methods=['POST'])
@ndb.synctasklet
def feed_push_update(feed_key):
    feed = ndb.Key(urlsafe=feed_key).get()
    if not feed:
        raise ndb.Return(("No feed", 404))

    data = request.stream.read()
    logger.info('Got PuSH body: %s', data)
    logger.info('Got PuSH headers: %s', request.headers)

    if feed.hub_secret:
        server_signature = request.headers.get('X-Hub-Signature', None)
        signature = hmac.new(feed.hub_secret, data).hexdigest()

        if server_signature != signature:
            logger.warn('Got PuSH subscribe POST for feed key=%s w/o valid signature: sent=%s != expected=%s', feed_key,
                        server_signature, signature)

            raise ndb.Return('')

    parsed_feed = feedparser.parse(data)
    new_guids, old_guids = yield Entry.process_parsed_feed(parsed_feed, feed, overflow=False)
    yield Entry.publish_for_feed(feed, skip_queue=False)

    raise ndb.Return('')

feed_push_update.login_required = False


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

    parsed_feed = feedparser.parse(request.stream.read())
    new_guids, old_guids = yield Entry.process_parsed_feed(parsed_feed, feed, overflow=False)
    yield Entry.publish_for_feed(feed, skip_queue=False)

    etag = request.args.get('etag')
    if etag:
        feed.etag = etag
    else:
        logger.info('Missing an updated etag for feed: %s', feed_key)

    last_hash = request.args.get('last_hash')
    if last_hash:
        feed.last_fetched_content_hash = last_hash
    else:
        logger.info('Missing an updated hash for feed: %s', feed_key)

    if feed.error_count > 0:
        feed.error_count = 0

    yield feed.put_async()

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
    feed.error_count += 1

    noop = request.form.get('noop')
    if noop:
        logger.info('Noop feed error feed: %s because off testing', feed_key)
        raise ndb.Return(jsonify(status='ok'))

    yield feed.put_async()

    raise ndb.Return(jsonify(status='ok'))

update_feed_for_error.app_token_required = True
update_feed_for_error.login_required = False



@app.route('/api/feeds/all/update/<int:interval_id>')
@app.route('/api/backend/feeds/all/update/<int:interval_id>')
@ndb.synctasklet
def update_all_feeds(interval_id):
    """Update all feeds for a specific interval"""
    if request.headers.get('X-Appengine-Cron') != 'true':
        raise ndb.Return(jsonify_error(message='Not a cron call'))

    feeds = Feed.for_interval(interval_id)

    for feed_type, feed_class in FEED_TYPE_TO_CLASS.iteritems():
        feeds = Feed.for_interval(interval_id)
        success = 0
        more = True
        cursor = None
        futures = []
        while more:
            feeds_to_fetch, cursor, more = yield feeds.fetch_page_async(BATCH_SIZE, start_cursor=cursor)
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
            logger.exception('Failed to Publish feed:%s' % (feed.feed_url, ))

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
        feeds = feed_class.query()
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
        resp = yield future

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

    qit = Feed.query().iter()
    feeds_response = []
    while (yield qit.has_next_async()):
        feeds_response.append(feed_to_dict(qit.next()))

    poller_run_id = uuid.uuid4().hex

    logger.info('Poller run %s dispatched with %d feeds', poller_run_id, len(feeds_response))

    response = {
        'poller_run_id': poller_run_id,
        'feeds': feeds_response,
    }

    raise ndb.Return(jsonify(status='ok', data=response))

all_feeds.app_token_required = True
all_feeds.login_required = False


@app.route('/api/feeds/monitor', methods=['GET'])
@app.route('/api/backend/feeds/monitor', methods=['GET'])
@ndb.synctasklet
def monitor_jobs():
    """Are the jobs running"""
    post_value = yield get_epoch_from_stat(Stat, 'post_job')
    poll_value = yield get_epoch_from_stat(Stat, 'poll_job')

    response = {
        'post': post_value,
        'poll': poll_value,
    }

    raise ndb.Return(jsonify(status='ok', data=response))

monitor_jobs.login_required = False


@app.route('/_ah/warmup')
@app.route('/_ah/start')
@app.route('/_ah/stop')
def warmup():
    """App Engine warmup handler
    See http://code.google.com/appengine/docs/python/config/appconfig.html#Warming_Requests

    """
    return ''

warmup.login_required = False
