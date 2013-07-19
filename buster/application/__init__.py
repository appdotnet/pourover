"""
Initialize Flask app

"""
from flask import Flask
import re

# from flask_debugtoolbar import DebugToolbarExtension
from werkzeug.debug import DebuggedApplication

from .middleware import ADNTokenAuthMiddleware
from flask_cors import CrossOriginResourceSharing
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

# Flask-DebugToolbar (only enabled when DEBUG=True)
# toolbar = DebugToolbarExtension(app)

ADNTokenAuthMiddleware(app)

# Werkzeug Debugger (only enabled when DEBUG=True)
if app.debug:
    app = DebuggedApplication(app, evalex=True)
else:
    import logging
    import email_logger
    #requests_log = logging.getLogger("requests")
    #requests_log.setLevel(logging.WARNING)
    email_logger.register_logger(app.config['ADMIN_EMAIL'])
