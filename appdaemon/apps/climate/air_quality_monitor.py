from typing import Dict

from base_automation import BaseAutomation
from lib.climate.air_quality_level import AirQualityLevel
from lib.core.component import Component
from lib.core.monitored_callback import monitored_callback
from lib.helper import is_float


class MonitorSettings:
    def __init__(self, config):
        self._air_quality_entity_id = config['air_quality_entity_id']
        self._climate_comfort_level_entity_id = config.get('climate_comfort_level_entity_id')
        self._fan_entity_id = config.get('fan_entity_id')
        self._front_airflow_entity_id = config.get('front_airflow_entity_id')
        self._name = config['name']
        self._thresholds = config['thresholds']
        self._allowed_periods = config.get('allowed_periods', [])

    @property
    def air_quality_entity_id(self):
        return self._air_quality_entity_id

    @property
    def climate_comfort_level_entity_id(self):
        return self._climate_comfort_level_entity_id

    @property
    def fan_entity_id(self):
        return self._fan_entity_id

    @property
    def front_airflow_entity_id(self):
        return self._front_airflow_entity_id

    @property
    def name(self):
        return self._name

    @property
    def thresholds(self):
        return self._thresholds

    @property
    def allowed_periods(self):
        return self._allowed_periods


class FanSnapshot:
    def __init__(self, fan_entity, direction):
        self._fan_entity = fan_entity
        self._direction = direction

    @property
    def entity_id(self):
        return self._fan_entity['entity_id']

    @property
    def state(self):
        return self._fan_entity['state']

    @property
    def oscillating(self):
        return self._fan_entity.get('attributes', {}).get('oscillating', False)

    @property
    def speed(self):
        return self._fan_entity.get('attributes', {}).get('percentage')

    @property
    def direction(self):
        return self._direction


def create_monitor(app: BaseAutomation, setting: MonitorSettings):
    if setting.fan_entity_id:
        return FanMonitor(app, setting)

    return Monitor(app, setting)


class Monitor(Component):
    _setting: MonitorSettings

    def __init__(self, app, setting: MonitorSettings):
        super().__init__(app, {})

        self._setting = setting

    @property
    def name(self):
        return self._setting.name

    @property
    def air_quality_entity_id(self):
        return self._setting.air_quality_entity_id

    @property
    def is_in_monitoring_period(self):
        allowed_periods = self._setting.allowed_periods

        if not allowed_periods:
            return True

        for period in allowed_periods:
            start, end = period.split('-')
            if self.app.now_is_between(start, end):
                return True

        return False

    @property
    def current_air_quality_level(self):
        threshold_setting = self._find_matching_threshold_setting()
        if threshold_setting is None:
            return AirQualityLevel.GOOD

        return AirQualityLevel(threshold_setting['level'])

    def _find_matching_threshold_setting(self):
        air_quality = self.float_state(self._setting.air_quality_entity_id)

        for threshold_setting in reversed(self._setting.thresholds):
            if air_quality > threshold_setting['threshold']:
                return threshold_setting

        return None

    def handle_air_quality_level_change(self, current_level):
        pass


class FanMonitor(Monitor):
    _snapshot: FanSnapshot

    def __init__(self, app, setting: MonitorSettings):
        super().__init__(app, {})

        self._setting = setting
        self._snapshot = None

    @property
    def fan_entity_id(self):
        return self._setting.fan_entity_id

    @property
    def is_fan_running(self):
        return self.get_state(self.fan_entity_id) == 'on'

    @property
    def threshold_speed(self):
        threshold_setting = self._find_matching_threshold_setting()
        if threshold_setting is None:
            return 0

        return threshold_setting['fan_speed']

    def turn_on(self, speed, oscillating=True, direction=None):
        self.log('Turning on {} with speed={}, oscillating={}, direction={}'.format(self.fan_entity_id, speed,
                                                                                    oscillating, direction))

        # self.call_service('fan/turn_on', **{
        #     'entity_id': self.fan_entity_id,
        #     'percentage': speed,
        # })
        #
        # front_airflow_entity_id = self._setting.front_airflow_entity_id
        # if front_airflow_entity_id:
        #     self._update_direction(direction)
        #
        # self._update_oscillating(oscillating)

    def turn_off(self):
        self.log('Turning off {}'.format(self.fan_entity_id))

        # self.call_service('fan/turn_off', **{
        #     'entity_id': self.fan_entity_id,
        # })

    def _update_direction(self, direction):
        if direction is None:
            return

        front_airflow_entity_id = self._setting.front_airflow_entity_id
        current_front_airflow = self.get_state(self._setting.front_airflow_entity_id) == 'on'
        front_airflow = direction == 'forward'
        if current_front_airflow != front_airflow:
            if front_airflow:
                self.app.turn_on(front_airflow_entity_id)
            else:
                self.app.turn_off(front_airflow_entity_id)

    def _update_oscillating(self, oscillating):
        current_oscillating = self.get_state(self.fan_entity_id, attribute='oscillating')
        if current_oscillating != oscillating:
            self.app.sleep(2)
            self.call_service('fan/oscillate', **{
                'entity_id': self.fan_entity_id,
                'oscillating': oscillating,
            })

    def has_snapshot(self):
        return self._snapshot is not None

    def capture_snapshot(self):
        if self.has_snapshot():
            return

        if self.get_state(self._setting.front_airflow_entity_id) == 'on':
            direction = 'forward'
        else:
            direction = 'reverse'

        self._snapshot = FanSnapshot(self.get_state(self.fan_entity_id, attribute='all'), direction)

    def restore_snapshot(self):
        if not self.has_snapshot():
            return

        if self._snapshot.state == 'on':
            self.turn_on(
                self._snapshot.speed,
                self._snapshot.oscillating,
                self._snapshot.direction,
            )
        else:
            self.turn_off()

        self._snapshot = None

    def handle_air_quality_level_change(self, current_level):
        if current_level is AirQualityLevel.GOOD:
            self._handle_good_air_quality()
        else:
            self._handle_bad_air_quality()

    def _handle_good_air_quality(self):
        self.restore_snapshot()

    def _handle_bad_air_quality(self):
        if not self.is_in_monitoring_period:
            return

        if self.is_fan_running and not self.has_snapshot():
            return

        if not self.has_snapshot():
            self.capture_snapshot()

        self.turn_on(self.threshold_speed, oscillating=False, direction=None)


