import concurrent
import time
import traceback

import appdaemon.utils as utils
import hassapi as hass
from lib.helper import to_float, to_int


class BaseAutomation(hass.Hass):

    @property
    def debug_enabled(self):
        return self.args.get('debug', False)

    def log(self, msg, level='INFO'):
        if level == 'DEBUG' and not self.debug_enabled:
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

    def arg(self, key, default=None):
        value = self.args.get(key, default)

        if str(value).startswith("state:"):
            value = self.get_state(value.split(':')[1])

        return value

    def int_arg(self, key, default=None):
        return to_int(self.float_arg(key, default))

    def float_arg(self, key, default=None):
        value = self.arg(key, default)
        return to_float(value, default)

    def list_arg(self, key, default=None):
        value = self.args.get(key, default)

        if isinstance(value, list):
            return self._flatten_list_arg(value)

        return [value]

    def _flatten_list_arg(self, arg_value):
        values = []
        for value in arg_value:
            if isinstance(value, list):
                values.extend(self._flatten_list_arg(value))
            else:
                values.append(value)

        return values

    def sleep(self, duration):
        self.debug('About to sleep for {} sec'.format(duration))
        time.sleep(duration)

    @utils.sync_wrapper
    async def get_state(self, entity=None, **kwargs):
        if entity is None and not 'namespace' in kwargs:
            self.debug('About to retrieve state with entity=None\n{}'.format(
                ''.join(traceback.format_stack())
            ))

        state = await super().get_state(entity, **kwargs)

        if entity is not None and not 'namespace' in kwargs:
            self.debug('Retrieved state, entity_id={} state={}'.format(entity,
                                                                       state))

        return state

    def set_state(self, entity_id, **kwargs):
        self.log('Updated {} state: kwargs{}'.format(entity_id, kwargs))
        super().set_state(entity_id, **kwargs)

    @utils.sync_wrapper
    async def call_service(self, service, **kwargs):
        self.log('Calling {} with {}'.format(service, kwargs))
        return await super().call_service(service, **kwargs)

    def select_option(self, entity_id, option, **kwargs):
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
                action.do_action(trigger_info)
                self.debug('{} is done'.format(action))
            return

        self.debug('About to do action(s) in parallel')
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(do_action, action, trigger_info): action for action in actions}
            for future in concurrent.futures.as_completed(futures):
                future.result()

            self.debug('All action(s) are performed')


def do_action(action, trigger_info):
    action.debug('About to do action: {}'.format(action))
    try:
        return action.do_action(trigger_info)
    except Exception as e:
        action.error('Error when running actions in parallel: {}, action={}, trigger_info={}\n{}'.format(
            e,
            action,
            trigger_info,
            traceback.format_exc()))
