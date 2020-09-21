import concurrent
import traceback

from base_automation import BaseAutomation
from lib.actions import get_action
from lib.constraints import get_constraint
from lib.triggers import get_trigger


class ConfigurableAutomation(BaseAutomation):
    def initialize(self):
        self._global_constraints = []
        self._handlers = []

    def init_trigger(self, platform, config):
        config['platform'] = platform
        get_trigger(self, config, self.trigger_handler)

    def init_global_constraint(self, platform, config):
        constraint = self.create_constraint(platform, config)
        self._global_constraints.append(constraint)

    def create_constraint(self, platform, config):
        config['platform'] = platform
        return get_constraint(self, config)

    def create_action(self, platform, config):
        config['platform'] = platform
        return get_action(self, config)

    def init_handler(self, handler):
        self._handlers.append(handler)

    def create_handler(self, constraints, actions, do_parallel_actions=True):
        return Handler(self, constraints, actions,
                       do_parallel_actions=do_parallel_actions)

    def trigger_handler(self, trigger_info):
        self.debug('Triggered with trigger_info={}'.format(trigger_info))

        try:
            for constraint in self._global_constraints:
                if not constraint.check(trigger_info):
                    return

            for handler in self._handlers:
                if handler.check_constraints(trigger_info):
                    handler.do_actions(trigger_info)
                    return
        except Exception as e:
            self.error('Error when handling trigger: ' + traceback.format_exc())


class Handler:
    def __init__(self, app, constraints, actions, do_parallel_actions=True):
        self._app = app
        self._do_parallel_actions = do_parallel_actions
        self._constraints = constraints
        self._actions = actions

    def check_constraints(self, trigger_info):
        self._app.debug('Checking handler={}'.format(self))
        if self._constraints:
            for constraint in self._constraints:
                if not constraint.check(trigger_info):
                    self._app.debug(
                        'Constraint does not match {}'.format(constraint))
                    return False

                trigger_info.matched_constraints.append(constraint)

        self._app.debug('All constraints match')
        return True

    def do_actions(self, trigger_info):
        if len(self._actions) == 0:
            return

        if len(self._actions) == 1 or not self._do_parallel_actions:
            self._app.debug('About to do action(s) in sequential order')
            for action in self._actions:
                if action.check_action_constraints(trigger_info):
                    action.do_action(trigger_info)
                    self._app.debug('{} is done'.format(action))
            return

        self._app.debug('About to do action(s) in parallel')
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(do_action, action, trigger_info): action
                       for action in self._actions}
            for future in concurrent.futures.as_completed(futures):
                future.result()

            self._app.debug('All action(s) are performed')

    def __repr__(self):
        return "{}(constraints={}, actions={}, do_parallel_actions={})".format(
            self.__class__.__name__,
            self._constraints,
            self._actions,
            self._do_parallel_actions)


def do_action(action, trigger_info):
    if not action.check_action_constraints(trigger_info):
        return

    action.debug('About to do action: {}'.format(action))
    try:
        return action.do_action(trigger_info)
    except Exception as e:
        action.error('Error when running actions in parallel: {}, action={}, trigger_info={}\n{}'.format(
            e,
            action,
            trigger_info,
            traceback.format_exc()))
