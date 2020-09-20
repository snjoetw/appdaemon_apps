import calendar
import operator
from datetime import datetime, date

from lib.component import Component
from lib.helper import to_float
from lib.schedule_job import has_scheduled_job


def get_constraint(app, config):
    platform = config['platform'];
    if platform == 'state':
        return StateConstraint(app, config)
    elif platform == 'triggered_state':
        return TriggeredStateConstraint(app, config)
    elif platform == 'triggered_event':
        return TriggeredEventConstraint(app, config)
    elif platform == 'attribute':
        return AttributeConstraint(app, config)
    elif platform == 'darkness_level':
        return DarknessStateConstraint(app, config)
    elif platform == 'time':
        return TimeConstraint(app, config)
    elif platform == 'has_scheduled_job':
        return HasScheduledJobConstraint(app, config)
    elif platform == 'day_of_week':
        return DayOfWeekConstraint(app, config)
    else:
        raise ValueError("Invalid constraint config: " + config)


class Constraint(Component):
    def __init__(self, app, constraint_config):
        super().__init__(app, constraint_config)

    def check(self, trigger_info):
        raise NotImplementedError()


class StateConstraint(Constraint):
    def __init__(self, app, constraint_config):
        super().__init__(app, constraint_config)

    def check(self, trigger_info):
        entity_ids = self.list_config('entity_id')
        state = self._config['state']
        negate = self._config.get('negate', False)
        match_all = self._config.get('match_all', False)
        return self._check_entity_state(entity_ids, state, negate, match_all)

    def _check_entity_state(self, entity_ids, target_state, negate, match_all):
        for entity_id in entity_ids:
            current_state = self.get_state(entity_id)
            condition = matches_value(target_state, current_state)

            if negate is True:
                condition = not condition

            if match_all and not condition:
                return False

            if not match_all and condition:
                self.debug('state constraint matched, entity_id={} '
                           'target_state={} '
                           'negate={}'.format(entity_id, target_state, negate))
                return condition

        if match_all:
            return True

        self.debug('no state constraint matched, entity_ids={} '
                   'target_state={} '
                   'negate={}'.format(entity_ids, target_state, negate))

        return False


class TriggeredStateConstraint(Constraint):
    def __init__(self, app, constraint_config):
        super().__init__(app, constraint_config)

    def check(self, trigger_info):
        if trigger_info.platform != "state":
            return False

        triggered = trigger_info.data

        entity_id = self.list_config('entity_id', [])
        if entity_id and not matches_value(entity_id, triggered.get('entity_id')):
            return False

        attribute = self.list_config('attribute', [])
        if attribute and not matches_value(attribute, triggered.get('attribute')):
            return False

        from_state = self.list_config('from', [])
        if from_state and not matches_value(from_state, triggered.get('from')):
            return False

        to_state = self.list_config('to', [])
        if to_state and not matches_value(to_state, triggered.get('to')):
            return False

        return True


class TriggeredEventConstraint(Constraint):
    def __init__(self, app, constraint_config):
        super().__init__(app, constraint_config)

    def check(self, trigger_info):
        if trigger_info.platform != "event":
            return False

        event = trigger_info.data

        entity_id = self.list_config('entity_id', [])
        if entity_id and event.get('entity_id') not in entity_id:
            return False

        event_name = self.list_config('event_name', [])
        if event_name and event.get('event_name') not in event_name:
            return False

        click_type = self.list_config('click_type', [])
        if click_type and event.get('data', {}).get(
                'click_type') not in click_type:
            return False

        if not self.check_attribute(event, 'device_ieee'):
            return False

        if not self.check_attribute(event, 'cluster_id'):
            return False

        if not self.check_attribute(event, 'endpoint_id'):
            return False

        if not self.check_attribute(event, 'command'):
            return False

        if not self.check_attribute(event, 'args'):
            return False

        return True

    def check_attribute(self, event, attribute_name):
        self.debug('attribute_name: {}'.format(attribute_name))
        attribute_constrains = [str(a) for a in
                                self.list_config(attribute_name, [])]
        self.debug('attribute_constrains: {}'.format(attribute_constrains))
        if not attribute_constrains:
            return True

        attribute_value = str(event.get('data', {}).get(attribute_name))
        self.debug('attribute_value: {}'.format(attribute_value))
        if not attribute_value:
            return True

        self.debug('eval: {}'.format(attribute_value in attribute_constrains))
        return attribute_value in attribute_constrains


