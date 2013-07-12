"""
views.py

URL route handlers

Note that any handler params must match the URL route params.
For example the *say_hello* handler, handling the URL route '/hello/<username>',
  must be passed *username* as the argument.

"""
import json
import logging
import datetime

from flask import request, render_template, g, Response

from flask_cache import Cache

from application import app
from models import Entry, Feed, UPDATE_INTERVAL
from forms import FeedCreate

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
def index():
    return render_template('index.html')

index.login_required = False


@app.route('/api/feeds', methods=['GET'])
def feeds():
    """List all examples"""
    users_feeds = [feed.to_json() for feed in Feed.for_user(g.user)]
    return jsonify(status='ok', data=users_feeds)


@app.route('/api/feeds', methods=['POST'])
def feed_create():
    """List all examples"""
    form = FeedCreate(request.form)
    if not form.validate():
        return jsonify(status='error', message='The passed arguments failed validation')

    exsisting_feeds = Feed.for_user_and_url(user=g.user, feed_url=form.data['feed_url'])
    try:
        feed = exsisting_feeds.iter().next()
    except StopIteration:
        feed = Feed.create_feed_from_form(g.user, form)

    return jsonify(status='ok', data=feed.to_json())


@app.route('/api/feed/preview', methods=['GET'])
def feed_preview():
    """preview a feed"""
    feed_url = request.args.get('feed_url')
    include_summary = request.args.get('include_summary', 'false') == 'true'
    if not feed_url:
        return jsonify(status='error', message='You must pass a feed url')

    exsisting_feeds = Entry.entry_preview_for_feed(feed_url=feed_url, include_summary=include_summary)

    return jsonify(status='ok', data=exsisting_feeds[0:3])


@app.route('/api/feeds/<int:feed_id>', methods=['GET'])
def feed(feed_id):
    """Get a feed"""
    feed = Feed.get_by_id(feed_id)
    if not feed:
        return jsonify_error(message="Can't find that feed")

    if feed.parent_key() != g.user.key:
        return jsonify_error(message="Not Authorized")

    feed_data = feed.to_json()
    entries = [entry.to_dict(include=['guid', 'published', 'extra_info']) for entry in Entry.latest_for_feed(feed).fetch(10)]
    feed_data['entries'] = entries

    return jsonify(status='ok', data=feed_data)


@app.route('/api/feeds/<int:feed_id>', methods=['POST'])
def feed_change(feed_id):
    """Get a feed"""

    form = FeedCreate(request.form)
    if not form.validate():
        return jsonify_error(message="Invalid update data")

    feed = Feed.get_by_id(feed_id)
    if not feed:
        return jsonify_error(message="Can't find that feed")

    if feed.parent_key() != g.user.key:
        return jsonify_error(message="Not Authorized")

    form.populate_obj(feed)
    feed.put()

    feed_data = feed.to_json()
    entries = [entry.to_dict(include=['title', 'link', 'published', 'published_at']) for entry in Entry.latest_for_feed(feed).fetch(10)]
    feed_data['entries'] = entries

    return jsonify(status='ok', data=feed_data)


@app.route('/api/feeds/<int:feed_id>', methods=['DELETE'])
def delete_feed(feed_id):
    """Get a feed"""
    feed = Feed.get_by_id(feed_id)
    if not feed:
        return jsonify_error(message="Can't find that feed")

    if feed.parent_key() != g.user.key:
        return jsonify_error(message="Not Authorized")

    Entry.delete_for_feed(feed)
    feed.key.delete()

    return jsonify(status='ok')


@app.route('/api/feeds/<int:feed_id>/unpublished', methods=['GET'])
def unpublished_entries_for_feed(feed_id):
    feed = Feed.get_by_id(feed_id)
    if not feed:
        return jsonify_error(message="Can't find that feed")

    if feed.parent_key() != g.user.key:
        return jsonify_error(message="Not Authorized")

    feed_data = feed.to_json()
    entries = [entry.to_json(include=['title', 'link', 'published', 'published_at']) for entry in Entry.latest_unpublished(feed).fetch(20)]
    feed_data['entries'] = entries

    return jsonify(status='ok', data=feed_data)


@app.route('/api/feeds/<int:feed_id>/published', methods=['GET'])
def published_entries_for_feed(feed_id):
    feed = Feed.get_by_id(feed_id)
    if not feed:
        return jsonify_error(message="Can't find that feed")

    if feed.parent_key() != g.user.key:
        return jsonify_error(message="Not Authorized")

    feed_data = feed.to_json()
    entries = [entry.to_json(include=['title', 'link', 'published', 'published_at']) for entry in Entry.latest_published(feed).fetch(20)]
    feed_data['entries'] = entries

    return jsonify(status='ok', data=feed_data)


@app.route('/api/feeds/<int:feed_id>/subscribe', methods=['GET'])
def feed_subscribe(feed_id):
    mode = request.args['hub.mode']
    challenge = request.args['hub.challenge']
    verify_token = request.args.get('hub.verify_token', '')

    if mode == 'subscribe':
        feed = Feed.get_by_id(feed_id)
        if verify_token != feed.verify_token:
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


@app.route('/api/feeds/<int:feed_id>/subscribe', methods=['POST'])
def feed_push_update(feed_id):
    feed = Feed.get_by_id(feed_id)
    if not feed:
        return "No feed", 404

    Entry.update_for_feed(feed, publish=True, skip_queue=True)

    return ''

feed_push_update.login_required = False


@app.route('/api/feeds/<int:feed_id>/update', methods=['POST'])
def feed_update(feed_id):
    """Update a feed"""
    feed = Feed.get_by_id(feed_id)
    if not feed:
        return jsonify_error(message="Can't find that feed")

    if feed.parent_key() != g.user.key:
        return jsonify_error(message="Not Authorized")

    Entry.update_for_feed(feed, publish=True)

    return jsonify(status='ok')

feed_update.login_required = False


@app.route('/api/feeds/<int:feed_id>/entries/<int:entry_id>/publish', methods=['POST'])
def feed_entry_publish(feed_id, entry_id):
    """Get a feed"""
    logger.info('Manually publishing Feed:%s Entry: %s', feed_id, entry_id)

    feed = Feed.get_by_id(feed_id)
    if not feed:
        return jsonify_error(message="Can't find that feed")

    entry = Entry.get_by_id(entry_id, parent=feed.key)
    if not entry:
        return jsonify_error(message="Can't find that entry")

    if feed.parent_key() != g.user.key:
        return jsonify_error(message="Not Authorized")

    entry.publish_entry()
    entry.overflow = False
    entry.put()

    return jsonify(status='ok')


@app.route('/api/feeds/all/update/<int:interval_id>')
def update_all_feeds(interval_id):
    """Update all feeds for a specific interval"""

    feeds = Feed.for_interval(interval_id)
    for feed in feeds:
        Entry.update_for_feed(feed, publish=True)

    return jsonify(status='ok')

update_all_feeds.login_required = False


@app.route('/_ah/warmup')
def warmup():
    """App Engine warmup handler
    See http://code.google.com/appengine/docs/python/config/appconfig.html#Warming_Requests

    """
    return ''

warmup.login_required = False
