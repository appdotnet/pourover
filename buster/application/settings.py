"""
settings.py

Configuration for Flask app

Important: Place your keys in the secret_keys.py module,
           which should be kept out of version control.

"""

import os

from secret_keys import CSRF_SECRET_KEY, SESSION_KEY


DEBUG_MODE = False

# Auto-set debug mode based on App Engine dev environ
if 'SERVER_SOFTWARE' in os.environ and os.environ['SERVER_SOFTWARE'].startswith('Dev'):
    DEBUG_MODE = True

DEBUG = DEBUG_MODE

# Set secret keys for CSRF protection
SECRET_KEY = CSRF_SECRET_KEY
CSRF_SESSION_KEY = SESSION_KEY

CSRF_ENABLED = True

# Flask-DebugToolbar settings
DEBUG_TB_PROFILER_ENABLED = DEBUG
DEBUG_TB_INTERCEPT_REDIRECTS = False

# Flask-Cache settings
CACHE_TYPE = 'gaememcached'

# update this with your own App.net client ID
# make sure this matches what's in gob/app/views/main.html
CLIENT_ID = '6kmFxf2JrEqmFRQ4WncLfN8WWx7FnUS8'

# Make sure you update this with your email address
ADMIN_EMAIL = 'alex@app.net'
