"""
The ``agar.env`` module contains a number of constants to help determine which environment code is running in.
"""

import os

from google.appengine.api.app_identity import get_application_id
from google.appengine.api import apiproxy_stub_map


server_software = os.environ.get('SERVER_SOFTWARE', '')
have_appserver = bool(apiproxy_stub_map.apiproxy.GetStub('datastore_v3'))

appid = None
if have_appserver:
    appid = get_application_id()
else:
    try:
        project_dir = os.path.dirname(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
        from google.appengine.tools import dev_appserver
        appconfig, matcher, from_cache = dev_appserver.LoadAppConfig(project_dir, {})
        appid = appconfig.application
    except ImportError:
        appid = None

#: ``True`` if running in the dev server, ``False`` otherwise.
on_development_server = bool(have_appserver and (not server_software or server_software.lower().startswith('devel')))
#: ``True`` if running on a google server, ``False`` otherwise.
on_server = bool(have_appserver and appid and server_software and not on_development_server)
#: ``True`` if running on a google server and the application ID ends in ``-int``, ``False`` otherwise.
on_integration_server = on_server and appid.lower().endswith('-int')
#: ``True`` if running on a google server and the application ID does not end in ``-int``, ``False`` otherwise.
on_production_server = on_server and not on_integration_server
