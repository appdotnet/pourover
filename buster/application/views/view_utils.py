import datetime
import json

from flask import Response, g
from application.constants import FEED_TYPE
from application.models import FEED_TYPE_TO_CLASS


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


def get_feeds_for_channel(channel_id):
    return [feed for feed in FEED_TYPE_TO_CLASS[FEED_TYPE.RSS].for_user_and_channel(g.user, channel_id) if feed.visible]


def export_feeds_to_json(feeds):
    return [feed.to_json() for feed in feeds]
