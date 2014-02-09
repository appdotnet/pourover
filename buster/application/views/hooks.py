import hashlib
import hmac
import json
import logging

import feedparser
from flask import request, url_for
from google.appengine.api import mail
from google.appengine.api.taskqueue import Task, Queue
from google.appengine.ext import ndb

from application import app
from application.constants import UPDATE_INTERVAL, BATCH_SIZE
from application.models import FEED_TYPE_TO_CLASS, Entry, Configuration, InstagramFeed
from application.publisher.entry import publish_entry

from view_utils import jsonify

logger = logging.getLogger(__name__)


@app.route('/_ah/mail/<string:email>', methods=['POST'])
@ndb.synctasklet
def email_to_feed(email):
    logger.info('Email: %s', email)
    account, _ = email.split('@', 1)
    logger.info('Account: %s', account)
    unique_key, feed_type, version = account.split('_')
    feed_type, version = map(int, (feed_type, version))
    logger.info('unique_key: %s feed_type:%s version:%s', unique_key, feed_type, version)
    feed = FEED_TYPE_TO_CLASS[feed_type].for_email(unique_key)
    logger.info('Found feed: %s', feed)
    mail_message = mail.InboundEmailMessage(request.stream.read())
    entry = yield feed.create_entry_from_mail(mail_message)
    yield publish_entry(entry, feed)

    raise ndb.Return(jsonify(status='ok'))


email_to_feed.login_required = False


@app.route('/api/feeds/instagram/subscribe', methods=['GET'])
def instagram_subscribe():
    mode = request.args['hub.mode']
    challenge = request.args['hub.challenge']
    verify_token = request.args.get('hub.verify_token')

    if mode == 'subscribe':
        instagram_verify_token = Configuration.value_for_name('instagram_verify_token')
        if verify_token and verify_token != instagram_verify_token:
            logger.info('Failed verification feed.verify_token:%s GET verify_token:%s', instagram_verify_token, verify_token)
            return "Failed Verification", 400

        logger.info('Responding to instagram challange: %s', challenge)
        return challenge

instagram_subscribe.login_required = False


@app.route('/api/feeds/instagram/subscribe', methods=['POST'])
@ndb.synctasklet
def instagram_push_update():
    data = request.stream.read()
    instagram_client_secret = Configuration.value_for_name('instagram_client_secret')

    server_signature = request.headers.get('X-Hub-Signature', None)
    signature = hmac.new(str(instagram_client_secret), data, digestmod=hashlib.sha1).hexdigest()

    if server_signature != signature:
        logger.warn('Got PuSH subscribe POST from instagram w/o valid signature: sent=%s != expected=%s',
                    server_signature, signature)

        raise ndb.Return('')

    logger.info('Got PuSH body: %s', data)
    logger.info('Got PuSH headers: %s', request.headers)

    parsed_feed = json.loads(data)
    user_ids = [int(x.get('object_id')) for x in parsed_feed]
    feeds = InstagramFeed.query(InstagramFeed.user_id.IN(user_ids))

    cursor = None
    more = True
    keys = []
    while more:
        feed_keys, cursor, more = feeds.fetch_page(BATCH_SIZE, keys_only=True, start_cursor=cursor)
        keys += feed_keys

    keys = ','.join([x.urlsafe() for x in keys])
    if keys:
        yield Queue('poll').add_async(Task(url=url_for('tq_feed_poll-canonical'), method='POST', params={'keys': keys}))

    raise ndb.Return('ok')

instagram_push_update.login_required = False


@app.route('/api/feeds/<feed_key>/subscribe', methods=['GET'])
@app.route('/api/backend/feeds/<feed_key>/subscribe', methods=['GET'])
def feed_subscribe(feed_key):
    mode = request.args['hub.mode']
    challenge = request.args['hub.challenge']
    verify_token = request.args.get('hub.verify_token')

    if mode == 'subscribe':
        feed = ndb.Key(urlsafe=feed_key).get()
        # Only check this if they send back a verify token
        if verify_token and verify_token != feed.verify_token:
            logger.info('Failed verification feed.verify_token:%s GET verify_token:%s', feed.verify_token, verify_token)
            return "Failed Verification", 400

        if not feed:
            return "No feed", 404

        feed.subscribed_at_hub = True
        # If PuSH is enabled lets only poll these feeds every 15 minutes
        feed.update_interval = UPDATE_INTERVAL.MINUTE_15
        feed.put()
        logger.info('Responding to challange: %s', challenge)
        return challenge

feed_subscribe.login_required = False


@app.route('/api/feeds/<feed_key>/subscribe', methods=['POST'])
@app.route('/api/backend/feeds/<feed_key>/subscribe', methods=['POST'])
@ndb.synctasklet
def feed_push_update(feed_key):
    feed = ndb.Key(urlsafe=feed_key).get()
    if not feed:
        raise ndb.Return(("No feed", 404))

    data = request.stream.read()
    logger.info('Got PuSH body: %s', data)
    logger.info('Got PuSH headers: %s', request.headers)

    if feed.hub_secret:
        server_signature = request.headers.get('X-Hub-Signature', None)
        signature = hmac.new(feed.hub_secret, data).hexdigest()

        if server_signature != signature:
            logger.warn('Got PuSH subscribe POST for feed key=%s w/o valid signature: sent=%s != expected=%s', feed_key,
                        server_signature, signature)

            raise ndb.Return('')

    yield feed.clear_error()
    parsed_feed = feedparser.parse(data)
    new_guids, old_guids = yield Entry.process_parsed_feed(parsed_feed, feed, overflow=False)
    yield Entry.publish_for_feed(feed, skip_queue=False)

    raise ndb.Return('')

feed_push_update.login_required = False
