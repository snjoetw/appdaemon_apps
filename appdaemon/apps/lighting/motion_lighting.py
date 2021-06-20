from typing import List, Any, Dict

from base_automation import BaseAutomation
from lib.actions import TurnOnAction, get_action, TurnOffAction
from lib.actions import figure_light_settings
from lib.constraints import get_constraint, Constraint
from lib.core.monitored_callback import monitored_callback
from lib.triggers import TriggerInfo

DEFAULT_SCENE = 'Default'
TURN_ON_TRIGGER_STATES = ['on', 'unlocked']
PATHWAY_LIGHT_TRIGGER_ENTITY_ID = "pathway_light_trigger_entity_id"


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
    motion_entity_ids: List[str]
    darkness_entity_id: str
    enabler_entity_id: str
    scene_entity_id: str
    lighting_scenes: Dict[str, Any]
    turn_off_delay: int
    dim_light_before_turn_off: bool
    turn_on_constraints: List[Constraint]
    turn_off_light_entity_ids: List[str]
    pathway_light_turn_off_delay: int

    def initialize(self):
        self.motion_entity_ids = self.cfg.list('motion_entity_id')
        self.darkness_entity_id = self.cfg.value('darkness_entity_id')
        self.enabler_entity_id = self.cfg.value('enabler_entity_id')
        self.scene_entity_id = self.cfg.value('scene_entity_id')
        self.lighting_scenes = self.cfg.value('lighting_scenes')
        self.turn_off_delay = self.cfg.value('turn_off_delay')
        self.dim_light_before_turn_off = self.cfg.value('dim_light_before_turn_off', True)

        # pathway light
        self.pathway_light_turn_off_delay = self.cfg.int('pathway_light_turn_off_delay', 20)

        self.turn_on_constraints = []
        for constraint in self.cfg.list('turn_on_constraints', []):
            self.turn_on_constraints.append(get_constraint(self, constraint))

        light_entity_ids = light_settings_to_entity_ids(self.lighting_scenes)
        self.turn_off_light_entity_ids = self.cfg.list('turn_off_light_entity_ids', light_entity_ids)
        self.turn_off_lights_handle = None

        if self.is_enabled:
            self._register_motion_state_change_event()

        if self.enabler_entity_id:
            self.listen_state(self._enabler_state_change_handler, self.enabler_entity_id)

    @property
    def is_enabled(self):
        return self.enabler_entity_id is None or self.get_state(self.enabler_entity_id) == 'on'

    def _register_motion_state_change_event(self):
        if not self.motion_entity_ids:
            return

        self.motion_event_handlers = [self.listen_state(self._motion_state_change_handler, motion_entity_id)
                                      for motion_entity_id in self.motion_entity_ids]
        self.debug('Registered motion state handler, entity_ids={}'.format(self.motion_entity_ids))

    @monitored_callback
    def _enabler_state_change_handler(self, entity, attribute, old, new, kwargs):
        if new == 'on':
            self._register_motion_state_change_event()
            return

        [self.cancel_listen_state(handle) for handle in self.motion_event_handlers]
        self.debug('Cancelled motion state handler, entity_ids={}'.format(self.motion_entity_ids))

    @monitored_callback
    def _motion_state_change_handler(self, entity, attribute, old, new, kwargs):
        self._cancel_turn_off_delay()

        self.debug('Motion triggered by entity_id={}, new={}, old={}'.format(entity, new, old))

        trigger_info = TriggerInfo("state", {
            "entity_id": entity,
            "attribute": attribute,
            "from": old,
            "to": new,
        })

        if self._should_turn_on_lights(trigger_info):
            self._turn_on_lights()
        elif self._should_turn_off_lights(trigger_info):
            self._turn_off_lights(trigger_info)

    def _should_turn_on_lights(self, trigger_info):
        if not self.is_enabled:
            return False

        if self.darkness_entity_id and self.get_state(self.darkness_entity_id) == 'Not Dark':
            return False

        motion_state = trigger_info.data.get('to')
        if motion_state not in TURN_ON_TRIGGER_STATES:
            return False

        for constraint in self.turn_on_constraints:
            if not constraint.check(trigger_info):
                return False

        return True

    def _should_turn_off_lights(self, trigger_info):
        motion_state = trigger_info.data.get('to')

        if len(self.motion_entity_ids) == 1:
            return motion_state not in TURN_ON_TRIGGER_STATES

        for motion_entity_id in self.motion_entity_ids:
            if self.get_state(motion_entity_id) in TURN_ON_TRIGGER_STATES:
                return False

        return True

    def _turn_on_lights(self):
        light_settings = self._figure_light_settings()
        if light_settings is None or not light_settings:
            return

        actions = [TurnOnAction(self, {'entity_ids': [light_setting]}) for light_setting in light_settings]
        self.do_actions(actions)

    def _figure_light_settings(self):
        for scene, light_settings in self.lighting_scenes.items():
            if not scene.startswith('sun') and not scene[0].isdigit():
                continue

            period, scene = scene.split(',')
            if not period or not scene:
                self.debug('Skipping time based scene, missing period={} or scene={}'.format(period, scene))
                continue

            start, end = period.split('-')
            if not start or not end:
                self.debug('Skipping time based scene, missing start={} or end={}'.format(start, end))
                continue

            if not self.now_is_between(start, end):
                self.debug('Skipping time based scene, now is not between start={} and end={}'.format(start, end))
                continue

            current_scene = DEFAULT_SCENE if self.scene_entity_id is None else self.get_state(self.scene_entity_id)
            if scene is not None and current_scene != scene:
                self.debug('Skipping time based scene, scene={} does not match current={}'.format(scene, current_scene))
                continue

            self.debug('Using time based scene, period={} light_settings={}'.format(period, scene, light_settings))
            return light_settings

        scene = DEFAULT_SCENE if self.scene_entity_id is None else self.get_state(self.scene_entity_id)
        if scene not in self.lighting_scenes:
            scene = DEFAULT_SCENE
        light_settings = self.lighting_scenes.get(scene)

        self.debug('Scene is {}, using light_settings={}'.format(scene, light_settings))

        return light_settings

    def _turn_off_lights(self, trigger_info=None):
        turn_off_delay = self._figure_turn_off_delay(trigger_info)

        if turn_off_delay is None:
            return

        self.debug('About to turn lights off in {} second'.format(turn_off_delay))
        self.turn_off_lights_handle = self.run_in(self._turn_off_lights_handler, turn_off_delay)

    def _cancel_turn_off_delay(self):
        if self.turn_off_lights_handle is not None:
            self.cancel_timer(self.turn_off_lights_handle)
            self.turn_off_lights_handle = None
            self.debug('Cancelled turn off delay timer')

    def _turn_off_lights_handler(self, kwargs={}):
        actions = [TurnOffAction(self, {
            'entity_ids': self.turn_off_light_entity_ids,
            'dim_light_before_turn_off': self.dim_light_before_turn_off,
        })]
        self.do_actions(actions)

    def _figure_turn_off_delay(self, trigger_info: TriggerInfo):
        if trigger_info is not None and trigger_info.data.get('entity_id') == PATHWAY_LIGHT_TRIGGER_ENTITY_ID:
            return self.pathway_light_turn_off_delay

        if trigger_info is not None and trigger_info.platform == 'time':
            return 0

        return self.turn_off_delay

    def trigger_pathway_light(self):
        self._motion_state_change_handler(PATHWAY_LIGHT_TRIGGER_ENTITY_ID, None, 'off', 'on', None)
        # trigger turn off immediately so that we can start pathway light turn off counter
        self._motion_state_change_handler(PATHWAY_LIGHT_TRIGGER_ENTITY_ID, None, 'on', 'off', None)
