import time
from threading import Lock

import appdaemon.plugins.mqtt.mqttapi as mqtt
from teslajson import Connection

from base_automation import BaseAutomation
from lib.core.component import Component
from lib.core.monitored_callback import monitored_callback
from lib.helper import to_int


class TeslaProxy(mqtt.Mqtt, BaseAutomation):

    def initialize(self):
        c = Connection(self.cfg.value('tesla_username'), self.cfg.value('tesla_password'))
        self.orca = c.vehicles[0]
        response = self.orca.get('')
        self.log(response)
        self._lock = Lock()
        self._queue = []
        self._motion_entity_id = self.cfg.value('motion_entity_id')

        super(mqtt.Mqtt, self).listen_event(
            self._door_lock_handler,
            'MQTT_MESSAGE',
            namespace='mqtt',
            topic='hass_tesla/268372268/door/set')

        super(mqtt.Mqtt, self).listen_event(
            self._actuate_trunk_handler,
            'MQTT_MESSAGE',
            namespace='mqtt',
            topic='hass_tesla/268372268/trunk/actuate')

        super(mqtt.Mqtt, self).listen_event(
            self._set_charge_limit_handler,
            'MQTT_MESSAGE',
            namespace='mqtt',
            topic='hass_tesla/268372268/charge/limit')

    @monitored_callback
    def _door_lock_handler(self, event_name, data, kwargs):
        self.debug('Received data: {}'.format(data))

        payload = data['payload']

        if payload == 'LOCK':
            self._queue.append(LockCommand(self, self.orca))
        elif payload == 'UNLOCK':
            if super(BaseAutomation, self).get_state(self._motion_entity_id) == 'on':
                self._queue.append(AnnouncementUnlockCommand(self, self.orca, self._motion_entity_id))
            else:
                self._queue.append(UnlockCommand(self, self.orca))

        self._lock_and_process()

    @monitored_callback
    def _actuate_trunk_handler(self, event_name, data, kwargs):
        self.debug('Received data: {}'.format(data))

        payload = data['payload']

        if payload == 'rear':
            self._queue.append(ActuateTrunkCommand(self, self.orca))
        elif payload == 'front':
            self._queue.append(ActuateFrunkCommand(self, self.orca))

        self._lock_and_process()

    @monitored_callback
    def _set_charge_limit_handler(self, event_name, data, kwargs):
        self.debug('Received data: {}'.format(data))

        percent = to_int(data['payload'])

        self.set_charge_limit(percent)

    # public API
    def set_charge_limit(self, percent):
        self._queue.append(SetChargeLimitCommand(self, self.orca, params={
            'percent': to_int(percent)
        }))
        self._lock_and_process()

    def _lock_and_process(self):
        if not self._queue:
            self.log('Nothing in the queue, skipping ...')
            return

        if self._lock.locked():
            self.log('Unable to acquire lock, rescheduling ...')

        self._lock.acquire()
        try:
            last_command = None
            last_result = None
            while self._queue:
                command = self._queue.pop(0)

                if type(last_command) == type(command) and last_result == True:
                    self.log('Skipping duplicate command={}, last_command={}, last_result={}'.format(
                        command,
                        last_command,
                        last_result))
                    continue

                result = command.execute()
                self.debug('Executed command={}, result={}'.format(command, result))

                last_command = command
                last_result = result
        finally:
            self._lock.release()

    def log(self, msg, level='INFO'):
        if level == 'DEBUG' and not self.debug_enabled:
            return

        if level == 'DEBUG':
            msg = 'DEBUG - {}'.format(msg)
            level = 'INFO'

        super().log(msg, level=level)


