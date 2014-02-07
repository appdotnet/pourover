import datetime
import json

from flask import Response


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