class AttributeConstraint(Constraint):
    def __init__(self, app, constraint_config):
        super().__init__(app, constraint_config)

    def check(self, trigger_info):
        entity_id = self._config['entity_id']
        attribute = self._config['attribute']
        value = self._config['value']
        negate = self._config.get('negate', False)
        current_value = self.get_state(entity_id, attribute=attribute)
        condition = matches_value(value, current_value)

        if negate is True:
            return not condition

        return condition


def get_operator_fn(op):
    return {
        '<': operator.lt,
        '<=': operator.le,
        '>': operator.gt,
        '>=': operator.ge,
    }[op]


def matches_value(expected, actual):
    if isinstance(expected, list):
        return actual in expected

    if not isinstance(expected, str):
        return expected == actual

    if not expected.startswith('<') and not expected.startswith('>'):
        return expected == actual

    if expected.startswith('<='):
        return matches_numeric_value('<=', expected, actual)
    elif expected.startswith('<'):
        return matches_numeric_value('<', expected, actual)
    elif expected.startswith('>='):
        return matches_numeric_value('>=', expected, actual)
    elif expected.startswith('>'):
        return matches_numeric_value('>', expected, actual)

    return expected == actual


def matches_numeric_value(op, expected, actual):
    expected = expected.replace(op, '')
    expected = to_float(expected)
    actual = to_float(actual)
    operator_fn = get_operator_fn(op)
    return operator_fn(actual, expected)


class DarknessStateConstraint(Constraint):
    def __init__(self, app, constraint_config):
        super().__init__(app, constraint_config)

    def check(self, trigger_info):
        darkness_entity_id = self._config['darkness_entity_id']
        darkness_entity = self.get_state(darkness_entity_id, attribute='all')
        darkness_changed_at = darkness_entity['last_changed']

        for skip_entity_id in self._config.get('skip_entity_ids', []):
            skip_entity = self.get_state(skip_entity_id, attribute='all')

            # if skip_entity is on, then skip
            if skip_entity['state'] == 'on':
                return False
            # if darkness_entity was updated before skip_entity, then skip
            elif darkness_changed_at < skip_entity['last_changed']:
                return False

        min_darkness_level = to_float(self._config['min_darkness_level'])
        current_darkness_level = to_float(darkness_entity['state'])

        return current_darkness_level >= min_darkness_level


class TimeConstraint(Constraint):
    def __init__(self, app, constraint_config):
        super().__init__(app, constraint_config)

    def check(self, trigger_info):
        start_time = self._config.get('start_time')
        end_time = self._config.get('end_time')

        if start_time and end_time:
            return self._app.now_is_between(start_time, end_time)

        start_time = self.get_state(self._config.get('start_time_entity_id'))
        end_time = self.get_state(self._config.get('end_time_entity_id'))

        if start_time and end_time:
            start_time = datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S')
            end_time = datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S')
            return start_time <= datetime.now() < end_time


class HasScheduledJobConstraint(Constraint):
    def __init__(self, app, constraint_config):
        super().__init__(app, constraint_config)

    def check(self, trigger_info):
        has_job = has_scheduled_job(self._app)
        negate = self._config.get('negate', False)

        if negate:
            return not has_job

        return has_job


class DayOfWeekConstraint(Constraint):
    def __init__(self, app, constraint_config):
        super().__init__(app, constraint_config)

    def check(self, trigger_info):
        days = self.list_config('day', [])
        today = date.today()
        day = calendar.day_name[today.weekday()]
        return day in days