class AirQualityMonitor(BaseAutomation):
    _bad_air_quality_mode_entity_id: str
    _air_quality_level_entity_id: str
    _automation_user_id: str
    _monitors: Dict[Monitor, AirQualityLevel]

    def initialize(self):
        self._bad_air_quality_mode_entity_id = self.cfg.value('bad_air_quality_mode_entity_id')
        self._air_quality_level_entity_id = self.cfg.value('air_quality_level_entity_id')
        self._automation_user_id = self.cfg.value('automation_user_id')
        self._monitors = {}

        for setting in [MonitorSettings(c) for c in self.cfg.list('monitors')]:
            self.listen_state(self._air_quality_change_handler, setting.air_quality_entity_id, immediate=True)
            self._monitors[create_monitor(self, setting)] = AirQualityLevel.GOOD

        self.listen_event(self._fan_state_changed_handler, 'state_changed')

    def _fan_state_changed_handler(self, event_name, data, kwargs):
        entity_id = data.get('entity_id')
        if not entity_id.startswith('fan.'):
            return

        changed_by = data.get('context', {}).get('user_id')
        if changed_by == self._automation_user_id:
            self.log('Ignoring fan changes made by automation, data={}'.format(data))
            return

        fan: FanMonitor = [fan for fan in self._monitors.keys() if
                           isinstance(fan, FanMonitor) and fan.fan_entity_id == entity_id]
        if fan is None:
            self.error('Fan is not monitored, entity_id={}'.format(entity_id))

        # if fan has snapshot and non-appdaemon user changed fan setting, then capture a snapshot again so when we
        # restore it'll keep the same setting
        if fan.has_snapshot():
            self.log('Fan changes detected, capturing snapshot, data={}'.format(data))
            fan.capture_snapshot()

    @monitored_callback
    def _air_quality_change_handler(self, entity, attribute, old, new, kwargs):
        if new == old:
            self.debug('Ignoring air quality unchanged {} vs {}'.format(old, new))
            return

        if not is_float(new):
            self.debug('Ignoring air quality is not number'.format(new))
            return

        fan, previous_level = next(item for item in self._monitors.items() if item[0].air_quality_entity_id == entity)
        current_level = fan.current_air_quality_level
        if current_level == previous_level:
            self.debug('Ignoring air quality unchanged {} => {}'.format(previous_level, current_level))
            return

        self.debug('Air quality changed {}, {} => {}'.format(fan.air_quality_entity_id, previous_level, current_level))
        self._monitors[fan] = current_level

        self.figure_overall_air_quality_level()
        if self.get_bad_air_quality_monitors():
            self.turn_on(self._bad_air_quality_mode_entity_id)
        else:
            self.turn_off(self._bad_air_quality_mode_entity_id)

        fan.handle_air_quality_level_change(current_level)

    def figure_overall_air_quality_level(self):
        bad_air_quality_monitors = self.get_bad_air_quality_monitors()
        if not bad_air_quality_monitors:
            self.select_option(self._air_quality_level_entity_id, AirQualityLevel.GOOD.value)

        bad_air_quality_levels = set(bad_air_quality_monitors.values())
        if AirQualityLevel.VERY_BAD in bad_air_quality_levels:
            self.select_option(self._air_quality_level_entity_id, AirQualityLevel.VERY_BAD.value)
        elif AirQualityLevel.BAD in bad_air_quality_levels:
            self.select_option(self._air_quality_level_entity_id, AirQualityLevel.BAD.value)
        elif AirQualityLevel.MODERATE in bad_air_quality_levels:
            self.select_option(self._air_quality_level_entity_id, AirQualityLevel.MODERATE.value)

    def get_bad_air_quality_monitors(self) -> Dict[Monitor, AirQualityLevel]:
        return {monitor: level for (monitor, level) in self._monitors.items() if level != AirQualityLevel.GOOD}
