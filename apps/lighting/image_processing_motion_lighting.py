from lighting.motion_lighting2 import MotionLighting


class ImageProcessingMotionLighting(MotionLighting):

    def initialize(self):
        super().initialize()
        self.image_processing_enabler_entity_id = self.arg('image_processing_enabler_entity_id')

    def motion_state_change_handler(self, entity, attribute, old, new, kwargs):
        self.cancel_turn_off_delay()

        if new == 'on':
            self.turn_on_lights()
            return

        if new == 'off':
            self.enable_image_processing()

        if self.should_turn_off_lights(new):
            self.turn_off_lights()
            self.disable_image_processing()

    def enable_image_processing(self):
        self.turn_on(self.image_processing_enabler_entity_id)
        self.debug('Enabled image_processing_enabler_entity_id={}'.format(self.image_processing_enabler_entity_id))

    def disable_image_processing(self):
        self.turn_off(self.image_processing_enabler_entity_id)
        self.debug('Disabled image_processing_enabler_entity_id={}'.format(self.image_processing_enabler_entity_id))
