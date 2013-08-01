import logging

from wtforms.form import Form
from wtforms import fields
from wtforms import validators
from wtforms.validators import ValidationError
from urlparse import urlparse

from constants import PERIOD_SCHEDULE, FORMAT_MODE

logger = logging.getLogger(__name__)


def boolean_filter(value):
    return value is True or value == 'true'


def adn_rss_feed_check(form, field):
    urlparts = urlparse(field.data)
    if urlparts.netloc.endswith('alpha-api.app.net'):
        raise ValidationError('App.net RSS feeds are disallowed')


class FeedUpdate(Form):
    include_summary = fields.BooleanField(default=False, filters=[boolean_filter])
    linked_list_mode = fields.BooleanField(default=False, filters=[boolean_filter])
    include_thumb = fields.BooleanField(default=True, filters=[boolean_filter])
    include_video = fields.BooleanField(default=True, filters=[boolean_filter])
    max_stories_per_period = fields.IntegerField(default=1, validators=[validators.NumberRange(1, 5)])
    schedule_period = fields.IntegerField(default=PERIOD_SCHEDULE.MINUTE_5, validators=[validators.AnyOf(PERIOD_SCHEDULE)])
    format_mode = fields.IntegerField(default=FORMAT_MODE.LINKED_TITLE, validators=[validators.AnyOf(FORMAT_MODE)])
    bitly_login = fields.TextField(validators=[validators.Length(min=-1, max=40)])
    bitly_api_key = fields.TextField(validators=[validators.Length(min=-1, max=40)])


class FeedPreview(FeedUpdate):
    feed_url = fields.TextField(validators=[validators.DataRequired(), validators.URL(), adn_rss_feed_check])


class FeedCreate(FeedUpdate):
    feed_url = fields.TextField(validators=[validators.DataRequired(), validators.URL(), adn_rss_feed_check])
