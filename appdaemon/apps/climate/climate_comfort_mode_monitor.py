from base_automation import BaseAutomation
from lib.core.monitored_callback import monitored_callback
from lib.helper import to_float


class ClimateComfortModeMonitor(BaseAutomation):
    def initialize(self):
        self.mode_entity_id = self.cfg.value('mode_entity_id')
        self.comfort_threshold = self.cfg.value('comfort_temp_threshold', 0.7)
        self.climate_entity_id = self.cfg.value('climate_entity_id')

        self.listen_state(self.state_change_handler, self.climate_entity_id)

    @monitored_callback
    def state_change_handler(self, entity, attribute, old, new, kwargs):
        climate_entity = self.get_state(self.climate_entity_id, attribute='all')
        attributes = climate_entity.get('attributes')
        current_temp = to_float(attributes.get('current_temperature'))
        target_temp_high = to_float(attributes.get('target_temp_high'))
        target_temp_low = to_float(attributes.get('target_temp_low'))

        comfort_range = self.get_comfort_range(target_temp_high, target_temp_low)
        warm_range = range_open_closed(comfort_range.end, target_temp_high)
        cool_range = range_closed_open(target_temp_low, comfort_range.start)

        if comfort_range.contains(current_temp):
            self.set_mode_value(self.mode_entity_id, 'Comfort')
        elif warm_range.contains(current_temp):
            self.set_mode_value(self.mode_entity_id, 'Warm')
        elif cool_range.contains(current_temp):
            self.set_mode_value(self.mode_entity_id, 'Cool')
        elif current_temp > warm_range.end:
            self.set_mode_value(self.mode_entity_id, 'Hot')
        elif current_temp < cool_range.end:
            self.set_mode_value(self.mode_entity_id, 'Cold')

    def get_comfort_range(self, target_temp_high, target_temp_low):
        target_mid_temp = self.get_target_mid_temperature(target_temp_high, target_temp_low)
        return range_closed(target_mid_temp - self.comfort_threshold, target_mid_temp + self.comfort_threshold)

    def get_target_mid_temperature(self, target_temp_high, target_temp_low):
        return (target_temp_high - target_temp_low) / 2 + target_temp_low

    def set_mode_value(self, mode_entity_id, new_mode_value):
        current_mode_value = self.get_state(mode_entity_id)

        if current_mode_value != new_mode_value:
            self.log("Setting {} to {}".format(mode_entity_id, new_mode_value))
            self.select_option(mode_entity_id, new_mode_value)


def range_open(start, end):
    return Range(start, end, False, False)


def range_closed(start, end):
    return Range(start, end, True, True)


def range_open_closed(start, end):
    return Range(start, end, False, True)


def range_closed_open(start, end):
    return Range(start, end, True, False)


class Range:
    def __init__(self, start, end, include_start=True, include_end=True):
        self._start = start
        self._end = end
        self._include_start = include_start
        self._include_end = include_end

    @property
    def start(self):
        return self._start

    @property
    def end(self):
        return self._end

    def contains(self, value):
        # open
        # {x | a < x < b}
        if self._include_start is False and self._include_end is False:
            return self._start < value < self._end
        # closed
        # {x | a <= x <= b}
        elif self._include_start is True and self._include_end is True:
            return self._start <= value <= self._end
        # open, closed
        # {x | a < x <= b}
        elif self._include_start is False and self._include_end is True:
            return self._start < value <= self._end
        # closed, open
        # {x | a <= x < b}
        elif self._include_start is True and self._include_end is False:
            return self._start <= value < self._end
