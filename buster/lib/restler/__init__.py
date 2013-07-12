"""The ``restler`` package is a simple and flexible serialization to JSON and XML of App Engine Models and Queries.


A Simple Example
----------------

First, we'll need to import some appengine and
restler package classes and functions.

>>> from google.appengine.ext import db
>>> from restler.serializers import ModelStrategy, to_json, to_xml, SKIP

To help with our examples, let's create a simple ``db.Model`` class that we'll later serialize.

>>> class Person(db.Model):
...     first_name = db.StringProperty()
...     last_name = db.StringProperty()
...     ssn = db.StringProperty()

Next, we'll create an instance of the Person class.

>>> jean = Person(first_name="Jeanne", last_name="d'Arc", ssn="N/A")

Now, let's try serializing it:

>>> to_json(jean)
'{"first_name": "Jeanne", "last_name": "d\'Arc", "ssn": "N/A"}'

How about to XML?

>>> to_xml(jean)
"<result><person><first_name>Jeanne</first_name><last_name>d'Arc</last_name><ssn>N/A</ssn></person></result>"

Include/Exclude Fields
----------------------

Perfect, that's exactly what we wanted.  *Almost...*  An SSN is
rather sensitive information that we really shouldn't expose.

To keep SSN from being serialized, we have to introduce
``restler.serializers.ModelStrategy`` which describes how to
serialize a ``google.ext.db.Model`` i.e. which properties to
serialize.

To only serialize ``first_name`` and ``last_name`` we'd create a ModelStrategy
as follows:

>>> person_strategy = ModelStrategy(Person).include("first_name", "last_name")
>>> to_json(jean, person_strategy)
'{"first_name": "Jeanne", "last_name": "d\'Arc"}'

If we supply a ModelStrategy without including any fields, we'll get an
empty json object.

>>> person_strategy = ModelStrategy(Person)
>>> to_json(jean, person_strategy)
'{}'

If our Person model defined a lot of properties, it might be tedious to add
all of the fields.  It would be nice to declare that we want *all* properties
of the Person model *except* for SSN.  And, in fact, we can do that as follows:

>>> person_strategy = ModelStrategy(Person, include_all_fields=True).exclude("ssn")
>>> to_json(jean, person_strategy)
'{"first_name": "Jeanne", "last_name": "d\'Arc"}'

To summarize, ``Restler`` will serialize all properties of a Model unless there is
a ``ModelStrategy`` that defines which properties are to be serialized.

Renaming Fields
---------------

What if we wanted to use ``family_name`` instead of ``last_name`` and ``given_name``
instead of ``first_name``?  We do that as follows:

>>> person_strategy = ModelStrategy(Person).include("ssn", given_name="first_name", family_name="last_name")
>>> to_json(jean, person_strategy)
'{"family_name": "d\'Arc", "ssn": "N/A", "given_name": "Jeanne"}'

Derived Fields
--------------

What if we wanted one field called ``full_name`` instead of the individual ``first_name``
and ``last_name`` properties?  We'd do that by creating a ``callable`` (generally a function)
that will be called with an instance of the model and an optional context (any object).

>>> def full_name_func(obj):
...     return obj.first_name + ' ' + obj.last_name

>>> person_strategy = ModelStrategy(Person).include(full_name=full_name_func)
>>> to_json(jean, person_strategy)
'{"full_name": "Jeanne d\'Arc"}'

Ok, let's assume we want to include the SSN field only if it looks like a real SSN.  We'll
do that by *overriding* the default ``ssn`` property that returns a special ``SKIP`` object
that will tell the serializer to not include the field in the json output.

>>> def ssn_func(obj):
...     if len(obj.ssn) and obj.ssn[0].isdigit():
...         return obj.ssn
...     return SKIP

**NOTE:** restler won't allow you to hide an exposed field by *just* redefining it.  You must
explicitly ``override`` it.  Here, since we're explicitly saying to ``include_all_fields``
we need to ``override`` ``ssn``

>>> person_strategy = ModelStrategy(Person, include_all_fields=True).override(ssn=ssn_func)

So here we see that the ``ssn`` field is skipped for Jean.

>>> to_json(jean, person_strategy)
'{"first_name": "Jeanne", "last_name": "d\'Arc"}'

But in Kurt's json, ssn is included:

>>> to_json(Person(first_name="Kurt", last_name="Cobain", ssn="536-90-4399"), person_strategy)
'{"first_name": "Kurt", "last_name": "Cobain", "ssn": "536-90-4399"}'

Context Objects
---------------

Sometimes it's important to change how serialization is done based on some state of the system.
For example, perhaps we want to display ``ssn`` only if the user is logged in.  We'd do that
by passing in a ``context`` object (usually a ``dictionary``) which will be passed to each
``callable`` that takes two parameters (the first parameter being the model instance).  Let's redo
the above example using a ``context`` object.

>>> def ssn_func(obj, context):
...     if context.has_key('is_logged_in') and bool(context['is_logged_in']):
...         return obj.ssn
...     return SKIP

>>> person_strategy = ModelStrategy(Person, include_all_fields=True).override(ssn=ssn_func)

>>> to_json(Person(first_name="Kurt", last_name="Cobain", ssn="536-90-4399"), person_strategy, dict(is_logged_in=True))
'{"first_name": "Kurt", "last_name": "Cobain", "ssn": "536-90-4399"}'

>>> to_json(Person(first_name="Kurt", last_name="Cobain", ssn="536-90-4399"), person_strategy, dict(is_logged_in=False))
'{"first_name": "Kurt", "last_name": "Cobain"}'


Serialization Strategies
------------------------

Most of the time we're not dealing with just one model but rather a collection of models
that we want to serialize in a consistent manner -- most likely for a specific ``version`` of
an API. The container is called a ``SerializationStrategy``.  You don't normally instantiate
a ``SerializationStrategy``.  Rather, you combine two or more ``ModelStrategy`` instances together
and the result is a ``SerializationStrategy``

Here's an example:

>>> class Address(db.Model):
...     street1 = db.StringProperty()
...     street2 = db.StringProperty()
...     city = db.StringProperty()
...     state = db.StringProperty()
...     zip = db.StringProperty()

>>> ser_strategy = ModelStrategy(Person, include_all_fields=True) + ModelStrategy(Address, include_all_fields=True)
>>> addr = Address(street1="4422 Colfax Ave.", city="Minneapolis", state="MN", zip="55407")
>>> to_json([jean, addr], ser_strategy)
'[{"first_name": "Jeanne", "last_name": "d\'Arc", "ssn": "N/A"}, {"city": "Minneapolis", "street2": null, "state": "MN", "zip": "55407", "street1": "4422 Colfax Ave."}]'

Here's an example of how you might version an API

>>> v1_person_strategy = ModelStrategy(Person, include_all_fields=True)
>>> v1_address_strategy = ModelStrategy(Address).include("street1", "city", "state", "zip")

>>> v2_person_strategy =  v1_person_strategy.exclude("ssn") # shouldn't include ssn
>>> v2_address_strategy = v1_address_strategy.include("street2") # forgot street2

>>> v1_strategy = v1_person_strategy + v1_address_strategy
>>> v2_strategy = v2_person_strategy + v2_address_strategy

>>> to_json([jean, addr], v1_strategy)
'[{"first_name": "Jeanne", "last_name": "d\'Arc", "ssn": "N/A"}, {"street1": "4422 Colfax Ave.", "state": "MN", "zip": "55407", "city": "Minneapolis"}]'

>>> to_json([jean, addr], v2_strategy)
'[{"first_name": "Jeanne", "last_name": "d\'Arc"}, {"street1": "4422 Colfax Ave.", "state": "MN", "street2": null, "zip": "55407", "city": "Minneapolis"}]'

"""