"""
App Engine config

"""


def gae_mini_profiler_should_profile_production():
    """Uncomment the first two lines to enable GAE Mini Profiler on production for admin accounts"""
    # from google.appengine.api import users
    # return users.is_current_user_admin()
    return False

remoteapi_CUSTOM_ENVIRONMENT_AUTHENTICATION = ('HTTP_X_APPENGINE_INBOUND_APPID', ['pour-over'])
