#!/usr/bin/env python
# encoding: utf-8
from collections import defaultdict
import logging
import os
import sys
import unittest
import json
import base64
from datetime import datetime, timedelta

import inspect

from google.appengine.api import memcache
from google.appengine.api import apiproxy_stub_map
from google.appengine.ext import ndb

sys.path.insert(1, os.path.join(os.path.abspath('./buster/'), 'lib'))
sys.path.insert(1, os.path.join(os.path.abspath('./buster')))

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

from agar.test import MockUrlfetchTest
# from rss_to_adn import Feed
from application import app
from application.models import Entry, User, Feed
from application.constants import FEED_STATE, OVERFLOW_REASON
from application.utils import append_query_string
from application.fetcher import hash_content
from application import settings

RSS_ITEM = u"""
<item>
    <title>
        %(unique_key)s
    </title>
    <description>
        %(content_image)s %(description)s
    </description>
    <pubDate>Wed, 19 Jun 2013 17:59:53 -0000</pubDate>
    <guid>http://example.com/buster/%(unique_key)s</guid>
    <link>http://example.com/buster/%(unique_key)s</link>
    %(tags)s
    %(author)s
    %(media_thumbnail)s
</item>
"""

XML_TEMPLATE = u"""
<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:atom="http://www.w3.org/2005/Atom" xmlns:geo="http://www.w3.org/2003/01/geo/wgs84_pos#" xmlns:georss="http://www.georss.org/georss" version="2.0">
    <channel>
        %(push_hub)s
        <title>Busters RSS feed</title>
        <link>http://example.com/buster</link>
        <description>
            Hi, my name is Buster. This is the second sentence.
        </description>
        %(language)s
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

HTML_PAGE_TEMPLATE_WITH_META = """
<!DOCTYPE html>
<html>
<head>
    <meta property="og:site_name" content="YouTube">
    <meta property="og:url" content="http://www.youtube.com/watch?v=ABm7DuBwJd8">
    <meta property="og:title" content="Reggie Watts: A send-off in style">
    <meta property="og:type" content="video">
    <meta property="og:image" content="http://i1.ytimg.com/vi/ABm7DuBwJd8/hqdefault.jpg?feature=og">

    <meta property="og:description" content="Reggie Watts, the final performer on the PopTech 2011 stage, sends the audience off in style with his characteristic blend of wry improvisational humor and u...">

    <meta property="og:video" content="http://www.youtube.com/v/ABm7DuBwJd8?version=3&amp;autohide=1">
    <meta property="og:video:type" content="application/x-shockwave-flash">
    <meta property="og:video:width" content="1280">
    <meta property="og:video:height" content="720">

    <meta property="fb:app_id" content="87741124305">

    <meta name="twitter:card" content="player">
    <meta name="twitter:site" content="@youtube">
    <meta name="twitter:url" content="http://www.youtube.com/watch?v=ABm7DuBwJd8">
    <meta name="twitter:title" content="Reggie Watts: A send-off in style">
    <meta name="twitter:description" content="Reggie Watts, the final performer on the PopTech 2011 stage, sends the audience off in style with his characteristic blend of wry improvisational humor and u...">
    <meta name="twitter:image" content="http://i1.ytimg.com/vi/ABm7DuBwJd8/hqdefault.jpg">
    <meta name="twitter:app:name:iphone" content="YouTube">
    <meta name="twitter:app:id:iphone" content="544007664">
    <meta name="twitter:app:name:ipad" content="YouTube">
    <meta name="twitter:app:id:ipad" content="544007664">
    <meta name="twitter:app:url:iphone" content="vnd.youtube://watch/ABm7DuBwJd8">
    <meta name="twitter:app:url:ipad" content="vnd.youtube://watch/ABm7DuBwJd8">
    <meta name="twitter:app:name:googleplay" content="YouTube">
    <meta name="twitter:app:id:googleplay" content="com.google.android.youtube">
    <meta name="twitter:app:url:googleplay" content="http://www.youtube.com/watch?v=ABm7DuBwJd8">
    <meta name="twitter:player" content="https://www.youtube.com/embed/ABm7DuBwJd8">
    <meta name="twitter:player:width" content="1280">
    <meta name="twitter:player:height" content="720">
</head>
<body>
</body>
</html>
"""

HTML_PAGE_TEMPLATE_WITH_IMAGES = """
<!DOCTYPE html>
<html>
<head>
</head>
<body>
    <img src='http://example.com/bad.jpg'>
    <img src='http://example.com/bad.jpg' width=''>
    <img src='http://example.com/bad.jpg' width='a' height='b'>
    <img src='http://example.com/bad.jpg' width='199px' height='199px'>
    <img src='http://example.com/bad.jpg' width='201px' height='199px'>
    <img src='http://example.com/good.jpg' width='210px' height='210px'>
    <img src='http://example.com/bad.jpg' width='201px' height='201px'>
    <img src='http://example.com/bad.jpg' width='999px' height='1001px'>
