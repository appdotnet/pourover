#!/usr/bin/env python
# encoding: utf-8
import os
import sys
import unittest
import json
from datetime import timedelta

from google.appengine.ext import testbed
from google.appengine.api import memcache


sys.path.insert(1, os.path.join(os.path.abspath('./buster/'), 'lib'))
sys.path.insert(1, os.path.join(os.path.abspath('./buster')))
from agar.test import MockUrlfetchTest
# from rss_to_adn import Feed
from application import app
from application.models import Entry, User, Feed

XML_TEMPLATE = """
<?xml version='1.0' encoding='utf-8'?>
<rss xmlns:atom="http://www.w3.org/2005/Atom" xmlns:geo="http://www.w3.org/2003/01/geo/wgs84_pos#" xmlns:georss="http://www.georss.org/georss" version="2.0">
    <channel>
        %s
        <title>Busters RSS feed</title>
        <link>http://example.com/buster</link>
        <description>
            Hi, my name is Buster.
        </description>
        <atom:link href="http://example.com/buster/rss" type="application/rss+xml" rel="self"/>
        <item>
            <title>
                %s
            </title>
            <description>
                %s
            </description>
            <pubDate>Wed, 19 Jun 2013 17:59:53 -0000</pubDate>
            <guid>http://example.com/buster/%s</guid>
            <link>http://example.com/buster/%s</link>
        </item>
    </channel>
</rss>
"""

FAKE_ACCESS_TOKEN = 'theres_always_posts_in_the_banana_stand'