class Command(Component):
    def __init__(self, app, vehicle, params={}):
        super().__init__(app, {})

        self.vehicle = vehicle
        self.params = params

    def execute(self):
        pass

    def get_vehicle_state(self):
        response = self.get('')

        if not response:
            return 'unknown'

        return response.get('response', {}).get('state', 'unknown')

    def sleep(self, duration):
        self.debug('About to sleep for {} sec'.format(duration))
        time.sleep(duration)

    def command(self, name, data={}):
        self.debug('About to call Tesla command: {} - {}'.format(name, data))
        response = self.vehicle.command(name, data)
        self.debug('Received Tesla command response: {}'.format(response))
        return response

    def get(self, name):
        self.debug('About to call Tesla get: {}'.format(name))
        response = self.vehicle.get(name)
        self.debug('Received Tesla get response: {}'.format(response))
        return response

    def post(self, name, data={}):
        self.debug('About to call Tesla post: {} - {}'.format(name, data))
        response = self.vehicle.post(name, data)
        self.debug('Received Tesla post response: {}'.format(response))
        return response


class WakeupRequiredCommand(Command):
    def __init__(self, app, vehicle, params={}):
        super().__init__(app, vehicle, params=params)

    def execute(self):
        if not self.should_wakeup():
            return self.execute_after_wakeup()

        retry_count = 0
        while True:
            state = self.wakeup()

            if state == 'online':
                self.debug('Vehicle is now awake')
                return self.execute_after_wakeup()

            self.sleep(3)
            retry_count += 1

            if self.is_max_retry_reached(retry_count):
                self.error('Failed, max wakeup retry reached')
                return False

        return False

    def execute_after_wakeup(self):
        return True

    def should_wakeup(self):
        state = self.get_vehicle_state()
        return state == 'asleep' or state == 'unknown'

    def wakeup(self):
        response = self.post('wake_up')
        if not response:
            return 'unknown'

        return response.get('response', {}).get('state', 'unknown')

    @staticmethod
    def is_max_retry_reached(retry_count):
        return retry_count > 8


class LockCommand(WakeupRequiredCommand):
    def __init__(self, app, vehicle, params={}):
        super().__init__(app, vehicle, params=params)

    def execute_after_wakeup(self):
        response = self.command('door_lock')

        if not response:
            return False

        return response.get('response', {}).get('result', False)


class UnlockCommand(WakeupRequiredCommand):
    def __init__(self, app, vehicle, params={}):
        super().__init__(app, vehicle, params=params)

    def execute_after_wakeup(self):
        response = self.command('door_unlock')

        if not response:
            return False

        return response.get('response', {}).get('result', False)


class AnnouncementUnlockCommand(UnlockCommand):
    def __init__(self, app, vehicle, motion_entity_id, params={}):
        super().__init__(app, vehicle, params=params)
        self.wakeup_count = 0
        self.announcer = self.app.get_app('announcer')

        self.motion_entity_id = motion_entity_id

    def execute(self):
        self.wakeup_count = 0
        super().execute()

    def wakeup(self):
        if self.wakeup_count == 0:
            self.announce('Waking up Model X')
        if self.wakeup_count % 2 == 0:
            self.announce('Still trying')

        return super().wakeup()

    def execute_after_wakeup(self):
        result = super().execute_after_wakeup()
        if result:
            self.announce('Model X is unlocked')
        else:
            self.announce('Failed to unlock Model X')

        return result

    def announce(self, message):
        self.announcer.announce(message, motion_entity_id=self.motion_entity_id)


class ActuateTrunkCommand(WakeupRequiredCommand):
    def __init__(self, app, vehicle, params={}):
        super().__init__(app, vehicle, params=params)

    def execute_after_wakeup(self):
        response = self.command('actuate_trunk', {
            'which_trunk': 'rear'
        })

        if not response:
            return False

        return response.get('response', {}).get('result', False)


class ActuateFrunkCommand(WakeupRequiredCommand):
    def __init__(self, app, vehicle, params={}):
        super().__init__(app, vehicle, params=params)

    def execute_after_wakeup(self):
        response = self.command('actuate_trunk', {
            'which_trunk': 'front'
        })

        if not response:
            return False

        return response.get('response', {}).get('result', False)


class SetChargeLimitCommand(WakeupRequiredCommand):
    def __init__(self, app, vehicle, params={}):
        super().__init__(app, vehicle, params=params)

    def execute_after_wakeup(self):
        response = self.command('set_charge_limit', {
            'percent': self.params['percent']
        })

        if not response:
            return False

        return response.get('response', {}).get('result', False)
