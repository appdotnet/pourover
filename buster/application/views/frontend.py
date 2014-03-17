import logging

from google.appengine.ext import ndb
from flask import g, request

from application import app
from application.constants import FEED_TYPE
from application.models import Entry, Feed, FEED_TYPE_TO_CLASS
from application.fetcher import FetchException, fetch_parsed_feed_for_feed
from application.publisher.entry import publish_entry

from view_utils import jsonify, jsonify_error, get_feeds_for_channel, export_feeds_to_json


logger = logging.getLogger(__name__)


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

    users_feeds = get_feeds_for_channel(channel_id)
    users_feeds = export_feeds_to_json(users_feeds)

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
            # If this feed is already publishing to a channel don't yank it away.
            if feed.channel_id:
                return jsonify(status='error', message='The feed is already connected to a channel.')

            feed.publish_to_stream = True
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

    publish_entry(entry, feed, ignore_publish_state=True).get_result()
    entry.overflow = False
    entry.put()

    return jsonify(status='ok')
