import logging

from flask import request
from google.appengine.api import prospective_search
from google.appengine.ext import ndb

from application import app

from view_utils import jsonify, jsonify_error

logger = logging.getLogger(__name__)


@app.route('/api/backend/queries/matched', methods=['POST'], endpoint="quries_matched")
@ndb.synctasklet
def inbound_search_matches():
    if request.headers.get('X-Appengine-Queuename') != 'default':
        raise ndb.Return(jsonify_error(message='Not a cron call'))

    # List of subscription ids that matched for match.
    sub_ids = request.form.getlist('id')
    keys = []
    for sub_id in sub_ids:
        keys.append(ndb.Key(urlsafe=sub_id))

    subs = yield ndb.get_multi_async(keys)
    doc = prospective_search.get_document(request.form)
    for sub in subs:
        logger.info('prospective: Would have sent to %s %s', sub, doc)

    logger.info('prospective: Request form: %s', request.form)
    raise ndb.Return(jsonify(status='ok'))

inbound_search_matches.login_required = False
