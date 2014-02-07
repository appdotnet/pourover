from google.appengine.ext import ndb


class Stat(ndb.Model):
    """Keep track of users"""
    name = ndb.StringProperty()
    value = ndb.StringProperty()