</body>
</html>
"""

YOUTUBE_OEMBED_RESPONSE = json.dumps({u'provider_url': u'http://www.youtube.com/', u'title': u'Auto-Tune the News #8: dragons. geese. Michael Vick. (ft. T-Pain)', u'html': u'<iframe width="459" height="344" src="http://www.youtube.com/embed/bDOYN-6gdRE?feature=oembed" frameborder="0" allowfullscreen></iframe>', u'author_name': u'schmoyoho', u'height': 344, u'thumbnail_width': 480, u'width': 459, u'version': u'1.0', u'author_url': u'http://www.youtube.com/user/schmoyoho', u'thumbnail_height': 360, u'thumbnail_url': u'http://i1.ytimg.com/vi/bDOYN-6gdRE/hqdefault.jpg', u'type': u'video', u'provider_name': u'YouTube'})
VIMEO_OEMBED_RESPONSE = json.dumps({u'is_plus': u'0', u'provider_url': u'https://vimeo.com/', u'description': u'Brad finally gets the attention he deserves.', u'title': u'Brad!', u'video_id': 7100569, u'html': u'<iframe src="http://player.vimeo.com/video/7100569" width="1280" height="720" frameborder="0" webkitAllowFullScreen mozallowfullscreen allowFullScreen></iframe>', u'author_name': u'Casey Donahue', u'height': 720, u'thumbnail_width': 1280, u'width': 1280, u'version': u'1.0', u'author_url': u'http://vimeo.com/caseydonahue', u'duration': 118, u'provider_name': u'Vimeo', u'thumbnail_url': u'http://b.vimeocdn.com/ts/294/128/29412830_1280.jpg', u'type': u'video', u'thumbnail_height': 720})
BIT_LY_RESPONSE = """{ "status_code": 200, "status_txt": "OK", "data": { "long_url": "http:\/\/daringfireball.net\/2013\/05\/facebook_home_dogfooding?utm_medium=App.net&utm_source=PourOver", "url": "http:\/\/bit.ly\/123", "hash": "1c3ehlA", "global_hash": "1c3ehlB", "new_hash": 0 } }"""


def get_file_from_data(fname):
    return open(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe()))) + fname).read()


FAKE_POST_OBJ_RESP = get_file_from_data('/data/post_resp.json')

FAKE_SMALL_IMAGE = get_file_from_data('/data/small_image.jpg')
FAKE_RIGHT_IMAGE = get_file_from_data('/data/right_image.jpg')
FAKE_LARGE_IMAGE = get_file_from_data('/data/large_image.jpg')

FAKE_ACCESS_TOKEN = 'theres_always_posts_in_the_banana_stand'

logger = logging.getLogger()
logger.setLevel(logging.WARNING)


class BusterTestCase(MockUrlfetchTest):
    def setUp(self):
        super(BusterTestCase, self).setUp()
        # Flask apps testing. See: http://flask.pocoo.org/docs/testing/
        app.config['TESTING'] = True
        app.config['CSRF_ENABLED'] = False
        self.app = app.test_client()

        self.set_response("https://alpha-api.app.net/stream/0/posts", content=FAKE_POST_OBJ_RESP, status_code=200, method="POST")
        self.clear_datastore()

        taskqueue_stub = apiproxy_stub_map.apiproxy.GetStub('taskqueue')
        dircontainingqueuedotyaml = os.path.dirname(os.path.dirname(__file__))
        taskqueue_stub._root_path = dircontainingqueuedotyaml

        self.taskqueue_stub = taskqueue_stub
        self.set_response('http://i1.ytimg.com/vi/ABm7DuBwJd8/hqdefault.jpg?feature=og', content=FAKE_SMALL_IMAGE, method="GET")
        for i in xrange(0, 12):
            for b in xrange(0, 12):
                unique_key = 'test%s_%s' % (i, b)
                unique_key2 = 'test_%s' % (i)
                self.set_response('http://example.com/buster/%s' % (unique_key), content=HTML_PAGE_TEMPLATE_WITH_META % ({'unique_key': unique_key}))
                self.set_response('http://example.com/buster/%s' % (unique_key2), content=HTML_PAGE_TEMPLATE_WITH_META % ({'unique_key': unique_key2}))

    def tearDown(self):
        self.testbed.deactivate()

    def buildRSS(self, unique_key, items=1, **kw):
        kwargs = defaultdict(unicode)
        kwargs.update(kw)

        if kwargs['push_hub']:
            kwargs['push_hub'] = '<link rel="hub" href="http://pubsubhubbub.appspot.com"/>'

        if kwargs['language']:
            kwargs['language'] = '<language>%s</language>' % kwargs['language']

        if kwargs['tags']:
            kwargs['tags'] = '\n'.join(["<category><![CDATA[%s]]></category>" % tag for tag in kwargs['tags']])

        if kwargs['author']:
            kwargs['author'] = '<dc:creator>%s</dc:creator>' % kwargs['author']

        kwargs['description'] = kwargs.get('description', unique_key)

        if kwargs['media_thumbnail']:
            if kwargs['thumb_width']:
                kwargs['thumb_width'] = 'width="%(thumb_width)s"' % kwargs

            if kwargs['thumb_height']:
                kwargs['thumb_height'] = 'height="%(thumb_height)s"' % kwargs

            kwargs['media_thumbnail'] = '<media:thumbnail url="%(media_thumbnail)s" %(thumb_width)s %(thumb_height)s time="12:05:01.123" />' % kwargs

        if kwargs['content_image']:
            if kwargs['thumb_width']:
                kwargs['thumb_width'] = 'width="%(thumb_width)spx"' % kwargs

            if kwargs['thumb_height']:
                kwargs['thumb_height'] = 'height="%(thumb_height)spx"' % kwargs

            kwargs['content_image'] = '<img src="%(content_image)s" %(thumb_width)s %(thumb_height)s/>' % kwargs

        rss_items = []
        for x in xrange(0, items):
            kwargs.update({'unique_key': '%s_%s' % (unique_key, x)})
            rss_items.append(RSS_ITEM % kwargs)

        kwargs.update({
            'items': ''.join(rss_items)
        })

        return XML_TEMPLATE % kwargs

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

    def buildMockAppResponse(self):
        return {
            'data': {
                'is_app_token': True,
                'app': {
                    'client_id': settings.CLIENT_ID,
                }
            }
        }

    def authHeaders(self, access_token=FAKE_ACCESS_TOKEN):
        return {
            'Authorization': 'Bearer %s' % access_token
        }

    def get_task_queues(self):
        """
        """
        return self.get_task_queue_stub().GetQueues()

    def get_task_queue_names(self):
        """
        """
        return [q['name'] for q in self.get_task_queues()]

    def get_task_queue_stub(self):
        """
        """
        return self.taskqueue_stub

    def clear_task_queue(self):
        stub = self.get_task_queue_stub()
        for name in self.get_task_queue_names():
            stub.FlushQueue(name)


    def execute_tasks(self, n=0, queue_name='default'):
        """
        Executes all currently queued tasks.
        """

        # Execute the task in the taskqueue
        tasks = self.taskqueue_stub.GetTasks(queue_name)
        self.assertEqual(len(tasks), n)
        # Run each of the tasks, checking that they succeeded.
        for task in tasks:
            params = base64.b64decode(task["body"])
            #response = self.app.post(task["url"], params)
            #params = task.get('params', {})
            content_type = dict(task['headers']).pop('content-type', '')
            response = self.app.post(task['url'], data=params, headers=task['headers'], content_type=content_type)
            self.assertEqual(200, response.status_code)

        self.clear_task_queue()

    def setMockUser(self, access_token=FAKE_ACCESS_TOKEN, username='voidfiles', id=3):
        user_data = self.buildMockUserResponse(username=username, id=id)
        memcache.set('user:%s' % access_token, json.dumps(user_data), 60 * 60)
        user = User(access_token=access_token)
        user.put()

    def setMockAppToken(self):
        app_data = self.buildMockAppResponse()
        self.set_response('https://alpha-api.app.net/stream/0/token', content=json.dumps(app_data), method='GET')

    def pollUpdate(self, interval_id=1, n=1, queue_name='poll'):
        resp = self.app.get('/api/feeds/all/update/%s' % (interval_id), headers={'X-Appengine-Cron': 'true'})
        self.execute_tasks(n=n, queue_name=queue_name)
        resp = self.app.get('/api/feeds/all/post', headers={'X-Appengine-Cron': 'true'})


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

        self.set_rss_response("http://example.com/awesome/", content=self.buildRSS('test', items=1), status_code=200)
        # Shouldn't be able to create two feeds for the same user
        resp = self.app.post('/api/feeds', data=dict(
            feed_url='http://example.com/awesome/',
            include_summary='true',
            max_stories_per_period=1,
            schedule_period=5,
        ), headers=self.authHeaders())
        json_resp = json.loads(resp.data)
        assert 2 == Feed.query().count()

        resp = self.app.get('/api/feeds', headers=self.authHeaders())
        json_resp = json.loads(resp.data)
        assert len(json_resp['data']) == 2
        content = self.buildRSS('test2')
        content_hash = hash_content(content)
        self.set_rss_response("http://example.com/rss", content=content, status_code=200)
        feed = Feed.query().get()
        Entry.update_for_feed(feed).get_result()
        assert 12 == Entry.query().count()

        assert content_hash == feed.last_fetched_content_hash

        new_content = self.buildRSS('test3')
        new_content_hash = hash_content(new_content)
        feed.last_fetched_content_hash = new_content_hash
        feed.put()

        self.set_rss_response("http://example.com/rss", content=new_content, status_code=200)
        Entry.update_for_feed(feed).get_result()
        assert 12 == Entry.query().count()

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

        self.pollUpdate(2, n=0)
        assert 2 == Entry.query().count()

        self.pollUpdate()

        assert 3 == Entry.query().count()

    def testPush(self):
        self.setMockUser()
        self.set_response('http://pubsubhubbub.appspot.com', content='', status_code=200, method="POST")
        test_feed_url = 'http://example.com/rss'
        self.set_rss_response(test_feed_url, content=self.buildRSS('test', push_hub=True), status_code=200)
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
        data = get_file_from_data('/data/df_feed.xml')
        resp = self.app.post('/api/feeds/%s/subscribe' % (feed.key.urlsafe(), ), data=data, headers={
            'Content-Type': 'application/xml',
        })

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
        self.pollUpdate()

        assert 1 == Entry.query(Entry.published == True, Entry.overflow == False).count()

        self.set_rss_response(test_feed_url, content=self.buildRSS('test3'), status_code=200)
        self.pollUpdate()
        # Should have been rate limited
        assert 1 == Entry.query(Entry.published == True, Entry.overflow == False).count()

        # Set the entry back in time
        first_entry = Entry.query(Entry.published == True, Entry.overflow == False).get()
        first_entry.published_at = first_entry.published_at - timedelta(minutes=10)
        first_entry.put()

        self.set_rss_response(test_feed_url, content=self.buildRSS('test4'), status_code=200)
        self.pollUpdate()

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

        self.pollUpdate()
        self.set_rss_response(test_feed_url, content=self.buildRSS('test2'), status_code=200)

        self.pollUpdate()
        # Should not have been rate limited
        assert 1 == Entry.query(Entry.published == True, Entry.overflow == False).count()

        self.set_rss_response(test_feed_url, content=self.buildRSS('test3'), status_code=200)
        self.pollUpdate()
        # Should not have been rate limited
        assert 2 == Entry.query(Entry.published == True, Entry.overflow == False).count()

        self.set_rss_response(test_feed_url, content=self.buildRSS('test4'), status_code=200)
        self.pollUpdate()
        # Should have been rate limited
        assert 2 == Entry.query(Entry.published == True, Entry.overflow == False).count()

        # We should have burned off the latest entry
        burned_entries = Entry.query(Entry.published == True, Entry.overflow == True).fetch(2)
        assert 1 == len(burned_entries)
        # So, the first entry was burned because it was already in the feed
        assert burned_entries[0].overflow_reason == OVERFLOW_REASON.BACKLOG

    def testRssFeedDetection(self):
        self.setMockUser()
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
        self.setMockUser()
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
        self.setMockUser()
        data = get_file_from_data('/data/df_feed.xml')
        self.set_rss_response('http://daringfireball.net/index.xml', content=data)
        self.set_response('http://daringfireball.net/linked/2013/07/17/pourover', content=HTML_PAGE_TEMPLATE_WITH_META)
        self.set_response('http://blog.app.net/2013/07/15/pourover-for-app-net-is-now-available/', content=HTML_PAGE_TEMPLATE_WITH_META)
        resp = self.app.get('/api/feed/preview?feed_url=http://daringfireball.net/index.xml', headers=self.authHeaders())
        data = json.loads(resp.data)
        assert data['data'][0]['html'] == "<span><a href='http://blog.app.net/2013/07/15/pourover-for-app-net-is-now-available/?utm_medium=App.net&utm_source=PourOver'>PourOver for App.net</a></span>"

        resp = self.app.get('/api/feed/preview?linked_list_mode=true&feed_url=http://daringfireball.net/index.xml', headers=self.authHeaders())
        data = json.loads(resp.data)
        assert data['data'][0]['html'] == "<span><a href='http://daringfireball.net/linked/2013/07/17/pourover?utm_medium=App.net&utm_source=PourOver'>PourOver for App.net</a></span>"

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
            max_stories_per_period=1,
            schedule_period=5,
        ), headers=self.authHeaders())

        assert 0 == Entry.query(Entry.published == True, Entry.overflow == False).count()

        self.set_rss_response(test_feed_url, content=self.buildRSS('test2', items=6), status_code=200)
        self.pollUpdate()

        assert 0 == Entry.query(Entry.published == True, Entry.overflow == False).count()
        assert 12 == Entry.query(Entry.published == True, Entry.overflow == True).count()

        self.set_rss_response(test_feed_url, content=self.buildRSS('test2', items=7), status_code=200)
        self.pollUpdate()

        assert 1 == Entry.query(Entry.published == True, Entry.overflow == False).count()

    def testFeedRedirect(self):
        self.setMockUser()
        test_feed_url = 'http://example.com/rss'
        self.set_rss_response(test_feed_url, content=self.buildRSS('test', items=6), status_code=200)
        self.app.post('/api/feeds', data=dict(
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
        self.pollUpdate()

        feed = Feed.query().get()
        assert feed.feed_url == test_feed_url

        self.set_rss_response(test_feed_url2, content=self.buildRSS('test1', items=6), status_code=200)
        self.set_rss_response(test_feed_url, content='', status_code=301, headers={'Location': test_feed_url2})

        self.pollUpdate()

        feed = Feed.query().get()
        assert feed.feed_url == test_feed_url2

    def testLanguage(self):
        self.setMockUser()
        test_feed_url = 'http://example.com/rss'
        self.set_rss_response(test_feed_url, content=self.buildRSS('test', items=6), status_code=200)
        self.app.post('/api/feeds', data=dict(
            feed_url=test_feed_url,
            include_summary=True,
            max_stories_per_period=2,
            schedule_period=5,
        ), headers=self.authHeaders())

        feed = Feed.query().get()
        assert feed.language is None

        self.set_rss_response(test_feed_url, content=self.buildRSS('test', items=6, language='en-US'), status_code=200)
        self.pollUpdate()
        feed = Feed.query().get()
        assert feed.language == 'en'

    def testAuthor(self):
        self.setMockUser()
        test_feed_url = 'http://example.com/rss'
        self.set_rss_response(test_feed_url, content=self.buildRSS('test', items=1), status_code=200)
        self.app.post('/api/feeds', data=dict(
            feed_url=test_feed_url,
            include_summary=True,
            max_stories_per_period=2,
            schedule_period=5,
        ), headers=self.authHeaders())

        entry = Entry.query().order(-Entry.added).get()
        assert None == entry.author

        self.set_rss_response(test_feed_url, content=self.buildRSS('test1', items=1, author='Alex Kessinger'), status_code=200)
        self.pollUpdate()
        entry = Entry.query().order(-Entry.added).get()

        assert 'Alex Kessinger' == entry.author

    def testTags(self):
        self.setMockUser()
        test_feed_url = 'http://example.com/rss'
        self.set_rss_response(test_feed_url, content=self.buildRSS('test', items=1), status_code=200)
        self.app.post('/api/feeds', data=dict(
            feed_url=test_feed_url,
            include_summary=True,
            max_stories_per_period=2,
            schedule_period=5,
        ), headers=self.authHeaders())

        entry = Entry.query().order(-Entry.added).get()
        assert [] == entry.tags

        self.set_rss_response(test_feed_url, content=self.buildRSS('test1', items=1, tags=['example', 'feed']), status_code=200)
        self.pollUpdate()
        entry = Entry.query().order(-Entry.added).fetch(2)[0]
        assert ['example', 'feed'] == entry.tags

    def testIncludeSummary(self):
        self.setMockUser()
        test_feed_url = 'http://example.com/rss'
        self.set_rss_response(test_feed_url, content=self.buildRSS('test', items=1), status_code=200)
        resp = self.app.get('/api/feed/preview?feed_url=%s' % (test_feed_url), headers=self.authHeaders())
        data = json.loads(resp.data)
        assert data['data'][0]['html'] == "<span><a href='http://example.com/buster/test_0?utm_medium=App.net&utm_source=PourOver'>test_0</a></span>"

        resp = self.app.get('/api/feed/preview?include_summary=1&feed_url=%s' % (test_feed_url), headers=self.authHeaders())
        data = json.loads(resp.data)
        assert data['data'][0]['html'] == "<span><a href='http://example.com/buster/test_0?utm_medium=App.net&utm_source=PourOver'>test_0</a><br>test</span>"

    def testIncludeVideo(self):
        self.setMockUser()
        self.set_response('http://vimeo.com/api/oembed.json?url=http%3A%2F%2Fvimeo.com%2F7100569', content=VIMEO_OEMBED_RESPONSE)
        self.set_response('http://www.youtube.com/oembed?url=http%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3DPTHS7qjEDTs', content=YOUTUBE_OEMBED_RESPONSE)
        urls = [
            ('//www.youtube.com/v/PTHS7qjEDTs?version=3&amp;hl=en_US&amp;rel=0', 'http://i1.ytimg.com/vi/bDOYN-6gdRE/hqdefault.jpg'),
            ('//vimeo.com/7100569', 'http://b.vimeocdn.com/ts/294/128/29412830_1280.jpg')
        ]
        embed_types = ['<embed height="360" src="%s" type="application/x-shockwave-flash" width="640" />', '<iframe src="%s"></iframe>']
        test_feed_url = 'http://example.com/rss'
        for url, thumbnail_url in urls:
            for embed_type in embed_types:
                description = embed_type % url
                self.set_rss_response(test_feed_url, content=self.buildRSS('test', items=1, description=description), status_code=200)
                resp = self.app.get('/api/feed/preview?include_video=1&feed_url=%s' % (test_feed_url), headers=self.authHeaders())
                data = json.loads(resp.data)
                assert data['data'][0]['thumbnail_image_url'] == thumbnail_url
                assert data['data'][0]['html'] == "<span><a href='http://example.com/buster/test_0?utm_medium=App.net&utm_source=PourOver'>test_0</a></span>"

    def testThumbnail(self):
        self.setMockUser()
        self.set_response('http://example.com/small.jpg', content=FAKE_SMALL_IMAGE)
        self.set_response('http://example.com/right.jpg', content=FAKE_RIGHT_IMAGE)
        self.set_response('http://example.com/large.jpg', content=FAKE_LARGE_IMAGE)
        test_feed_url = 'http://example.com/rss'

        test_images = [
            (False, 'http://example.com/small.jpg', '100', '100', FAKE_SMALL_IMAGE),
            (True, 'http://example.com/right.jpg', '201', '201', FAKE_RIGHT_IMAGE),
            (False, 'http://example.com/large.jpg', '1001', '1001', FAKE_LARGE_IMAGE),
        ]

        for embed_type in ['media_thumbnail', 'content_image']:
            for should_work, url, width, height, img_content in test_images:
                kwargs = {
                    embed_type: url
                }

                for i in range(0, 1):
                    self.set_rss_response(test_feed_url, content=self.buildRSS('test', items=1, **kwargs), status_code=200)
                    resp = self.app.get('/api/feed/preview?include_thumb=1&feed_url=%s' % (test_feed_url), headers=self.authHeaders())
                    data = json.loads(resp.data)
                    if should_work:
                        #print '%s %s %s' % (embed_type, data['data'][0].get('thumbnail_image_url'), url)
                        assert data['data'][0].get('thumbnail_image_url') == url
                    else:
                        assert data['data'][0].get('thumbnail_image_url') is None

                    kwargs.update({
                        'width': width,
                        'height': height,
                    })

        self.set_rss_response(test_feed_url, content=self.buildRSS('test'), status_code=200)
        for should_work, url, width, height, img_content in test_images:
            # Final test for meta tags
            html = HTML_PAGE_TEMPLATE_WITH_META % ({'unique_key': 'test_0'})
            html = html.replace('http://i1.ytimg.com/vi/ABm7DuBwJd8/hqdefault.jpg?feature=og', url)
            self.set_response('http://example.com/buster/test_0', content=html, method='GET')
            resp = self.app.get('/api/feed/preview?include_thumb=1&feed_url=%s' % (test_feed_url), headers=self.authHeaders())
            data = json.loads(resp.data)
            if should_work:
                assert data['data'][0].get('thumbnail_image_url') == url
            else:
                assert data['data'][0].get('thumbnail_image_url') is None

        self.set_rss_response(test_feed_url, content=self.buildRSS('test1'), status_code=200)
        self.set_response('http://example.com/buster/test1_0', content=HTML_PAGE_TEMPLATE_WITH_IMAGES, method='GET')
        resp = self.app.post('/api/feeds', data=dict(
            feed_url=test_feed_url,
        ), headers=self.authHeaders())

        resp = self.app.get('/api/feed/preview?include_thumb=1&feed_url=%s' % (test_feed_url), headers=self.authHeaders())
        data = json.loads(resp.data)
        assert data['data'][0].get('thumbnail_image_url') is None

        feed = Feed.query().get()
        feed.image_in_html = True
        feed.put()

        self.set_rss_response(test_feed_url, content=self.buildRSS('test2'), status_code=200)
        self.set_response('http://example.com/buster/test2_0', content=HTML_PAGE_TEMPLATE_WITH_IMAGES, method='GET')
        self.pollUpdate()
        assert Entry.query().fetch(2)[1].thumbnail_image_url == "http://example.com/good.jpg"

    def testIncludeSummarySentanceSplit(self):
        self.setMockUser()
        test_feed_url = 'http://example.com/rss'
        sentance_1 = 'Dog' + ('x' * 196) + '.'
        sentance_2 = ' Dxx Dxx.'
        description  = sentance_1 + sentance_2
        self.set_rss_response(test_feed_url, content=self.buildRSS('test', items=1, description=description), status_code=200)
        resp = self.app.get('/api/feed/preview?include_summary=1&feed_url=%s' % (test_feed_url), headers=self.authHeaders())
        data = json.loads(resp.data)
        assert data['data'][0]['html'] == "<span><a href='http://example.com/buster/test_0?utm_medium=App.net&utm_source=PourOver'>test_0</a><br>%s</span>" % (sentance_1)

        sentance_1 = 'x' * 201 + '.'
        sentance_2 = ' xxx.'
        description  = sentance_1 + sentance_2
        self.set_rss_response(test_feed_url, content=self.buildRSS('test', items=1, description=description), status_code=200)
        resp = self.app.get('/api/feed/preview?include_summary=1&feed_url=%s' % (test_feed_url), headers=self.authHeaders())
        data = json.loads(resp.data)
        assert data['data'][0]['html'] == "<span><a href='http://example.com/buster/test_0?utm_medium=App.net&utm_source=PourOver'>test_0</a><br>%s</span>" % (sentance_1[0:199] + u"\u2026")

        sentances = ['Dog ' * 11 + '.' for i in range(0, 8)]
        description = ' '.join(sentances)
        expected = ' '.join(['Dog ' * 11 + '.' for i in range(0, 4)])
        self.set_rss_response(test_feed_url, content=self.buildRSS('test', items=1, description=description), status_code=200)
        resp = self.app.get('/api/feed/preview?include_summary=1&feed_url=%s' % (test_feed_url), headers=self.authHeaders())
        data = json.loads(resp.data)
        assert data['data'][0]['html'] == "<span><a href='http://example.com/buster/test_0?utm_medium=App.net&utm_source=PourOver'>test_0</a><br>%s</span>" % (expected)

    def testShortUrl(self):
        self.setMockUser()
        self.set_rss_response("https://api-ssl.bitly.com/v3/shorten?login=example&apiKey=R_123&longUrl=http%3A%2F%2Fexample.com%2Fbuster%2Ftest1_0%3Futm_medium%3DApp.net%26utm_source%3DPourOver", content=BIT_LY_RESPONSE)
        test_feed_url = 'http://example.com/rss'
        self.set_rss_response(test_feed_url, content=self.buildRSS('test', items=1), status_code=200)
        resp = self.app.post('/api/feeds', data=dict(
            feed_url=test_feed_url,
            include_summary=True,
            max_stories_per_period=2,
            schedule_period=5,
            bitly_login='example',
            bitly_api_key='R_123',
        ), headers=self.authHeaders())

        self.set_rss_response(test_feed_url, content=self.buildRSS('test1', items=1), status_code=200)
        self.pollUpdate()
        entry = Entry.query().order(-Entry.added).get()
        assert entry.short_url == 'http://bit.ly/123'

    def testAppendQueryParams(self):
        assert append_query_string('http://example.com', {'t': 1}) == 'http://example.com?t=1'
        assert append_query_string('http://example.com?t=1', {'b': 1}) == 'http://example.com?t=1&b=1'
        assert append_query_string('http://www.ntvspor.net#', {'t': 1}) == 'http://www.ntvspor.net?t=1#'

    def testPushResubCron(self):
        self.app.get('/api/feeds/all/try/subscribe', headers={'X-Appengine-Cron': 'true'})

    def testDbRaceCondition(self):
        self.setMockUser()
        test_feed_url = 'http://example.com/rss'
        self.set_rss_response(test_feed_url, content=self.buildRSS('test', items=1), status_code=200)
        self.app.post('/api/feeds', data=dict(
            feed_url=test_feed_url,
            include_summary=True,
            max_stories_per_period=2,
            schedule_period=5,
        ), headers=self.authHeaders())

        feed = Feed.query().get()

        key = ndb.Key(Entry, '1', parent=feed.key)

        entry = Entry(key=key, guid='1')
        entry.put()

        entry_2 = Entry(key=key, guid='2')
        entry_2.put()

        assert Entry.query().count() == 2

    def testBadFeedRemoval(self):
        self.setMockUser()
        test_feed_url = 'http://example.com/rss'
        self.set_rss_response(test_feed_url, content=self.buildRSS('test', items=1), status_code=200)
        self.app.post('/api/feeds', data=dict(
            feed_url=test_feed_url,
            include_summary=True,
            max_stories_per_period=2,
            schedule_period=5,
        ), headers=self.authHeaders())

        feed = Feed.query().get()

        feed.last_successful_fetch = datetime.now() - timedelta(days=2)
        feed.put()

        self.set_rss_response(test_feed_url, content=self.buildRSS('test1', items=1), status_code=500)
        self.pollUpdate()

        assert feed.feed_disabled is True

    def testFeedReauthoirzation(self):
        self.setMockUser()
        test_feed_url = 'http://example.com/rss'
        self.set_rss_response(test_feed_url, content=self.buildRSS('test', items=1), status_code=200)
        self.app.post('/api/feeds', data=dict(
            feed_url=test_feed_url,
            include_summary=True,
            max_stories_per_period=2,
            schedule_period=5,
        ), headers=self.authHeaders())


        self.set_response("https://alpha-api.app.net/stream/0/posts", content=FAKE_POST_OBJ_RESP, status_code=401, method="POST")
        self.set_rss_response(test_feed_url, content=self.buildRSS('test1', items=1), status_code=200)
        self.pollUpdate()
        feed = Feed.query().get()

        assert feed.status == FEED_STATE.NEEDS_REAUTH

        resp = self.app.post('/api/feeds', data=dict(
            feed_url=test_feed_url,
            max_stories_per_period=1,
            schedule_period=5,
        ), headers={'Authorization': 'Bearer NEW_ACCESS_TOKEN'})

        feed = Feed.query().get()

        assert feed.status == FEED_STATE.ACTIVE

    def testFeedMetaDataUpdate(self):
        self.setMockUser()
        test_feed_url = 'http://example.com/rss'
        self.set_rss_response(test_feed_url, content=self.buildRSS('test', items=1), status_code=200)
        self.app.post('/api/feeds', data=dict(
            feed_url=test_feed_url,
            max_stories_per_period=1,
            schedule_period=5,
        ), headers=self.authHeaders())

        feed = Feed.query().get()
        assert feed.link == 'http://example.com/buster'
        assert feed.title == 'Busters RSS feed'
        assert feed.description == 'Hi, my name is Buster. This is the second sentence.'

    def testImageBlacklist(self):
        self.setMockUser()
        self.set_response('http://example.com/right.jpg', content=FAKE_RIGHT_IMAGE)
        test_feed_url = 'http://example.com/rss'
        image_url = 'http://example.com/right.jpg'
        self.set_rss_response(test_feed_url, content=self.buildRSS('test', items=1, media_thumbnail=image_url, thumbnail_width='201', thumb_height='201'), status_code=200)
        self.app.post('/api/feeds', data=dict(
            feed_url=test_feed_url,
            max_stories_per_period=1,
            schedule_period=5,
        ), headers=self.authHeaders())

        entry = Entry.query().get()

        assert entry.thumbnail_image_url == image_url
        feed = Feed.query().get()
        feed.image_in_rss = False
        feed.put()

        self.set_rss_response(test_feed_url, content=self.buildRSS('test1', items=1, media_thumbnail=image_url, thumbnail_width='201', thumb_height='201'), status_code=200)
        self.pollUpdate()

        entry = Entry.query().fetch(2)[0]

        assert entry.thumbnail_image_url is None

        feed = Feed.query().get()
        feed.image_in_content = False
        feed.put()

        self.set_rss_response(test_feed_url, content=self.buildRSS('test2', items=1, content_image=image_url, thumbnail_width='201', thumb_height='201'), status_code=200)
        self.pollUpdate()

        entry = Entry.query().get()

        assert entry.thumbnail_image_url is None

        feed = Feed.query().get()
        feed.image_in_meta = False
        feed.put()
        self.set_response('http://i1.ytimg.com/vi/ABm7DuBwJd8/hqdefault.jpg?feature=og', content=FAKE_RIGHT_IMAGE, method="GET")
        self.set_rss_response(test_feed_url, content=self.buildRSS('test3', items=1), status_code=200)
        self.pollUpdate()

        entry = Entry.query().get()

        assert entry.thumbnail_image_url is None


if __name__ == '__main__':
    unittest.main()
