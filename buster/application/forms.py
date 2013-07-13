import logging

from wtforms.form import Form
from wtforms import fields
from wtforms import validators
from wtforms.validators import ValidationError

from .models import PERIOD_SCHEDULE, fetch_feed_url, VALID_STATUS

logger = logging.getLogger(__name__)


def boolean_filter(value):
    return value is True or value == 'true'


def valid_feed(form, field):
    parsed_feed = fetch_feed_url(field.data)
    if getattr(parsed_feed, 'status', None) not in VALID_STATUS:
        logger.info('Failed good status %s', getattr(parsed_feed, 'status', None))
        raise ValidationError(message='Failed to fetch feed')

    if not parsed_feed.feed.get('title'):
        logger.info('Failed to find a feed title')
        raise ValidationError(message='Invalid RSS feed')


class FeedCreate(Form):
    feed_url = fields.TextField(validators=[validators.DataRequired(), validators.URL(), valid_feed])
    include_summary = fields.BooleanField(default=False, filters=[boolean_filter])
    max_stories_per_period = fields.IntegerField(default=1, validators=[validators.NumberRange(1, 5)])
    schedule_period = fields.IntegerField(default=PERIOD_SCHEDULE.MINUTE_5, validators=[validators.AnyOf(PERIOD_SCHEDULE)])
