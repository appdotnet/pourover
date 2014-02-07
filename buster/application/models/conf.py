from google.appengine.ext import ndb


class Configuration(ndb.Model):
    name = ndb.StringProperty()
    value = ndb.StringProperty()

    @classmethod
    def value_for_name(cls, name, default=None):
        conf = cls.query(cls.name == name).get()
        if not conf:
            return default

        return conf.value
