"""
views.py

URL route handlers
"""
import json
import logging
import datetime
import hmac

from google.appengine.ext import ndb

from flask import request, render_template, g, Response
from google.appengine.api import urlfetch

from flask_cache import Cache

from application import app
from models import Entry, Feed, UPDATE_INTERVAL, FetchException
from forms import FeedCreate, FeedUpdate, FeedPreview

logger = logging.getLogger(__name__)

# Flask-Cache (configured to use App Engine Memcache API)
cache = Cache(app)


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
@app.route('/logout/', endpoint='logout')
@app.route('/feed/<feed_id>/', endpoint='feeds')
def index(feed_id=None):
    return render_template('index.html')

index.login_required = False


@app.route('/api/me', methods=['GET'])
def me():
    """return current user"""
    return jsonify(status='ok', data=g.adn_user)


@app.route('/api/feeds', methods=['GET'])
def feeds():
    """List all examples"""
    users_feeds = [feed.to_json() for feed in Feed.for_user(g.user)]
    return jsonify(status='ok', data=users_feeds)


@app.route('/api/feeds', methods=['POST'])
def feed_create():
    """List all examples"""
    form = FeedCreate(request.form)
    logger.info('Form data %s', request.form)
    if not form.validate():
        return jsonify(status='error', message='The passed arguments failed validation')

    exsisting_feeds = Feed.for_user_and_url(user=g.user, feed_url=form.data['feed_url'])
    if exsisting_feeds.count():
        feed = exsisting_feeds.get()
    else:
        feed = Feed.create_feed_from_form(g.user, form)

    return jsonify(status='ok', data=feed.to_json())


@app.route('/api/feed/preview', methods=['GET'])
def feed_preview():
    """preview a feed"""
    form = FeedPreview(request.args)
    if not form.validate():
        return jsonify(status='error', form_errors=form.errors)

    feed = Feed()
    form.populate_obj(feed)
    feed.preview = True
    entries = []
    error = None

    try:
        entries = Entry.entry_preview_for_feed(feed)
    except FetchException, e:
        error = unicode(e)
    except Exception, e:
        raise
        error = 'Something went wrong while fetching your URL.'
        logger.exception('Feed Preview: Failed to update feed:%s' % (feed.feed_url, ))

    if not entries and not error:
        error = 'The feed doesn\'t have any entries'

    if error:
        return jsonify(status='error', message=error)

    return jsonify(status='ok', data=entries[0:3])


@app.route('/api/feeds/<int:feed_id>', methods=['GET'])
def feed(feed_id):
    """Get a feed"""
    feed = Feed.get_by_id(feed_id, parent=g.user.key)
    if not feed:
        return jsonify_error(message="Can't find that feed")

    feed_data = feed.to_json()
    entries = [entry.to_dict(include=['guid', 'published', 'extra_info']) for entry in Entry.latest_for_feed(feed).fetch(10)]
    feed_data['entries'] = entries

    return jsonify(status='ok', data=feed_data)


@app.route('/api/feeds/<int:feed_id>', methods=['POST'])
def feed_change(feed_id):
    """Get a feed"""
    form = FeedUpdate(request.form)
    if not form.validate():
        return jsonify_error(message="Invalid update data")

    feed = Feed.get_by_id(feed_id, parent=g.user.key)
    if not feed:
        return jsonify_error(message="Can't find that feed")

    form.populate_obj(feed)
    feed.put()

    feed_data = feed.to_json()
    entries = [entry.to_dict(include=['title', 'link', 'published', 'published_at']) for entry in Entry.latest_for_feed(feed).fetch(10)]
    feed_data['entries'] = entries

    return jsonify(status='ok', data=feed_data)


@app.route('/api/feeds/<int:feed_id>', methods=['DELETE'])
def delete_feed(feed_id):
    """Get a feed"""
    feed = Feed.get_by_id(feed_id, parent=g.user.key)
    if not feed:
        return jsonify_error(message="Can't find that feed")

    Entry.delete_for_feed(feed)
    feed.key.delete()

    return jsonify(status='ok')


