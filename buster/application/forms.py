import logging

from wtforms.form import Form
from wtforms import fields
from wtforms import validators
from wtforms.validators import ValidationError

from .models import PERIOD_SCHEDULE, fetch_feed_url, FORMAT_MODE

logger = logging.getLogger(__name__)


def boolean_filter(value):
    return value is True or value == 'true'


class FeedUpdate(Form):
    include_summary = fields.BooleanField(default=False, filters=[boolean_filter])
    linked_list_mode = fields.BooleanField(default=False, filters=[boolean_filter])
    include_thumb = fields.BooleanField(default=False, filters=[boolean_filter])
    max_stories_per_period = fields.IntegerField(default=1, validators=[validators.NumberRange(1, 5)])
    schedule_period = fields.IntegerField(default=PERIOD_SCHEDULE.MINUTE_5, validators=[validators.AnyOf(PERIOD_SCHEDULE)])
    format_mode = fields.IntegerField(default=FORMAT_MODE.LINKED_TITLE, validators=[validators.AnyOf(FORMAT_MODE)])


class FeedPreview(FeedUpdate):
    feed_url = fields.TextField(validators=[validators.DataRequired(), validators.URL()])


class FeedCreate(FeedUpdate):
    feed_url = fields.TextField(validators=[validators.DataRequired(), validators.URL()])