class BusterTestCase(MockUrlfetchTest):
    def setUp(self):
        super(BusterTestCase, self).setUp()
        # Flask apps testing. See: http://flask.pocoo.org/docs/testing/
        app.config['TESTING'] = True
        app.config['CSRF_ENABLED'] = False
        self.app = app.test_client()

        self.clear_datastore()

    def tearDown(self):
        self.testbed.deactivate()

    def buildRSS(self, title, description, guid, link, use_hub=False):
        hub = ''
        if use_hub:
            hub = '<link rel="hub" href="http://pubsubhubbub.appspot.com"/>'
        return XML_TEMPLATE % (hub, title, description, guid, link)

    def buildMockUserResponse(self, username='voidfiles', id=3):
        return {
            'data': {
                'id': unicode(id),
                'username': username
            }
        }

    def authHeaders(self, access_token=FAKE_ACCESS_TOKEN):
        return {
            'Authorization': 'Bearer %s' % access_token
        }

    def setMockUser(self,):
        user_data = self.buildMockUserResponse()
        memcache.set('user:%s' % FAKE_ACCESS_TOKEN, json.dumps(user_data), 60 * 60)
        user = User(adn_user_id=int(user_data['data']['id']), access_token=FAKE_ACCESS_TOKEN)
        user.put()

    def testAuth(self):
        resp = self.app.get('/api/feeds/1')
        assert resp.status_code == 401
        mock_user_response = json.dumps(self.buildMockUserResponse())

        self.set_response("https://alpha-api.app.net/stream/0/users/me", content=mock_user_response, status_code=200)
        resp = self.app.get('/api/feeds', headers=self.authHeaders())

        assert resp.status_code == 200
        assert User.query().count() == 1

        resp = self.app.get('/api/feeds', headers=self.authHeaders())

        assert User.query().count() == 1

    def testFeed(self):
        self.setMockUser()
        self.set_response("https://alpha-api.app.net/stream/0/posts", content='', status_code=200, method="POST")
        resp = self.app.get('/api/feeds', headers=self.authHeaders())
        json_resp = json.loads(resp.data)
        assert len(json_resp['data']) == 0

        self.set_response("http://example.com/rss", content=self.buildRSS('test', 'test', 'test_1', 'test_1'), status_code=200)
        test_feed_url = 'http://example.com/rss'
        resp = self.app.post('/api/feeds', data=dict(
            feed_url=test_feed_url,
            include_summary='true',
            max_stories_per_period=0,
            schedule_period=5,
        ), headers=self.authHeaders())

        assert 0 == Entry.query().count()

        resp = self.app.post('/api/feeds', data=dict(
            feed_url=test_feed_url,
            include_summary='true',
            max_stories_per_period=1,
            schedule_period=5,
        ), headers=self.authHeaders())
        json_resp = json.loads(resp.data)
        assert json_resp['data']['feed_url'] == test_feed_url
        assert 1 == Entry.query().count()

        feed_id = json_resp['data']['feed_id']
        resp = self.app.get('/api/feeds/%s' % feed_id, headers=self.authHeaders())
        json_resp = json.loads(resp.data)
        assert len(json_resp['data']['entries']) == 1
        assert json_resp['data']['entries'][0]['guid'] == "http://example.com/buster/test_1"

        resp = self.app.get('/api/feeds', headers=self.authHeaders())
        json_resp = json.loads(resp.data)
        assert len(json_resp['data']) == 1

        self.set_response("http://example.com/rss", content=self.buildRSS('test', 'test', 'test_2', 'test_2'), status_code=200)
        resp = self.app.post('/api/feeds/%s/update' % feed_id, headers=self.authHeaders())
        assert 2 == Entry.query().count()

    def testPoller(self):
        self.setMockUser()
        self.set_response("https://alpha-api.app.net/stream/0/posts", content='', status_code=200, method="POST")
        test_feed_url = 'http://example.com/rss'
        self.set_response(test_feed_url, content=self.buildRSS('test', 'test', 'test_1', 'test_1'), status_code=200)
        resp = self.app.post('/api/feeds', data=dict(
            feed_url=test_feed_url,
        ), headers=self.authHeaders())

        test_feed_url = 'http://example.com/rss2'
        self.set_response(test_feed_url, content=self.buildRSS('test', 'test', 'test_1', 'test_1'), status_code=200)

        resp = self.app.post('/api/feeds', data=dict(
            feed_url=test_feed_url,
        ), headers=self.authHeaders())

        assert 2 == Entry.query().count()

        test_feed_url = 'http://example.com/rss2'
        self.set_response(test_feed_url, content=self.buildRSS('test', 'test', 'test_2', 'test_2'), status_code=200)

        resp = self.app.get('/api/feeds/all/update/2', data=dict(
            feed_url=test_feed_url,
        ))

        assert 2 == Entry.query().count()

        resp = self.app.get('/api/feeds/all/update/1', data=dict(
            feed_url=test_feed_url,
        ))

        assert 3 == Entry.query().count()

    def testPush(self):
        self.setMockUser()
        self.set_response("https://alpha-api.app.net/stream/0/posts", content='', status_code=200, method="POST")
        self.set_response('http://pubsubhubbub.appspot.com', content='', status_code=200, method="POST")
        test_feed_url = 'http://example.com/rss'
        self.set_response(test_feed_url, content=self.buildRSS('test', 'test', 'test_1', 'test_1', use_hub=True), status_code=200)
        resp = self.app.post('/api/feeds', data=dict(
            feed_url=test_feed_url,
            include_summary=True,
            max_stories_per_period=1,
            schedule_period=5,
        ), headers=self.authHeaders())

        feed = Feed.query().get()

        resp = self.app.get('/api/feeds/%s/subscribe' % (feed.key.id(), ), query_string={
            "hub.mode": 'subscribe',
            "hub.topic": feed.feed_url,
            "hub.challenge": 'testing',
            "hub.verify_token": feed.verify_token,
        })

        assert resp.data == 'testing'

        self.set_response(test_feed_url, content=self.buildRSS('test', 'test', 'test_2', 'test_2', use_hub=True), status_code=200)
        resp = self.app.post('/api/feeds/%s/subscribe' % (feed.key.id(), ))

        assert 2 == Entry.query().count()

        assert 1 == Entry.query(Entry.published == True).count()

        resp = self.app.post('/api/feeds/%s/subscribe' % (feed.key.id(), ))

        assert 2 == Entry.query(Entry.published == True).count()

    def testSchedule(self):
        self.setMockUser()
        test_feed_url = 'http://example.com/rss'
        self.set_response(test_feed_url, content=self.buildRSS('test', 'test', 'test_1', 'test_1'), status_code=200)
        resp = self.app.post('/api/feeds', data=dict(
            feed_url=test_feed_url,
            include_summary=True,
            max_stories_per_period=1,
            schedule_period=5,
        ), headers=self.authHeaders())

        assert 0 == Entry.query(Entry.published == True).count()

        self.set_response("https://alpha-api.app.net/stream/0/posts", content='', status_code=200, method="POST")

        resp = self.app.get('/api/feeds/all/update/1')

        assert 1 == Entry.query(Entry.published == True).count()

        self.set_response(test_feed_url, content=self.buildRSS('test', 'test', 'test_2', 'test_2'), status_code=200)
        resp = self.app.get('/api/feeds/all/update/1', data=dict(
            feed_url=test_feed_url,
        ))

        # Should have been rate limited
        assert 1 == Entry.query(Entry.published == True).count()

        # Set the entry back in time
        first_entry = Entry.query().get()
        first_entry.published_at = first_entry.published_at - timedelta(minutes=10)
        first_entry.put()

        self.set_response(test_feed_url, content=self.buildRSS('test', 'test', 'test_2', 'test_2'), status_code=200)
        resp = self.app.get('/api/feeds/all/update/1', data=dict(
            feed_url=test_feed_url,
        ))

    def testMulitpleSchedule(self):
        self.setMockUser()
        test_feed_url = 'http://example.com/rss'
        self.set_response(test_feed_url, content=self.buildRSS('test', 'test', 'test_1', 'test_1'), status_code=200)
        resp = self.app.post('/api/feeds', data=dict(
            feed_url=test_feed_url,
            include_summary=True,
            max_stories_per_period=2,
            schedule_period=5,
        ), headers=self.authHeaders())

        assert 0 == Entry.query(Entry.published == True).count()

        self.set_response("https://alpha-api.app.net/stream/0/posts", content='', status_code=200, method="POST")

        resp = self.app.get('/api/feeds/all/update/1')
        self.set_response(test_feed_url, content=self.buildRSS('test', 'test', 'test_2', 'test_2'), status_code=200)
        resp = self.app.get('/api/feeds/all/update/1')

        # Should not have been rate limited
        assert 2 == Entry.query(Entry.published == True).count()

        self.set_response(test_feed_url, content=self.buildRSS('test', 'test', 'test_3', 'test_3'), status_code=200)
        resp = self.app.get('/api/feeds/all/update/1')

        # Should have been rate limited
        assert 2 == Entry.query(Entry.published == True).count()

        # Set the entry back in time
        first_entry = Entry.query().get()
        first_entry.published_at = first_entry.published_at - timedelta(minutes=10)
        first_entry.put()

        resp = self.app.get('/api/feeds/all/update/1')
        assert 3 == Entry.query(Entry.published == True).count()

if __name__ == '__main__':
    unittest.main()
