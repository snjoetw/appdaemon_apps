from base_automation import BaseAutomation
from lib.actions import TurnOnAction, get_action, TurnOffAction
from lib.actions import figure_light_settings
from lib.constraints import get_constraint
from lib.triggers import TriggerInfo

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

        self.turn_on_constraints = []
        for constraint in self.list_arg('turn_on_constraints', []):
            self.turn_on_constraints.append(get_constraint(self, constraint))

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

        trigger_info = TriggerInfo("state", {
            "entity_id": entity,
            "attribute": attribute,
            "from": old,
            "to": new,
        })

        if self.should_turn_on_lights(trigger_info):
            self.turn_on_lights()
        elif self.should_turn_off_lights(trigger_info):
            self.turn_off_lights()

    def should_turn_on_lights(self, trigger_info):
        motion_state = trigger_info.data.get('to')
        if motion_state != 'on':
            return False

        for constraint in self.turn_on_constraints:
            if not constraint.check(trigger_info):
                return False

        return True

    def should_turn_off_lights(self, trigger_info):
        motion_state = trigger_info.data.get('to')

        if len(self.motion_entity_ids) == 1:
            return motion_state != 'on'

        for motion_entity_id in self.motion_entity_ids:
            if self.get_state(motion_entity_id) == 'on':
                return False

        return True

    def turn_on_lights(self):
        light_settings = self.figure_light_settings()
        if light_settings is None:
            return

        actions = [TurnOnAction(self, {'entity_ids': [light_setting]}) for light_setting in light_settings]
        self.do_actions(actions)

    def figure_light_settings(self):
        for scene, light_settings in self.lighting_scenes.items():
            if not scene.startswith('sun') and not scene[0].isdigit():
                continue

            start, end = scene.split('-')
            if not start or not end:
                continue

            if self.now_is_between(start, end):
                return light_settings

        scene = DEFAULT_SCENE if self.scene_entity_id is None else self.get_state(self.scene_entity_id)
        light_settings = self.lighting_scenes.get(scene)
        self.debug('Scene is {}, using light_settings={}'.format(scene, light_settings))

        return light_settings

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
