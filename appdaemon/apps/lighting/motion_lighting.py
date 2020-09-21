from configurable_automation import ConfigurableAutomation
from lib.actions import figure_light_settings


def light_settings_to_entity_ids(settings):
    entity_ids = set()
    for lighting_mode, settings in settings:
        for entity_id in figure_light_settings(settings).keys():
            entity_ids.add(entity_id)

    return list(entity_ids)


class MotionLighting(ConfigurableAutomation):

    def initialize(self):
        super().initialize()

        self.enabler_entity_id = self.arg('enabler_entity_id')
        self.lighting_mode_entity_id = self.arg('lighting_mode_entity_id')
        self.motion_entity_ids = self.list_arg('motion_entity_id')
        self.turn_off_delay = self.int_arg('turn_off_delay')
        self.lighting_mode_settings = self.arg('lighting_modes')
        self.turn_on_constraints = self.list_arg('turn_on_constraints', [])
        self.light_entity_ids = light_settings_to_entity_ids(
            self.lighting_mode_settings.items())
        self.cancel_auto_off = self.arg('cancel_auto_off', True)

        # timer config
        self.timer_config = self.arg('timer')
        if self.timer_config:
            self.timer_config = TimerConfig(self.timer_config)

        # image processing config
        self.image_processing_config = self.arg('image_processing')
        if self.image_processing_config:
            self.image_processing_config = ImageProcessingConfig(
                self.image_processing_config)

        if not self.motion_entity_ids:
            self.warn('Cannot initialize without motion_entity_ids')
            return

        # add image_processing_entity_id as motion trigger
        if self.image_processing_config:
            self.motion_entity_ids.append(
                self.image_processing_config.person_entity_id)

        self.init_trigger('state', {
            'entity_id': self.motion_entity_ids
        })

        state_on_handlers = self.create_triggered_state_on_handlers()
        for handler in state_on_handlers:
            self.init_handler(handler)

        if self.turn_off_delay > 0:

            # if lights will be turned off when motion stopped, then we also
            # need to check light state, if it's turned off then also cancel
            # any pending jobs
            if self.cancel_auto_off:
                self.init_trigger('state', {
                    'entity_id': self.light_entity_ids,
                    'to': 'off',
                })
            self.init_handler(self.create_light_state_off_handler())
            self.init_handler(self.create_triggered_state_off_handler())

        if self.timer_config:
            self.init_trigger('time', {
                'minutes': 15
            })

            for handler in self.create_turn_on_time_handlers():
                self.init_handler(handler)

            self.init_handler(self.create_turn_off_time_handler())

    def create_triggered_state_on_handlers(self):
        handlers = []

        for lighting_mode, settings in self.lighting_mode_settings.items():
            constraints = []
            actions = []

            if self.enabler_entity_id:
                constraints.append(self.create_constraint('state', {
                    'entity_id': self.enabler_entity_id,
                    'state': 'on'
                }))

            for constraint in self.turn_on_constraints:
                constraints.append(self.create_constraint(
                    constraint['platform'],
                    constraint))

            constraints.append(self.create_constraint('triggered_state', {
                'entity_id': self.motion_entity_ids,
                'to': 'on'
            }))

            if self.lighting_mode_entity_id:
                constraints.append(self.create_constraint('state', {
                    'entity_id': self.lighting_mode_entity_id,
                    'state': lighting_mode
                }))

            for setting in settings:
                actions.append(self.create_action('turn_on', {
                    'entity_ids': [setting],
                }))

            actions.append(self.create_action('cancel_job', {
                'cancel_all': True,
            }))

            handlers.append(self.create_handler(constraints, actions))

        return handlers

    def create_triggered_state_off_handler(self):
        constraints = []
        actions = []

        if self.enabler_entity_id:
            constraints.append(self.create_constraint('state', {
                'entity_id': self.enabler_entity_id,
                'state': 'on'
            }))

        # need this constraint to make sure the trigger is from motion instead of time
        constraints.append(self.create_constraint('triggered_state', {
            'entity_id': self.motion_entity_ids,
            'to': ['off', 'unavailable'],
        }))

        # these constraints are to ensure all the motion are off or unavailable before turning off the light
        for motion_entity_id in self.motion_entity_ids:
            constraints.append(self.create_constraint('state', {
                'entity_id': motion_entity_id,
                'state': ['off', 'unavailable'],
            }))

        # if image_processing is present, then we wanna start scanning when the motion just stopped
        # and stop scanning when the turn_off_delay is up.
        # if there's any detection, it'll be treated as if there's motion
        if self.image_processing_config:
            actions.append(self.create_action('turn_on', {
                'entity_ids': [self.image_processing_config.enabler_entity_id]
            }))

        turn_off_entity_ids = self.light_entity_ids.copy()
        if self.image_processing_config:
            turn_off_entity_ids.append(
                self.image_processing_config.enabler_entity_id)

        actions.append(self.create_action('cancel_job', {
            'cancel_all': True,
        }))
        actions.append(self.create_turn_off_action(turn_off_entity_ids))

        return self.create_handler(constraints, actions,
                                   do_parallel_actions=False)

    def create_turn_off_action(self, turn_off_entity_ids):
        if self.turn_off_delay > 0:
            return self.create_action('delay', {
                'delay': self.turn_off_delay,
                'actions': [{
                    'platform': 'turn_off',
                    'entity_ids': turn_off_entity_ids,
                    'dim_light_before_turn_off': self.arg('dim_light_before_turn_off', True)
                }]
            })

        return self.create_action('turn_off', {
            'entity_ids': turn_off_entity_ids,
            # 'delay': self.turn_off_delay,
            # 'dim_light_before_turn_off': self.arg('dim_light_before_turn_off', True)
        })

    def create_light_state_off_handler(self):
        if self.turn_off_delay <= 0:
            return

        constraints = []
        actions = []

        constraints.append(self.create_constraint('triggered_state', {
            'entity_id': self.light_entity_ids,
            'to': 'off',
        }))
        constraints.append(self.create_constraint('has_scheduled_job', {}))
        actions.append(self.create_action('cancel_job', {
            'cancel_all': True,
        }))

        return self.create_handler(constraints, actions)

    def create_turn_on_time_handlers(self):
        handlers = []

        for lighting_mode, settings in self.lighting_mode_settings.items():
            constraints = []
            actions = []

            constraints.append(self.create_constraint('time', {
                'start_time': self.timer_config.turn_on_start_time,
                'end_time': self.timer_config.turn_on_end_time,
            }))

            if self.lighting_mode_entity_id:
                constraints.append(self.create_constraint('state', {
                    'entity_id': self.lighting_mode_entity_id,
                    'state': lighting_mode
                }))

            actions.append(self.create_action('turn_on', {
                'entity_ids': settings,
            }))

            if self.enabler_entity_id:
                actions.append(self.create_action('turn_off', {
                    'entity_ids': {
                        self.enabler_entity_id: {
                            'force_off': False,
                        }
                    },
                }))

            handlers.append(self.create_handler(constraints, actions))

        return handlers

    def create_turn_off_time_handler(self):
        constraints = []
        actions = []

        constraints.append(self.create_constraint('time', {
            'start_time': self.timer_config.turn_on_end_time,
            'end_time': self.timer_config.turn_on_start_time,
        }))

        for lighting_mode, settings in self.lighting_mode_settings.items():
            actions.append(self.create_action('turn_off', {
                'entity_ids': settings,
            }))

        if self.enabler_entity_id:
            constraints.append(self.create_constraint('state', {
                'entity_id': self.enabler_entity_id,
                'state': 'off'
            }))

            actions.append(self.create_action('turn_on', {
                'entity_ids': {
                    self.enabler_entity_id: {
                        'force_on': False
                    }
                },
            }))

        return self.create_handler(constraints, actions)


class ImageProcessingConfig:
    def __init__(self, config):
        self._person_entity_id = config['person_entity_id']
        self._enabler_entity_id = config['enabler_entity_id']

    @property
    def person_entity_id(self):
        return self._person_entity_id

    @property
    def enabler_entity_id(self):
        return self._enabler_entity_id


class TimerConfig:
    def __init__(self, config):
        self._turn_on_start_time = config['turn_on_start_time']
        self._turn_on_end_time = config['turn_on_end_time']

    @property
    def turn_on_start_time(self):
        return self._turn_on_start_time

    @property
    def turn_on_end_time(self):
        return self._turn_on_end_time
