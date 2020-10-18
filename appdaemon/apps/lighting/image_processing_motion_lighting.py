from lib.actions import TurnOnAction, TurnOffAction
from lib.triggers import TriggerInfo
from lighting.motion_lighting2 import MotionLighting


class ImageProcessingMotionLighting(MotionLighting):

    def initialize(self):
        super().initialize()

        self.image_processing_settings = ImageProcessingSettings(self.arg('image_processing_settings'))
        person_detected_entity_id = self.image_processing_settings.person_detected_entity_id
        self.listen_state(self.image_processing_state_change_handler, person_detected_entity_id)

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
            self.turn_off_image_processing()
        elif self.should_turn_on_image_processing(trigger_info):
            self.turn_on_image_processing()
        else:
            self.turn_off_image_processing()

    def should_turn_on_image_processing(self, trigger_info):
        return self.should_turn_off_lights(trigger_info)

    def turn_on_image_processing(self):
        self.debug('Turning on image processing')

        enabler_entity_id = self.image_processing_settings.enabler_entity_id
        self.do_actions([TurnOnAction(self, {'entity_ids': enabler_entity_id})])
        # turn off lights here in case image processing is not running
        self.turn_off_lights()

    def turn_off_image_processing(self):
        self.debug('Turning off image processing')

        enabler_entity_id = self.image_processing_settings.enabler_entity_id
        self.do_actions([TurnOffAction(self, {'entity_ids': enabler_entity_id})])

    def image_processing_state_change_handler(self, entity, attribute, old, new, kwargs):
        self.debug('Image processing state changed entity_id={}, new={}, old={}'.format(entity, new, old))

        self.cancel_turn_off_delay()

        if new == 'off':
            self.turn_off_lights()

    def turn_off_lights_handler(self, kwargs={}):
        self.debug('Turning off image processing and lights')

        super().turn_off_lights_handler(kwargs)
        self.turn_off_image_processing()


class ImageProcessingSettings:
    def __init__(self, config):
        self._enabler_entity_id = config['enabler_entity_id']
        self._person_detected_entity_id = config['person_detected_entity_id']

    @property
    def enabler_entity_id(self):
        return self._enabler_entity_id

    @property
    def person_detected_entity_id(self):
        return self._person_detected_entity_id
