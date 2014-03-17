from flask import request

from google.appengine.ext import ndb

from application import app
from application.models import Feed
from application.utils import cast_int

from view_utils import jsonify, export_feeds_to_json


@app.route('/api/admin/feeds/channel/<int:channel_id>/limit', methods=['POST'])
@ndb.synctasklet
def limit_feeds_for_channel_id(channel_id):
    """Limit all feeds connected to a channel"""
    max_stories_per_period = cast_int(request.form.get('max_stories_per_period'), default=None)
    schedule_period = cast_int(request.form.get('schedule_period'), default=None)
    dump_excess_in_period = bool(request.form.get('dump_excess_in_period'))
    users_feeds = [feed for feed in Feed.for_channel(channel_id) if feed.visible]
    futures = []
    for feed in users_feeds:
        if dump_excess_in_period:
            feed.dump_excess_in_period = True

        if max_stories_per_period or schedule_period:
            feed.manual_control = True

        if max_stories_per_period:
            feed.max_stories_per_period = max_stories_per_period

        if schedule_period:
            feed.schedule_period = schedule_period

        futures.append(feed.put_async())

    for future in futures:
        yield future

    users_feeds = export_feeds_to_json(users_feeds)

    raise ndb.Return(jsonify(status='ok', data=users_feeds))


limit_feeds_for_channel_id.app_token_required = True
limit_feeds_for_channel_id.login_required = False
