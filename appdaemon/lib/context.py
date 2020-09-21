from enum import Enum


class PartsOfDay(Enum):
    MORNING = 1
    AFTERNOON = 2
    EVENING = 3
    NIGHT = 4


class Context:
    def __init__(self, parts_of_day, presence_mode=None, trigger_time=None):
        self._parts_of_day = parts_of_day
        self._presence_mode = presence_mode
        self._trigger_time = trigger_time

    @property
    def parts_of_day(self):
        return self._parts_of_day

    @property
    def presence_mode(self):
        # - No One is Home
        # - Someone is Home
        # - Everyone is Home
        # - Disabled
        return self._presence_mode

    @property
    def trigger_time(self):
        return self._trigger_time
