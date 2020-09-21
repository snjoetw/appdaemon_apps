from configurable_automation import ConfigurableAutomation


class AlarmMonitor(ConfigurableAutomation):

    def initialize(self):
        super().initialize()

        self.init_trigger('state', {
            'entity_id': self.list_arg('motion_entity_id'),
            'to': 'on',
        })

        self.init_trigger('state', {
            'entity_id': self.list_arg('door_entity_id'),
            'to': 'on',
        })

        self.init_trigger('state', {
            'entity_id': self.list_arg('window_entity_id'),
            'to': 'on',
        })

        alarm_triggered_actions = self.create_triggered_actions()

        self.init_handler(self.create_handler(
            self.create_armed_away_constraints(),
            alarm_triggered_actions))

        self.init_handler(self.create_handler(
            self.create_armed_home_constraints(),
            alarm_triggered_actions))

    def create_armed_away_constraints(self):
        return [self.create_constraint('state', {
            'entity_id': self.arg('alarm_entity_id'),
            'state': 'armed_away',
        })]

    def create_armed_home_constraints(self):
        constraints = [self.create_constraint('state', {
            'entity_id': self.arg('alarm_entity_id'),
            'state': 'armed_home',
        })]

        trigger_entity_ids = self.list_arg('door_entity_id') + self.list_arg('window_entity_id')
        constraints.append(self.create_constraint('triggered_state', {
            'entity_id': trigger_entity_ids,
            'to': 'on'
        }))

        return constraints

    def create_triggered_actions(self):
        actions = []

        actions.append(self.create_action('service', {
            'service': 'alarm_control_panel/alarm_trigger',
            'data': {
                'entity_id': self.arg('alarm_entity_id'),
            }
        }))

        actions.append(self.create_action('service', {
            'service': 'input_text/set_value',
            'data': {
                'entity_id': self.arg('alarm_triggered_entity_id'),
                'value': '{{ trigger_info.data.entity_id }}',
            }
        }))

        actions.append(self.create_action('alarm_notifier', {
            'trigger_entity_id': '{{ trigger_info.data.entity_id }}',
            'message': (
                    "{% if is_state_attr(trigger_info.data.entity_id, 'device_class', 'motion') %}"
                    "" + self.arg('motion_notify_message') + ""
                                                             "{% else %}"
                                                             "" + self.arg('default_notify_message') + ""
                                                                                                       "{% endif %}"
            )
        }))

        return actions
