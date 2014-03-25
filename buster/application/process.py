from collections import OrderedDict
from datetime import datetime, timedelta
import itertools
from time import mktime

from google.appengine.ext import ndb

from constants import OVERFLOW_REASON
from poster import prepare_entry_from_item
from utils import guid_for_item


@ndb.tasklet
def find_new_entries(cls, parsed_feed, parent_key):

    keys_by_guid = {guid: ndb.Key(cls, guid, parent=parent_key) for guid in parsed_feed.iterkeys()}
    entries = yield ndb.get_multi_async(keys_by_guid.values())
    old_guids = [x.key.id() for x in entries if x]
    new_guids = filter(lambda x: x not in old_guids, keys_by_guid.keys())

    raise ndb.Return(keys_by_guid, new_guids, old_guids)


def create_new_entries_for_guids(cls, keys_by_guid, new_guids):
    return {x: cls(key=keys_by_guid.get(x), guid=x, creating=True) for x in new_guids}


@ndb.tasklet
def stage_new_entries(cls, parsed_feed, parent_key):
    keys_by_guid, new_guids, old_guids = yield find_new_entries(cls, parsed_feed, parent_key)

    new_entries_by_guid = create_new_entries_for_guids(cls, keys_by_guid, new_guids)

    raise ndb.Return(new_entries_by_guid, new_guids, old_guids)


def date_filter():
    now = datetime.now()
    two_days_ago = now - timedelta(days=2)

    def _filter(entry):
        published_parsed = entry.get('published_parsed')
        if not published_parsed:
            return True

        published_parsed = datetime.fromtimestamp(mktime(published_parsed))

        if published_parsed > two_days_ago:
            return True

        return False

    return _filter


def filter_entries(entries):
    filters = [date_filter()]

    filtered_entries = entries
    for _filter in filters:
        filtered_entries = itertools.ifilter(_filter, filtered_entries)

    return list(filtered_entries)


def get_entries_by_guid(parsed_feed):
    return OrderedDict((guid_for_item(x), x) for x in filter_entries(parsed_feed.entries))


def process_parsed_feed(cls, parsed_feed, feed, overflow, overflow_reason=OVERFLOW_REASON.BACKLOG):

    feed_entries_by_guid = get_entries_by_guid(parsed_feed)

    new_entries_by_guid, new_guids, old_guids = yield stage_new_entries(cls, feed_entries_by_guid, feed.key)

    yield ndb.put_multi_async(new_entries_by_guid.values())

    entry_items = feed_entries_by_guid.items()
    # If we process first time feeds backwards the entries will be in the right added order
    entry_items = reversed(entry_items)

    published = overflow
    futures = []
    counter = 0
    first_time = getattr(feed, 'first_time', False)
    for guid, item in entry_items:
        entry = new_entries_by_guid.get(guid)
        if not entry:
            continue

        # We only need the first three items to be fully fleshed out on the first fetch because that is all
        # The user can see in the preview area.
        # Otherwise always fetch remote data
        remote_fetch = True
        if first_time and counter > 2:
            remote_fetch = False

        added = datetime.now()
        futures.append((entry, prepare_entry_from_item(item, feed, overflow, overflow_reason, published, added, remote_fetch)))
        counter += 1

    for entry, future in futures:
        entry_kwargs = yield future
        if not entry_kwargs:
            continue

        entry_kwargs.pop('parent')
        entry_kwargs['creating'] = False
        entry.populate(**entry_kwargs)

    if len(futures):
        feed.is_dirty = True
        yield feed.put_async()

    yield ndb.put_multi_async(new_entries_by_guid.values())

    raise ndb.Return((new_guids, old_guids))
