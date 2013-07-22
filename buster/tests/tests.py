#!/usr/bin/env python
# encoding: utf-8
import os
import sys
import unittest
import json
from datetime import timedelta

import inspect, os

from google.appengine.ext import testbed
from google.appengine.api import memcache

import feedparser

RSS_MOCKS = {}
true_parse = feedparser.parse


def fake_parse(url, *args, **kwargs):
    content = RSS_MOCKS.get(url, url)
    parsed_feed = true_parse(content, *args, **kwargs)
    if content != url:
        parsed_feed.status = 200
        parsed_feed.etag = ''

    return parsed_feed

feedparser.parse = fake_parse

sys.path.insert(1, os.path.join(os.path.abspath('./buster/'), 'lib'))
sys.path.insert(1, os.path.join(os.path.abspath('./buster')))
from agar.test import MockUrlfetchTest
# from rss_to_adn import Feed
from application import app
from application.models import Entry, User, Feed, OVERFLOW_REASON
from application import settings

RSS_ITEM = """
    <item>
        <title>
            %(unique_key)s
        </title>
        <description>
            %(unique_key)s
        </description>
        <pubDate>Wed, 19 Jun 2013 17:59:53 -0000</pubDate>
        <guid>http://example.com/buster/%(unique_key)s</guid>
        <link>http://example.com/buster/%(unique_key)s</link>
    </item>
"""

XML_TEMPLATE = """
<?xml version='1.0' encoding='utf-8'?>
<rss xmlns:atom="http://www.w3.org/2005/Atom" xmlns:geo="http://www.w3.org/2003/01/geo/wgs84_pos#" xmlns:georss="http://www.georss.org/georss" version="2.0">
    <channel>
        %(hub)s
        <title>Busters RSS feed</title>
        <link>http://example.com/buster</link>
        <description>
            Hi, my name is Buster.
        </description>
        <atom:link href="http://example.com/buster/rss" type="application/rss+xml" rel="self"/>
        %(items)s
    </channel>
</rss>
"""

HTML_PAGE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
        <link rel="alternate" type="application/rss+xml" title="TechCrunch &raquo; Feed" href="http://techcrunch.com/feed/" />
        <link rel="alternate" type="application/rss+xml" title="TechCrunch &raquo; Comments Feed" href="http://techcrunch.com/comments/feed/" />
