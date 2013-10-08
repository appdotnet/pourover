import hashlib
import json
import logging

from google.appengine.api import urlfetch, memcache
from flask import g, request, abort, current_app
import cachepy
from .models import User, Feed

MEMCACHE_USER_KEY = 'user:%s'

logger = logging.getLogger(__name__)


def hash_for_token(access_token):
    return MEMCACHE_USER_KEY % (access_token, ), hashlib.sha224(access_token).hexdigest()


# From https://github.com/makinacorpus/easydict
class EasyDict(dict):
    def __init__(self, d=None, **kwargs):
        if d is None:
            d = {}
        if kwargs:
            d.update(**kwargs)
        for k, v in d.items():
            setattr(self, k, v)
        # Class attributes
        for k in self.__class__.__dict__.keys():
            if not (k.startswith('__') and k.endswith('__')):
                setattr(self, k, getattr(self, k))

    def __setattr__(self, name, value):
        if isinstance(value, (list, tuple)):
            value = [EasyDict(x) if isinstance(x, dict) else x for x in value]
        else:
            value = EasyDict(value) if isinstance(value, dict) else value
        super(EasyDict, self).__setattr__(name, value)
        self[name] = value


class ADNTokenAuthMiddleware(object):
    def __init__(self, app):
        self.app = app
        app.before_request(self.before_request)

    def fetch_user_data(self, auth_token, memcache_key):
        headers = {
            'Authorization': 'Bearer %s' % auth_token,
        }

        resp = urlfetch.fetch(url='https://alpha-api.app.net/stream/0/token', method='GET', headers=headers)
        if resp.status_code == 200:
            cachepy.set(memcache_key, resp.content, 5 * 60)  # Expire in 5 min
            return resp.content

        return None

    def before_request(self):
        '''Try and setup user for this request'''

        adn_user = None
        is_app_token = False

        authorization_header = request.headers.get('Authorization')
        if authorization_header:
            method, access_token = authorization_header.split(' ', 1)
            if access_token:
                memcache_key, token_hash = hash_for_token(access_token)
                user_data = cachepy.get(memcache_key) or self.fetch_user_data(access_token, memcache_key)
                if user_data:
                    token = json.loads(user_data).get('data', {})
                    if token and token['app']['client_id'] == current_app.config['CLIENT_ID']:
                        if token.get('is_app_token'):
                            is_app_token = True
                        else:
                            try:
                                adn_user = EasyDict(token['user'])
                            except:
                                pass

        view_func = self.app.view_functions.get(request.endpoint)
        login_required = getattr(view_func, 'login_required', True)
        # logger.info('Login Required: %s', login_required)
        if login_required and not adn_user:
            abort(401)

        app_token_required = getattr(view_func, 'app_token_required', False)
        # logger.info('app_token_required: %s', app_token_required)
        if app_token_required and not is_app_token:
            abort(401)

        if adn_user:
            user = User.get_or_insert(User.key_from_adn_user(adn_user), access_token=access_token)
            if user.access_token != access_token:
                user.access_token = access_token
                user.put()
                Feed.reauthorize(user)

            g.adn_user = adn_user
            g.user = user
