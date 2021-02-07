from typing import List

import appdaemon.plugins.mqtt.mqttapi as mqtt

from base_automation import BaseAutomation
from lib.component import Component

BASE_TOPIC = 'app/notification/'


class Handler(Component):
    def __init__(self, app, app_topic):
        super().__init__(app, {})
        self._topic = '{}{}'.format(BASE_TOPIC, app_topic)

    @property
    def topic(self):
        return self._topic

    def handle(self, data):
        title, text = data.split('\n')
        self.log('Handling title={}, text={} with handler={}'.format(title, text, self))
        self._do_handle(title, text)

    def _do_handle(self, title, text):
        pass


class MobileAppNotificationHandler(mqtt.Mqtt, BaseAutomation):
    _handlers: List[Handler]

    def initialize(self):
        self._handlers = [
            TelusAlarmHandler(self),
            NestHandler(self),
            UberEatsHandler(self)]

        for handler in self._handlers:
            mqtt_app = super(mqtt.Mqtt, self)
            mqtt_app.listen_event(self._notification_handler, 'MQTT_MESSAGE', namespace='mqtt', topic=handler.topic)

    def _notification_handler(self, event_name, data, kwargs):
        for handler in self._handlers:
            if handler.topic == data['topic']:
                return handler.handle(data['payload'])

        self.log('No handler defined for data={}'.format(data))


class TelusAlarmHandler(Handler):
    def __init__(self, app):
        super().__init__(app, 'SmartHome')

    def _do_handle(self, title, text):
        telus_alarm_state = self._figure_alarm_state(title)
        if telus_alarm_state is None:
            self.error('No alarm state defined for title={}, text={}'.format(title, text))
            return

        current_alarm = self.get_state('alarm_control_panel.home_alarm', attribute='all')
        current_alarm_state = current_alarm['state']
        if current_alarm_state == telus_alarm_state:
            self.log('Alarm state is already {}, skipping title={}, text={}'.format(current_alarm_state, title, text))
            return

        alarm_attributes = current_alarm.get('attributes', {})
        alarm_attributes['changed_by'] = 'Telus SmartHome'

        # setting state before calling service to alarm_state_change_events to filter by changed_by attribute
        self.set_state('alarm_control_panel.home_alarm', state=telus_alarm_state, attributes=alarm_attributes)
        self.call_service(self._figure_service_name(title), entity_id='alarm_control_panel.home_alarm')

    @staticmethod
    def _figure_alarm_state(title):
        if 'Panel Disarmed' in title:
            return 'disarmed'
        elif 'Panel Armed Stay' in title:
            return 'armed_home'
        elif 'Panel Armed Away' in title:
            return 'armed_away'
        return None

    @staticmethod
    def _figure_service_name(title):
        if 'Panel Disarmed' in title:
            return 'alarm_control_panel/alarm_disarm'
        elif 'Panel Armed Stay' in title:
            return 'alarm_control_panel/alarm_arm_home'
        elif 'Panel Armed Away' in title:
            return 'alarm_control_panel/alarm_arm_away'
        return None


class NestHandler(Handler):
    def __init__(self, app):
        super().__init__(app, 'Nest')

    def _do_handle(self, title, text):
        if title == 'Package left • Front Door':
            self.app.turn_on('input_boolean.nest_front_door_package_delivered')
        elif title == 'Person • Front Yard':
            self.log('Handling title={}'.format(title))
        elif title == 'Motion • Rear Driveway':
            self.log('Handling title={}'.format(title))


class UberEatsHandler(Handler):
    def __init__(self, app):
        super().__init__(app, 'Uber Eats')

    def _do_handle(self, title, text):
        self.info('Uber Eats handler title={}, text={}'.format(title, text))
