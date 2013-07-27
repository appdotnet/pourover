

class DjangoEnum(object):
    def __init__(self, *string_list):
        self.__dict__.update([(string, number) for (number, string, friendly)
                              in string_list])
        self.int_to_display = {number: friendly for (number, string, friendly) in string_list}

    def get_choices(self):
        return tuple(enumerate(self.__dict__.keys()))

    def __iter__(self):
        return self.__dict__.values().__iter__()

    def next(self):
        return self.__dict__.values().next()

    def for_display(self, index):
        return self.int_to_display[index]


ENTRY_STATE = DjangoEnum(
    (1, 'ACTIVE', 'Active'),
    (10, 'INACTIVE', 'Inactive'),
)


FEED_STATE = DjangoEnum(
    (1, 'ACTIVE', 'Active'),
    (2, 'NEEDS_REAUTH', 'Needs reauth'),
    (10, 'INACTIVE', 'Inactive'),
)

FORMAT_MODE = DjangoEnum(
    (1, 'LINKED_TITLE', 'Linked Title'),
    (2, 'TITLE_THEN_LINK', 'Title then Link'),
)

UPDATE_INTERVAL = DjangoEnum(
    (5, 'MINUTE_1', '1 min'),
    (1, 'MINUTE_5', '5 mins'),
    (2, 'MINUTE_15', '15 mins'),
    (3, 'MINUTE_30', '30 mins'),
    (4, 'MINUTE_60', '60 mins'),
)


PERIOD_SCHEDULE = DjangoEnum(
    (1, 'MINUTE_1', '1 min'),
    (5, 'MINUTE_5', '5 mins'),
    (15, 'MINUTE_15', '15 mins'),
    (30, 'MINUTE_30', '30 mins'),
    (60, 'MINUTE_60', '60 mins'),
)


OVERFLOW_REASON = DjangoEnum(
    (1, 'BACKLOG', 'Added from feed backlog'),
    (2, 'FEED_OVERFLOW', 'Feed backed up'),
)


VALID_STATUS = (200, 304)
