from lib.actions import TurnOnAction, get_action, TurnOffAction
from lib.actions import figure_light_settings

from base_automation import BaseAutomation

DEFAULT_SCENE = 'Default'


def light_settings_to_entity_ids(settings):
    entity_ids = set()
    for lighting_mode, settings in settings.items():
        for entity_id in figure_light_settings(settings).keys():
            entity_ids.add(entity_id)

    return list(entity_ids)


def create_turn_off_action(app, entity_id):
    return get_action(app, {
        'platform': 'delay',
        'actions': [{
            'platform': 'turn_off',
            'entity_id': entity_id
        }],
    })


class MotionLighting(BaseAutomation):

    def initialize(self):
        self.motion_entity_ids = self.list_arg('motion_entity_id')
        self.enabler_entity_id = self.arg('enabler_entity_id')
        self.scene_entity_id = self.arg('scene_entity_id')
        self.lighting_scenes = self.arg('lighting_scenes')
        self.turn_off_delay = self.arg('turn_off_delay')

        self.light_entity_ids = light_settings_to_entity_ids(self.lighting_scenes)
        self.turn_off_lights_handle = None

        self.register_motion_state_change_event()

        if self.enabler_entity_id:
            self.listen_state(self.enabler_state_change_handler, self.enabler_entity_id)

    def register_motion_state_change_event(self):
        self.motion_event_handlers = [self.listen_state(self.motion_state_change_handler, motion_entity_id)
                                      for motion_entity_id in self.motion_entity_ids]
        self.debug('Registered motion state handler, entity_ids={}'.format(self.motion_entity_ids))

    def enabler_state_change_handler(self, entity, attribute, old, new, kwargs):
        if new == 'on':
            self.register_motion_state_change_event()
            return

        [self.cancel_listen_state(handle) for handle in self.motion_event_handlers]
        self.debug('Cancelled motion state handler, entity_ids={}'.format(self.motion_entity_ids))

    def motion_state_change_handler(self, entity, attribute, old, new, kwargs):
        self.cancel_turn_off_delay()

        self.debug('Motion triggered by entity_id={}, new={}, old={}'.format(entity, new, old))

        if self.should_turn_on_lights(new):
            self.turn_on_lights()
        elif self.should_turn_off_lights(new):
            self.turn_off_lights()

    def should_turn_on_lights(self, motion_state):
        return motion_state == 'on'

    def should_turn_off_lights(self, motion_state):
        if len(self.motion_entity_ids) == 1:
            return motion_state != 'on'

        for motion_entity_id in self.motion_entity_ids:
            if self.get_state(motion_entity_id) == 'on':
                return False

        return True

    def turn_on_lights(self):
        scene = DEFAULT_SCENE if self.scene_entity_id is None else self.get_state(self.scene_entity_id)
        light_settings = self.lighting_scenes.get(scene)

        if light_settings is None:
            self.debug('No scene settings defined for scene={}'.format(scene))
            return

        self.debug('Scene is {}, using light_settings={}'.format(scene, light_settings))

        actions = [TurnOnAction(self, {'entity_ids': [light_setting]}) for light_setting in light_settings]
        self.do_actions(actions)

    def turn_off_lights(self):
        if self.turn_off_delay is None:
            return

        self.debug('Motion stopped, will turn off in {}'.format(self.turn_off_delay))
        self.turn_off_lights_handle = self.run_in(self.turn_off_lights_handler, self.turn_off_delay)

    def cancel_turn_off_delay(self):
        if self.turn_off_lights_handle is not None:
            self.cancel_timer(self.turn_off_lights_handle)
            self.turn_off_lights_handle = None
            self.debug('Cancelled turn off delay timer')

    def turn_off_lights_handler(self, kwargs={}):
        actions = [TurnOffAction(self, {'entity_ids': self.light_entity_ids})]
        self.do_actions(actions)
