import hashlib
import json
import logging

from google.appengine.api import urlfetch, memcache
from flask import g, request, abort

from .models import User

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

        resp = urlfetch.fetch(url='https://alpha-api.app.net/stream/0/users/me', method='GET', headers=headers)
        if resp.status_code == 200:
            memcache.set(memcache_key, resp.content, 60 * 60)  # Expire in 1 hour
            return resp.content

        return None

    def before_request(self):
        '''Try and setup user for this request'''

        authorization_header = request.headers.get('Authorization')
        user = None
        if authorization_header:
            method, access_token = authorization_header.split(' ', 1)
            if access_token:
                memcache_key, token_hash = hash_for_token(access_token)
                user_data = memcache.get(memcache_key) or self.fetch_user_data(access_token, memcache_key)
                if user_data:
                    user_data = json.loads(user_data)
                    user = EasyDict(user_data.get('data'))

        view_func = self.app.view_functions.get(request.endpoint)
        login_required = getattr(view_func, 'login_required', None)
        login_required = login_required is None or login_required is True
        if login_required and user is None:
            abort(401)

        if user:
            User.get_or_create(user, access_token)
            user.id = int(user.id)

        g.user = user
