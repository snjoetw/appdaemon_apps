import concurrent
import time
import traceback

import appdaemon.plugins.hass.hassapi as hass
import appdaemon.utils as utils

from lib.core.config import Config
from lib.helper import to_float

LOG_LEVELS = {
    'DEBUG': 10,
    'INFO': 20,
    'WARNING': 30,
    'ERROR': 40,
}


class BaseAutomation(hass.Hass):

    @property
    def cfg(self):
        return Config(self, self.args)

    @property
    def debug_enabled(self):
        return self.cfg.value('debug', False)

    @property
    def log_level(self):
        log_level = self.cfg.value('log_level')
        if log_level:
            return log_level

        return 'INFO'

    @property
    def is_sleeping_time(self):
        sleeping_time_entity_id = self.cfg.value('sleeping_time_entity_id', 'binary_sensor.sleeping_time')
        return self.get_state(sleeping_time_entity_id) == 'on'

    @property
    def is_midnight_time(self):
        midnight_time_entity_id = self.cfg.value('midnight_time_entity_id', 'binary_sensor.midnight_time')
        return self.get_state(midnight_time_entity_id) == 'on'

    def log(self, msg, level='INFO'):
        if LOG_LEVELS[level] < LOG_LEVELS[self.log_level]:
            return

        if level == 'DEBUG':
            msg = 'DEBUG - {}'.format(msg)
            level = 'INFO'

        super().log(msg, level=level)

    def debug(self, msg):
        return self.log(msg, level='DEBUG')

    def warn(self, msg):
        return self.log(msg, level='WARNING')

    def error(self, msg):
        return self.log(msg, level='ERROR')

    def sleep(self, duration):
        self.debug('About to sleep for {} sec'.format(duration))
        time.sleep(duration)

    def float_state(self, entity_id):
        return to_float(self.get_state(entity_id))

    @utils.sync_wrapper
    async def sun_up(self):
        sun_entity_id = self.cfg.value('sun_entity_id', 'sun.sun')
        return self.get_state(sun_entity_id) == 'above_horizon'

    @utils.sync_wrapper
    async def sun_down(self):
        sun_entity_id = self.cfg.value('sun_entity_id', 'sun.sun')
        return self.get_state(sun_entity_id) == 'below_horizon'

    @utils.sync_wrapper
    async def get_state(self, entity=None, **kwargs):
        if entity is None and not 'namespace' in kwargs:
            self.debug('About to retrieve state with entity=None\n{}'.format(''.join(traceback.format_stack())))

        state = await super().get_state(entity, **kwargs)

        if entity is not None and not 'namespace' in kwargs:
            self.debug('Retrieved state, entity_id={} state={}'.format(entity, state))

        return state

    def set_state(self, entity_id, **kwargs):
        self.log('Updated {} state: kwargs{}'.format(entity_id, kwargs))
        super().set_state(entity_id, **kwargs)

    @utils.sync_wrapper
    async def call_service(self, service, **kwargs):
        self.log('Calling {} with {}'.format(service, kwargs))
        return await super().call_service(service, **kwargs)

    def select_option(self, entity_id, option, **kwargs):
        if self.get_state(entity_id) == option:
            self.debug('{} already in {}, skipping ...'.format(entity_id, option))
            return

        options = self.get_state(entity_id, attribute='options')
        if option not in options:
            self.error('{} is not a valid option in {} ({})'.format(option, entity_id, options))
            return

        self.log('Selecting {} in {}'.format(option, entity_id))
        super().select_option(entity_id, option, **kwargs)

    def cancel_timer(self, handle):
        try:
            super().cancel_timer(handle)
        except:
            self.error('Error when cancel job: ' + traceback.format_exc())

    def do_actions(self, actions, trigger_info=None, do_parallel_actions=True):
        if len(actions) == 0:
            return

        if len(actions) == 1 or not do_parallel_actions:
            self.debug('About to do action(s) in sequential order')
            for action in actions:
                do_action(action, trigger_info)
            return

        self.debug('About to do action(s) in parallel')
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(do_action, action, trigger_info): action for action in actions}
            for future in concurrent.futures.as_completed(futures):
                future.result()

            self.debug('All action(s) are performed')


def do_action(action, trigger_info):
    if not action.check_action_constraints(trigger_info):
        return

    action.debug('About to do action: {}'.format(action))
    try:
        action.cfg.trigger_info = trigger_info
        return action.do_action(trigger_info)
    except Exception as e:
        action.error('Error when running actions in parallel: {}, action={}, trigger_info={}\n{}'.format(
            e,
            action,
            trigger_info,
            traceback.format_exc()))

    action.cfg.trigger_info = None
