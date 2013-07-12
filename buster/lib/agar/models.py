"""
The ``agar.models`` module contains classes to help working with `Model`_.
"""

from google.appengine.ext import db
from google.appengine.ext.db import BadKeyError


class NamedModel(db.Model):
    """
    A base (or mix-in) `Model`_ subclass to create an entity with a ``key_name`` (either passed in or generated automatically).

    This base model has a classmethod for automatically assigning a new uuid for its ``key_name`` on creation of a new entity.
    """
    @property
    def key_name(self):
        """
        The entity's `key().name()`_ unicode value if available, otherwise ``None``.
        """
        return self.key().name()

    @classmethod
    def generate_key_name(cls):
        """
        Creates a (hopefully) unique string to be used as an identifier. The default implementation uses a `uuid4`_ hex
        value.

        :return: A unique string to be used as an identifier.
        """
        from agar.keygen import generate_key 
        return generate_key()

    @classmethod
    def create_new_entity(cls, **kwargs):
        """
        Creates and persists an entity by (optionally) generating and setting a ``key_name``. A ``key_name`` will be
        generated or may be provided as a keyword arg.  If a generated ``key_name`` is already in use,
        a new one will be generated.  If, after the 3rd attempt the ``key_name`` is still not unique,
        a :py:class:`agar.models.DuplicateKeyError` will be raised. This exception will also be raised if the argument
        ``key_name`` is not ``None`` and not unique.

        :param key_name: Used for the entity key name, otherwise will be generated.
        :param parent: Optional parent key. If not supplied, defaults to ``None``.
        :param kwargs: Initial values for the instance's properties, as keyword arguments.
        :return: The newly created and persisted :py:class:`NamedModel`.
        
        Examples::

            person = Person.create_new_entity()

            person_with_keyname = Person.create_new_entity(key_name='bob')
        """
        
        # Inline transaction function
        def txn(key_name):
            if kwargs.has_key('parent'):
                entity = cls.get_by_key_name(key_name, parent=kwargs['parent'])
            else:
                entity = cls.get_by_key_name(key_name)
            if entity is None:
                entity = cls(key_name=key_name, **kwargs)
                entity.put()
                return entity
            else:
                raise DuplicateKeyError("key_name '%s' is already in use" % key_name)
        
        # Function body
        entity = None
        tries = 0
        requested_key_name = kwargs.pop('key_name', None)
        if requested_key_name:
            entity = db.run_in_transaction(txn, requested_key_name)
        else:
            while entity is None:
                try:
                    entity = db.run_in_transaction(txn, cls.generate_key_name())
                except BadKeyError:
                    tries += 1
                    if tries >= 3:
                        raise
        return entity


class DuplicateKeyError(BadKeyError):
    """
    The :py:class:`NamedModel` tried to create an instance with a ``key_name`` that is already in use.
    """
    pass


class ModelException(Exception):
    """
    There was an exception working with a `Model`_ while processing a :py:class:`agar.json.JsonRequestHandler`.
    """
    pass
