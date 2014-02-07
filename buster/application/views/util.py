from google.appengine.ext import ndb

from application import app
from application.models import Stat
from application.utils import get_epoch_from_stat

from view_utils import jsonify


@app.route('/api/feeds/monitor', methods=['GET'])
@app.route('/api/backend/feeds/monitor', methods=['GET'])
@ndb.synctasklet
def monitor_jobs():
    """Are the jobs running"""
    post_value = yield get_epoch_from_stat(Stat, 'post_job')
    external_poll_get_all_feeds = yield get_epoch_from_stat(Stat, 'external_poll_get_all_feeds')
    external_poll_post_feed = yield get_epoch_from_stat(Stat, 'external_poll_post_feed')

    response = {
        'post': post_value,
        'external_poll_get_all_feeds': external_poll_get_all_feeds,
        'external_poll_post_feed': external_poll_post_feed,
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