@app.route('/api/feeds/<int:feed_id>/unpublished', methods=['GET'])
def unpublished_entries_for_feed(feed_id):
    feed = Feed.get_by_id(feed_id, parent=g.user.key)
    if not feed:
        return jsonify_error(message="Can't find that feed")

    feed_data = feed.to_json()
    entries = [entry.to_json(include=['title', 'link', 'published', 'published_at']) for entry in Entry.latest_unpublished(feed).fetch(20)]
    feed_data['entries'] = entries

    return jsonify(status='ok', data=feed_data)


@app.route('/api/feeds/<int:feed_id>/published', methods=['GET'])
def published_entries_for_feed(feed_id):
    feed = Feed.get_by_id(feed_id, parent=g.user.key)
    if not feed:
        return jsonify_error(message="Can't find that feed")

    feed_data = feed.to_json()
    entries = [entry.to_json(include=['title', 'link', 'published', 'published_at']) for entry in Entry.latest_published(feed).fetch(20)]
    feed_data['entries'] = entries

    return jsonify(status='ok', data=feed_data)


@app.route('/api/feeds/<int:feed_id>/preview', methods=['GET'])
def save_feed_preview(feed_id):
    """preview a saved feed"""
    form = FeedUpdate(request.args)
    if not form.validate():
        return jsonify_error(message="Invalid update data")

    feed = Feed.get_by_id(feed_id, parent=g.user.key)
    if not feed:
        return jsonify_error(message="Can't find that feed")

    form.populate_obj(feed)
    feed.preview = True
    preview_entries = Entry.entry_preview(Entry.latest_published(feed).fetch(3), feed, format=True)

    return jsonify(status='ok', data=preview_entries)


@app.route('/api/feeds/<int:feed_id>/entries/<int:entry_id>/publish', methods=['POST'])
def feed_entry_publish(feed_id, entry_id):
    """Get a feed"""
    logger.info('Manually publishing Feed:%s Entry: %s', feed_id, entry_id)

    feed = Feed.get_by_id(feed_id, parent=g.user.key)
    if not feed:
        return jsonify_error(message="Can't find that feed")

    entry = Entry.get_by_id(entry_id, parent=feed.key)
    if not entry:
        return jsonify_error(message="Can't find that entry")

    entry.publish_entry(feed)
    entry.overflow = False
    entry.put()

    return jsonify(status='ok')


@app.route('/api/feeds/<feed_key>/subscribe', methods=['GET'])
def feed_subscribe(feed_key):
    mode = request.args['hub.mode']
    challenge = request.args['hub.challenge']
    verify_token = request.args.get('hub.verify_token')

    if mode == 'subscribe':
        feed = ndb.Key(urlsafe=feed_key).get()
        # Only check this they send back a verify token
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
def feed_push_update(feed_key):
    feed = ndb.Key(urlsafe=feed_key).get()
    if not feed:
        return "No feed", 404

    data = request.stream.read()

    if feed.hub_secret:
        server_signature = request.headers.get('X-Hub-Signature', None)
        signature = hmac.new(feed.hub_secret, data).hexdigest()

        if server_signature != signature:
            logger.warn('Got PuSH subscribe POST for feed key=%s w/o valid signature: sent=%s != expected=%s', feed_key,
                        server_signature, signature)
            return ''

    logger.info('Got PuSH body: %s', data)
    logger.info('Got PuSH headers: %s', request.headers)

    Entry.update_for_feed(feed, publish=True, skip_queue=True)

    return ''

feed_push_update.login_required = False


@app.route('/api/feeds/all/update/<int:interval_id>')
def update_all_feeds(interval_id):
    """Update all feeds for a specific interval"""
    if request.headers.get('X-Appengine-Cron') != 'true':
        return jsonify_error(message='Not a cron call')

    feeds = Feed.for_interval(interval_id)

    for feed in feeds:
        feed.prepare_request()

    errors = 0
    success = 0
    for feed in feeds:
        try:
            Entry.update_for_feed(feed, publish=True)
            success += 1
        except FetchException, e:
            errors += 1
            pass
        except Exception, e:
            errors += 1
            logger.exception('Failed to update feed:%s' % (feed.feed_url, ))

    logger.info('Updated Feeds interval_id:%s success:%s errors: %s', interval_id, success, errors)

    return jsonify(status='ok')

update_all_feeds.login_required = False


@app.route('/_ah/warmup')
def warmup():
    """App Engine warmup handler
    See http://code.google.com/appengine/docs/python/config/appconfig.html#Warming_Requests

    """
    return ''

warmup.login_required = False