</head>
<body>
</body>
</html>
"""


def get_file_from_data(fname):
    return open(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe()))) + fname).read()


FAKE_POST_OBJ_RESP = get_file_from_data('/data/post_resp.json')

FAKE_ACCESS_TOKEN = 'theres_always_posts_in_the_banana_stand'


class BusterTestCase(MockUrlfetchTest):
    def setUp(self):
        super(BusterTestCase, self).setUp()
        # Flask apps testing. See: http://flask.pocoo.org/docs/testing/
        app.config['TESTING'] = True
        app.config['CSRF_ENABLED'] = False
        self.app = app.test_client()

        self.set_response("https://alpha-api.app.net/stream/0/posts", content=FAKE_POST_OBJ_RESP, status_code=200, method="POST")
        self.clear_datastore()

    def tearDown(self):
        self.testbed.deactivate()

    def buildRSS(self, unique_key, use_hub=False, items=1):
        hub = ''
        if use_hub:
            hub = '<link rel="hub" href="http://pubsubhubbub.appspot.com"/>'

        items = [RSS_ITEM % {'unique_key': '%s_%s' % (unique_key, x)} for x in xrange(0, items)]

        return XML_TEMPLATE % ({'hub': hub, 'items': ''.join(items)})

    def set_rss_response(self, url, content='', status_code=200, headers=None):
        self.set_response(url, content=content, status_code=status_code, headers=headers)

    def buildMockUserResponse(self, username='voidfiles', id=3):
        return {
            'data': {
                'user': {
                    'id': unicode(id),
                    'username': username,
                },
                'app': {
                    'client_id': settings.CLIENT_ID,
                }
            }
        }

    def authHeaders(self, access_token=FAKE_ACCESS_TOKEN):
        return {
            'Authorization': 'Bearer %s' % access_token
        }

    def setMockUser(self, access_token=FAKE_ACCESS_TOKEN, username='voidfiles', id=3):
        user_data = self.buildMockUserResponse(username=username, id=id)
        memcache.set('user:%s' % access_token, json.dumps(user_data), 60 * 60)
        user = User(access_token=access_token)
        user.put()

    def testAuth(self):
        resp = self.app.get('/api/feeds/1')
        assert resp.status_code == 401
        mock_user_response = json.dumps(self.buildMockUserResponse())

        self.set_response("https://alpha-api.app.net/stream/0/token", content=mock_user_response, status_code=200)
        resp = self.app.get('/api/feeds', headers=self.authHeaders())

        assert resp.status_code == 200
        assert User.query().count() == 1

        resp = self.app.get('/api/feeds', headers=self.authHeaders())

        assert User.query().count() == 1

    def testFeed(self):
        self.setMockUser()
        resp = self.app.get('/api/feeds', headers=self.authHeaders())
        json_resp = json.loads(resp.data)
        assert len(json_resp['data']) == 0

        self.set_rss_response("http://example.com/rss", content=self.buildRSS('test', items=10), status_code=200)
        test_feed_url = 'http://example.com/rss'

        # Should fail validation
        resp = self.app.post('/api/feeds', data=dict(
            feed_url=test_feed_url,
            max_stories_per_period=0,
            schedule_period=5,
        ), headers=self.authHeaders())
        assert 0 == Feed.query().count()

        resp = self.app.post('/api/feeds', data=dict(
            feed_url=test_feed_url,
            include_summary='true',
            max_stories_per_period=1,
            schedule_period=5,
        ), headers=self.authHeaders())
        json_resp = json.loads(resp.data)
        assert json_resp['data']['feed_url'] == test_feed_url
        assert 10 == Entry.query(Entry.published == True, Entry.overflow == True).count()

        feed_id = json_resp['data']['feed_id']
        resp = self.app.get('/api/feeds/%s' % feed_id, headers=self.authHeaders())
        json_resp = json.loads(resp.data)
        assert len(json_resp['data']['entries']) == 10
        assert json_resp['data']['entries'][0]['guid'] == "http://example.com/buster/test_0"

        # Shouldn't be able to create two feeds for the same user
        resp = self.app.post('/api/feeds', data=dict(
            feed_url=test_feed_url,
            include_summary='true',
            max_stories_per_period=1,
            schedule_period=5,
        ), headers=self.authHeaders())
        json_resp = json.loads(resp.data)
        assert 1 == Feed.query().count()

        resp = self.app.get('/api/feeds', headers=self.authHeaders())
        json_resp = json.loads(resp.data)
        assert len(json_resp['data']) == 1

        self.set_rss_response("http://example.com/rss", content=self.buildRSS('test2'), status_code=200)
        feed = Feed.query().get()
        Entry.update_for_feed(feed)
        assert 11 == Entry.query().count()

    def testPoller(self):
        self.setMockUser()
        another_fake_access_token = 'another_banana_stand'
        self.setMockUser(access_token=another_fake_access_token, username='george', id=2)
        test_feed_url = 'http://example.com/rss'
        self.set_rss_response(test_feed_url, content=self.buildRSS('test'), status_code=200)
        resp = self.app.post('/api/feeds', data=dict(
            feed_url=test_feed_url,
        ), headers=self.authHeaders())

        test_feed_url = 'http://example.com/rss2'
        self.set_rss_response(test_feed_url, content=self.buildRSS('test'), status_code=200)

        resp = self.app.post('/api/feeds', data=dict(
            feed_url=test_feed_url,
        ), headers={'Authorization': 'Bearer %s' % (another_fake_access_token, )})

        assert 2 == Entry.query().count()

        test_feed_url = 'http://example.com/rss2'
        self.set_rss_response(test_feed_url, content=self.buildRSS('test2'), status_code=200)

        resp = self.app.get('/api/feeds/all/update/2', headers={'X-Appengine-Cron': 'true'})

        assert 2 == Entry.query().count()

        resp = self.app.get('/api/feeds/all/update/1', headers={'X-Appengine-Cron': 'true'})

        assert 3 == Entry.query().count()

    def testPush(self):
        self.setMockUser()
        self.set_response('http://pubsubhubbub.appspot.com', content='', status_code=200, method="POST")
        test_feed_url = 'http://example.com/rss'
        self.set_rss_response(test_feed_url, content=self.buildRSS('test', use_hub=True), status_code=200)
        resp = self.app.post('/api/feeds', data=dict(
            feed_url=test_feed_url,
            include_summary=True,
            max_stories_per_period=1,
            schedule_period=5,
        ), headers=self.authHeaders())

        feed = Feed.query().get()

        resp = self.app.get('/api/feeds/%s/subscribe' % (feed.key.urlsafe(), ), query_string={
            "hub.mode": 'subscribe',
            "hub.topic": feed.feed_url,
            "hub.challenge": 'testing',
            "hub.verify_token": feed.verify_token,
        })

        assert resp.data == 'testing'

        self.set_rss_response(test_feed_url, content=self.buildRSS('test2', use_hub=True), status_code=200)
        resp = self.app.post('/api/feeds/%s/subscribe' % (feed.key.urlsafe(), ))

        assert 2 == Entry.query().count()

        assert 1 == Entry.query(Entry.published == True, Entry.overflow == False).count()

        resp = self.app.post('/api/feeds/%s/subscribe' % (feed.key.urlsafe(), ))

        assert 2 == Entry.query(Entry.published == True).count()

    def testSchedule(self):
        self.setMockUser()
        test_feed_url = 'http://example.com/rss'
        self.set_rss_response(test_feed_url, content=self.buildRSS('test1'), status_code=200)
        resp = self.app.post('/api/feeds', data=dict(
            feed_url=test_feed_url,
            include_summary=True,
            max_stories_per_period=1,
            schedule_period=5,
        ), headers=self.authHeaders())

        assert 0 == Entry.query(Entry.published == True, Entry.overflow == False).count()

        self.set_rss_response(test_feed_url, content=self.buildRSS('test2',), status_code=200)
        resp = self.app.get('/api/feeds/all/update/1', headers={'X-Appengine-Cron': 'true'})
        assert 1 == Entry.query(Entry.published == True, Entry.overflow == False).count()

        self.set_rss_response(test_feed_url, content=self.buildRSS('test3'), status_code=200)
        resp = self.app.get('/api/feeds/all/update/1', headers={'X-Appengine-Cron': 'true'})

        # Should have been rate limited
        assert 1 == Entry.query(Entry.published == True, Entry.overflow == False).count()

        # Set the entry back in time
        first_entry = Entry.query(Entry.published == True, Entry.overflow == False).get()
        first_entry.published_at = first_entry.published_at - timedelta(minutes=10)
        first_entry.put()

        self.set_rss_response(test_feed_url, content=self.buildRSS('test4'), status_code=200)
        resp = self.app.get('/api/feeds/all/update/1', headers={'X-Appengine-Cron': 'true'})

        # Should not have been rate limited
        assert 2 == Entry.query(Entry.published == True, Entry.overflow == False).count()

    def testMulitpleSchedule(self):
        self.setMockUser()
        test_feed_url = 'http://example.com/rss'
        self.set_rss_response(test_feed_url, content=self.buildRSS('test'), status_code=200)
        resp = self.app.post('/api/feeds', data=dict(
            feed_url=test_feed_url,
            include_summary=True,
            max_stories_per_period=2,
            schedule_period=5,
        ), headers=self.authHeaders())

        assert 1 == Entry.query(Entry.published == True, Entry.overflow == True).count()

        resp = self.app.get('/api/feeds/all/update/1', headers={'X-Appengine-Cron': 'true'})
        self.set_rss_response(test_feed_url, content=self.buildRSS('test2'), status_code=200)

        resp = self.app.get('/api/feeds/all/update/1', headers={'X-Appengine-Cron': 'true'})
        # Should not have been rate limited
        assert 1 == Entry.query(Entry.published == True, Entry.overflow == False).count()

        self.set_rss_response(test_feed_url, content=self.buildRSS('test3'), status_code=200)
        resp = self.app.get('/api/feeds/all/update/1', headers={'X-Appengine-Cron': 'true'})
        # Should not have been rate limited
        assert 2 == Entry.query(Entry.published == True, Entry.overflow == False).count()

        self.set_rss_response(test_feed_url, content=self.buildRSS('test4'), status_code=200)
        resp = self.app.get('/api/feeds/all/update/1', headers={'X-Appengine-Cron': 'true'})
        # Should have been rate limited
        assert 2 == Entry.query(Entry.published == True, Entry.overflow == False).count()

        # We should have burned off the latest entry
        burned_entries = Entry.query(Entry.published == True, Entry.overflow == True).fetch(2)
        assert 1 == len(burned_entries)
        # So, the first entry was burned because it was already in the feed
        assert burned_entries[0].overflow_reason == OVERFLOW_REASON.BACKLOG

    def testRssFeedDetection(self):
        self.set_rss_response('http://techcrunch.com/feed/', content=self.buildRSS('test'), status_code=200)
        self.set_response('http://techcrunch.com', content=HTML_PAGE_TEMPLATE, status_code=200, headers={'Content-Type': 'text/html'})
        resp = self.app.get('/api/feed/preview?feed_url=http://techcrunch.com', headers=self.authHeaders())
        assert 1 == len(json.loads(resp.data)['data'])

        resp = self.app.post('/api/feeds', data=dict(
            feed_url='http://techcrunch.com',
            max_stories_per_period=1,
            schedule_period=5,
        ), headers=self.authHeaders())

        feed = Feed.query().get()
        assert feed.feed_url == 'http://techcrunch.com/feed/'

    def testFeedPreview(self):
        self.set_rss_response('http://techcrunch.com/feed/', content=self.buildRSS('test'), status_code=200)
        resp = self.app.get('/api/feed/preview?feed_url=http://techcrunch.com/feed/', headers=self.authHeaders())
        assert 1 == len(json.loads(resp.data)['data'])
        self.set_rss_response('http://techcrunch.com/feed/2', content=self.buildRSS('test'), status_code=500)
        resp = self.app.get('/api/feed/preview?feed_url=http://techcrunch.com/feed/2', headers=self.authHeaders())
        assert json.loads(resp.data)['message']

        test_feed_url = 'http://example.com/rss'
        self.set_rss_response(test_feed_url, content=self.buildRSS('test'), status_code=200)
        resp = self.app.post('/api/feeds', data=dict(
            feed_url=test_feed_url,
            include_summary=True,
            max_stories_per_period=2,
            schedule_period=5,
        ), headers=self.authHeaders())

        assert 1 == Entry.query(Entry.published == True, Entry.overflow == True).count()
        feed = Feed.query().get()
        resp = self.app.get('/api/feeds/%s/preview' % (feed.key.id(), ), headers=self.authHeaders())
        assert 'data' in json.loads(resp.data)

    def testLinkedListMode(self):
        data = get_file_from_data('/data/df_feed.xml')
        self.set_rss_response('http://daringfireball.net/index.xml', content=data)
        resp = self.app.get('/api/feed/preview?feed_url=http://daringfireball.net/index.xml', headers=self.authHeaders())
        data = json.loads(resp.data)
        assert data['data'][0] == "<span><a href='http://blog.app.net/2013/07/15/pourover-for-app-net-is-now-available/?utm_medium=App.net&utm_source=PourOver'>PourOver for App.net</a></span>"

        resp = self.app.get('/api/feed/preview?linked_list_mode=true&feed_url=http://daringfireball.net/index.xml', headers=self.authHeaders())
        data = json.loads(resp.data)
        assert data['data'][0] == "<span><a href='http://daringfireball.net/linked/2013/07/17/pourover?utm_medium=App.net&utm_source=PourOver'>PourOver for App.net</a></span>"

    def testSingleItemPublish(self):
        self.setMockUser()
        test_feed_url = 'http://example.com/rss'
        self.set_rss_response(test_feed_url, content=self.buildRSS('test'), status_code=200)
        resp = self.app.post('/api/feeds', data=dict(
            feed_url=test_feed_url,
            include_summary=True,
            max_stories_per_period=2,
            schedule_period=5,
        ), headers=self.authHeaders())

        entry = Entry.query().get()
        feed = Feed.query().get()
        resp = self.app.post('/api/feeds/%s/entries/%s/publish' % (feed.key.id(), entry.key.id()), headers=self.authHeaders())

    def testLargeOverflow(self):
        self.setMockUser()
        test_feed_url = 'http://example.com/rss'
        self.set_rss_response(test_feed_url, content=self.buildRSS('test', items=6), status_code=200)
        resp = self.app.post('/api/feeds', data=dict(
            feed_url=test_feed_url,
            include_summary=True,
            max_stories_per_period=2,
            schedule_period=5,
        ), headers=self.authHeaders())

        assert 0 == Entry.query(Entry.published == True, Entry.overflow == False).count()
        self.set_rss_response(test_feed_url, content=self.buildRSS('test2', items=6), status_code=200)
        resp = self.app.get('/api/feeds/all/update/1', headers={'X-Appengine-Cron': 'true'})
        assert 2 == Entry.query(Entry.published == True, Entry.overflow == False).count()
        assert 10 == Entry.query(Entry.published == True, Entry.overflow == True).count()


    def testFeedRedirect(self):
        self.setMockUser()
        test_feed_url = 'http://example.com/rss'
        self.set_rss_response(test_feed_url, content=self.buildRSS('test', items=6), status_code=200)
        resp = self.app.post('/api/feeds', data=dict(
            feed_url=test_feed_url,
            include_summary=True,
            max_stories_per_period=2,
            schedule_period=5,
        ), headers=self.authHeaders())

        feed = Feed.query().get()
        assert feed.feed_url == test_feed_url

        test_feed_url2 = 'http://example.com/rss2'
        self.set_rss_response(test_feed_url, content='', status_code=302, headers={'Location': test_feed_url2})
        self.set_rss_response(test_feed_url2, content=self.buildRSS('test', items=6), status_code=200)
        resp = self.app.get('/api/feeds/all/update/1', headers={'X-Appengine-Cron': 'true'})

        feed = Feed.query().get()
        assert feed.feed_url == test_feed_url

        self.set_rss_response(test_feed_url, content='', status_code=301, headers={'Location': test_feed_url2})
        resp = self.app.get('/api/feeds/all/update/1', headers={'X-Appengine-Cron': 'true'})

        feed = Feed.query().get()
        assert feed.feed_url == test_feed_url2


if __name__ == '__main__':
    unittest.main()
