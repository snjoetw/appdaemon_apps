from base_automation import BaseAutomation
from lib.helper import to_float

CHECKER_RESULT_CACHE = {}


class AirQualityMonitor(BaseAutomation):

    def initialize(self):
        self.bad_air_quality_fans = []
        self.monitor_settings = [MonitorSettings(c) for c in self.list_arg('monitors')]
        self.bad_air_quality_mode_entity_id = self.arg('bad_air_quality_mode_entity_id')

        for setting in self.monitor_settings:
            self.listen_state(self.air_quality_change_handler, setting.air_quality_entity_id)

    def air_quality_change_handler(self, entity, attribute, old, new, kwargs):
        if new == old:
            return

        monitor_setting = next(setting for setting in self.monitor_settings if setting.air_quality_entity_id == entity)
        new = to_float(new)
        if new >= monitor_setting.threshold + 5:
            self.handle_bad_air_quality(monitor_setting)
        elif new < monitor_setting.threshold:
            self.handle_good_air_quality(monitor_setting)

    # IF NOT bad air
    #   IF fan running AND WAS NOT running
    #       TURN_OFF FAN
    #   IF fan running AND WAS running
    #       DO NOTHING
    #   IF fan WAS NOT running
    #       DO NOTHING
    def handle_good_air_quality(self, monitor_setting):
        fan_entity_id = monitor_setting.fan_entity_id
        previous_fan_snapshot = self.existing_bad_air_quality_fan(monitor_setting.fan_entity_id)
        current_fan_snapshot = FanSnapshot(self.get_state(fan_entity_id, attribute='all'))

        if not previous_fan_snapshot:
            return

        self.unmark_bad_air_quality_fan(fan_entity_id)

        if current_fan_snapshot.state == 'off':
            self.debug('Air quality is good, {} is not running, do nothing'.format(fan_entity_id))
            return

        if previous_fan_snapshot.state == 'on':
            self.debug('Air quality is good, {} was running, do nothing'.format(fan_entity_id))
            return

        self.debug('Air quality is good, turning {} off'.format(fan_entity_id))
        self.call_service('fan/turn_off', **{'entity_id': fan_entity_id})

    # IF bad air
    #   IF fan running
    #     DO NOTHING
    #   ELSE
    #     TURN_ON FAN && BACKFLOW
    def handle_bad_air_quality(self, monitor_setting):
        fan_entity_id = monitor_setting.fan_entity_id
        fan_snapshot = FanSnapshot(self.get_state(fan_entity_id, attribute='all'))

        self.mark_bad_air_quality_fan(fan_snapshot)

        if fan_snapshot.state == 'on':
            self.debug('Air quality is bad, {} is alrady on, do nothing'.format(fan_entity_id))
            return

        self.debug('Air quality is bad, turning {} on'.format(fan_entity_id))
        self.call_service('fan/turn_on', **{'entity_id': fan_entity_id})

        if fan_snapshot.is_flow_direction_front:
            self.sleep(2)
            self.call_service('dyson/set_flow_direction_front', **{
                'entity_id': fan_entity_id,
                'flow_direction_front': False,
            })

        if not fan_snapshot.is_auto_mode:
            self.sleep(2)
            self.call_service('fan/set_auto_mode', **{
                'entity_id': fan_entity_id,
                'auto_mode': True,
            })

    def mark_bad_air_quality_fan(self, latest_snapshot):
        existing = self.existing_bad_air_quality_fan(latest_snapshot.entity_id)
        if existing:
            return

        self.bad_air_quality_fans.append(latest_snapshot)

        self.debug('Marked {} as bad quality fan'.format(latest_snapshot.entity_id))

        self.turn_on(self.bad_air_quality_mode_entity_id)

    def unmark_bad_air_quality_fan(self, fan_entity_id):
        existing = self.existing_bad_air_quality_fan(fan_entity_id)
        if existing:
            self.bad_air_quality_fans.remove(existing)
            self.debug('Unmarked {} as bad quality fan'.format(fan_entity_id))

        if not self.bad_air_quality_fans:
            self.turn_off(self.bad_air_quality_mode_entity_id)

    def existing_bad_air_quality_fan(self, fan_entity_id):
        try:
            return next(s for s in self.bad_air_quality_fans if s.entity_id == fan_entity_id)
        except StopIteration:
            return None

    def bad_air_quality_names(self):
        names = []
        for fan in self.bad_air_quality_fans:
            setting = next(setting for setting in self.monitor_settings if setting.fan_entity_id == fan.entity_id)
            names.append(setting.name)

        self.debug('bad_air_quality_mode={}, bad_air_quality_names={}'.format(
            self.get_state(self.bad_air_quality_mode_entity_id),
            names))

        return names


class MonitorSettings:
    def __init__(self, config):
        self._air_quality_entity_id = config['air_quality_entity_id']
        self._fan_entity_id = config['fan_entity_id']
        self._threshold = to_float(config['threshold'])
        self._name = config['name']

    @property
    def air_quality_entity_id(self):
        return self._air_quality_entity_id

    @property
    def fan_entity_id(self):
        return self._fan_entity_id

    @property
    def threshold(self):
        return self._threshold

    @property
    def name(self):
        return self._name


class FanSnapshot:
    def __init__(self, fan_entity):
        self._fan_entity = fan_entity

    @property
    def entity_id(self):
        return self._fan_entity['entity_id']

    @property
    def state(self):
        return self._fan_entity['state']

    @property
    def is_auto_mode(self):
        return self._fan_entity.get('attributes', {}).get('auto_mode', False)

    @property
    def is_night_mode(self):
        return self._fan_entity.get('attributes', {}).get('night_mode', False)

    @property
    def is_flow_direction_front(self):
        return self._fan_entity.get('attributes', {}).get('flow_direction_front', False)

    @property
    def is_oscillating(self):
        return self._fan_entity.get('attributes', {}).get('oscillating', False)

    @property
    def speed(self):
        dyson_speed = self._fan_entity.get('attributes', {}).get('dyson_speed')
        if dyson_speed:
            return dyson_speed

        return self._fan_entity.get('attributes', {}).get('speed')
