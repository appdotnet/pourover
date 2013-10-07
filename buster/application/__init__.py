"""
Initialize Flask app

"""
from flask import Flask
# from flaskext.gae_mini_profiler import GAEMiniProfiler

import re

# from flask_debugtoolbar import DebugToolbarExtension
from werkzeug.debug import DebuggedApplication

from .middleware import ADNTokenAuthMiddleware
from flask_cors import CrossOriginResourceSharing

from google.appengine.ext import ndb
from google.appengine.ext.appstats import recording
# import gae_mini_profiler.profiler

app = Flask('application')
app.config.from_object('application.settings')

# Enable jinja2 loop controls extension
app.jinja_env.add_extension('jinja2.ext.loopcontrols')

# Pull in URL dispatch routes
import urls

allowed = (
    re.compile("^.*$"),  # Match a regex
)

cors = CrossOriginResourceSharing(app)
cors.set_allowed_origins(*allowed)
# GAEMiniProfiler(app)

# Flask-DebugToolbar (only enabled when DEBUG=True)
# toolbar = DebugToolbarExtension(app)

ADNTokenAuthMiddleware(app)

# Werkzeug Debugger (only enabled when DEBUG=True)
if app.debug:
    app.wsgi_app = DebuggedApplication(app.wsgi_app, evalex=True)
else:
    import logging
    # import email_logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    #requests_log = logging.getLogger("requests")
    #requests_log.setLevel(logging.WARNING)
    #email_logger.register_logger(app.config['ADMIN_EMAIL'])

app.wsgi_app = recording.appstats_wsgi_middleware(app.wsgi_app)

app.__call__ = ndb.toplevel(app.__call__)
