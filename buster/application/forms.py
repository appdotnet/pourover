import logging

from wtforms.form import Form
from wtforms import fields
from wtforms import validators

from .models import PERIOD_SCHEDULE

logger = logging.getLogger(__name__)


def boolean_filter(value):
    logger.info('Boolean filter: %s', value)
    return value is True or value == 'true'


class FeedCreate(Form):
    feed_url = fields.TextField(validators=[validators.URL()])
    include_summary = fields.BooleanField(default=False, filters=[boolean_filter])
    max_stories_per_period = fields.IntegerField(default=1, validators=[validators.NumberRange(1, 5)])
    schedule_period = fields.IntegerField(default=PERIOD_SCHEDULE.MINUTE_5, validators=[validators.AnyOf(PERIOD_SCHEDULE)])

