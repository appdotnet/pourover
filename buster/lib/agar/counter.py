"""
The ``agar.counter`` module contains classes to help work with scalable counters.
"""

import datetime
import re
import time

from google.appengine.api import memcache, taskqueue
from google.appengine.ext import db, deferred

from pytz import utc


def get_interval_number(ts, duration):
    """
    Returns the number of the current interval.

    :param ts: The timestamp to convert
    :param duration: The length of the interval
    :returns: The integer interval number.
    """
    return int(time.mktime(ts.timetuple()) / duration)

class WriteBehindCounter(db.Model):
    count = db.IntegerProperty(required=True, default=0)
    
    @classmethod
    def get_value(cls, name):
        """
        Returns the value of a counter.

        :param name: The name of the counter.
        :returns: The integer value of the count.
        """
        counter = cls.get_by_key_name(name)
        if counter:
            count = counter.count
        else:
            count = 0
        memcount = memcache.get(name, cls.kind())
        if memcount:
            count += int(memcount)
        return count
    
    @classmethod
    def flush_counter(cls, name):
        """
        Flush the value of a counter.

        :param name: The name of the counter to flush.
        """
        counter = cls.get_by_key_name(name)
        if not counter:
            counter = cls(key_name=name)
        # Get the current value
        value = memcache.get(name, cls.kind())
        # Subtract it from the memcached value
        memcache.decr(name, int(value), cls.kind())
        # Store it to the counter
        counter.count += int(value)
        counter.put()
    
    @classmethod
    def incr(cls, name, interval=5, value=1):
        """Increments a counter.

        :param name: The name of the counter to increment.
        :param interval: How frequently (in seconds) to call :py:meth:`flush_counter`.
        :param value: The value to increment the counter by.
        """
        memcache.incr(name, value, cls.kind(), initial_value=0)
        interval_num = get_interval_number(datetime.datetime.now(), interval)
        task_name = '-'.join([cls.kind(), name, str(interval), str(interval_num)])
        try:
            deferred.defer(cls.flush_counter, name, _name=task_name)
        except (taskqueue.TaskAlreadyExistsError, taskqueue.TombstonedTaskError):
            pass
    

class TimedWriteBehindCounter(db.Model):
    count = db.IntegerProperty(required=True, default=0)
    timestamp = db.DateTimeProperty(required=True)
    
    @classmethod
    def normalize_ts(cls, ts):
        if ts.tzinfo is not None:
            ts = utc.normalize(ts.astimezone(utc))
        return ts
    
    @classmethod
    def get_ts_name(cls, name, ts):
        name = '%s-%s' % (name, cls.normalize_ts(ts))
        name = re.sub(r'[^a-zA-Z0-9_-]', "_", name)
        return name
    
    @classmethod
    def get_value(cls, name, ts):
        """
        Returns the value of a counter with a specified timestamp.

        :param name: The name of the counter.
        :param ts: The timestamp to get the counter value for.
        :returns: The integer value of the count.
        """
        ts_name = cls.get_ts_name(name, ts)
        counter = cls.get_by_key_name(ts_name)
        if counter:
            count = counter.count
        else:
            count = 0
        memcount = memcache.get(ts_name, cls.kind())
        if memcount:
            count += int(memcount)
        return count
    
    @classmethod
    def flush_counter(cls, name, ts):
        """
        Flushes the value of the counter with the specified name and timestamp to the datastore.

        :param name: The name of the counter to flush.
        :param ts: The timestamp to get the counter value for.
        """

        ts_name = cls.get_ts_name(name, ts)
        counter = cls.get_by_key_name(ts_name)
        if not counter:
            counter = cls(key_name=ts_name, timestamp=cls.normalize_ts(ts))
        # Get the current value
        value = memcache.get(ts_name, cls.kind())
        # Subtract it from the memcached value
        memcache.decr(ts_name, int(value), cls.kind())
        # Store it to the counter
        counter.count += int(value)
        counter.put()
    
    @classmethod
    def incr(cls, name, now=None, interval=5, countdown=0, value=1):
        """Increments a counter.

        :param name: The name of the counter to increment.
        :param interval: How frequently (in seconds) to call :py:meth:`flush_counter`.
        :param countdown: The countdown for the :py:meth:`flush_counter` task.
        :param value: The value to increment the counter by.
        """
        if now is None:
            now = datetime.datetime.now(utc)
        ts_name = cls.get_ts_name(name, now)
        memcache.incr(ts_name, value, cls.kind(), initial_value=0)
        interval_num = get_interval_number(now, interval)
        task_name = '-'.join(
            [cls.kind(), ts_name, str(interval), str(interval_num)]
        )
        try:
            deferred.defer(
                cls.flush_counter, name, now,
                _name=task_name, _countdown=countdown
            )
        except (taskqueue.TaskAlreadyExistsError, taskqueue.TombstonedTaskError):
            pass
    

class HourlyWriteBehindCounter(TimedWriteBehindCounter):
    @classmethod
    def normalize_ts(cls, ts):
        if ts.tzinfo is not None:
            ts = utc.normalize(ts.astimezone(utc))
        return datetime.datetime(
            year=ts.year, month=ts.month, day=ts.day, hour=ts.hour
        )
    
    @classmethod
    def get_ts_name(cls, name, ts):
        ts = cls.normalize_ts(ts)
        return '%s-%04d%02d%02d%02d' % (
            name, ts.year, ts.month, ts.day, ts.hour
        )
    

class DailyWriteBehindCounter(TimedWriteBehindCounter):
    tz = utc
    
    @classmethod
    def normalize_ts(cls, ts):
        if ts.tzinfo is not None:
            ts = cls.tz.normalize(ts.astimezone(cls.tz)).date()
        return datetime.datetime(year=ts.year, month=ts.month, day=ts.day)
    
    @classmethod
    def get_ts_name(cls, name, ts):
        ts = cls.normalize_ts(ts)
        return '%s-%s-%04d%02d%02d' % (
            name, str(cls.tz).replace('/', '-'), ts.year, ts.month, ts.day
        )
    

