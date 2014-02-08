from google.appengine.ext import ndb


class User(ndb.Model):
    access_token = ndb.StringProperty()

    @classmethod
    def key_from_adn_user(cls, adn_user):
        return 'adn_user_id=%d' % int(adn_user.id)
