from base_automation import BaseAutomation
from lib.helper import to_float, to_int

NONE_STATE = 'NONE'
AWAITING_FULL_CHARGE_STATE = 'AWAITING_FULL_CHARGE'
HEADING_TO_LAUNDRY_ROOM_STATE = 'HEADING_TO_LAUNDRY_ROOM'
AWAITING_DUSTBIN_REMOVAL_STATE = 'AWAITING_DUSTBIN_REMOVAL'
AWAITING_CLEANED_DUSTBIN_STATE = 'AWAITING_CLEANED_DUSTBIN'
RETURNING_HOME_STATE = 'RETURNING_HOME'


def get_int_attribute(entity, attribute):
    value = get_attribute(entity, attribute)

    if value is None:
        return None

    return to_int(value)


def get_attribute(entity, attribute):
    if entity is None:
        return None

    attributes = entity.get('attributes', {})
    return attributes.get(attribute)


def get_state(entity):
    if entity is None:
        return None

    return entity.get('state')


class VacuumDustbinMonitor(BaseAutomation):

    def initialize(self):
        self.cleaned_count_entity_id = self.arg('runtime_entity_id')
        self.vacuum_entity_id = self.arg('vacuum_entity_id')
        self.monitor_state_entity_id = self.arg('monitor_state_entity_id')
        self.cleaned_count_threshold = self.arg('cleaned_count_threshold', 100)
        self.dumping_spot_x_coord = self.arg('dumping_spot_x_coord')
        self.dumping_spot_y_coord = self.arg('dumping_spot_y_coord')

        # self.listen_event(self.event_change_handler, 'zha_event')

        self.listen_state(self.vacuum_state_change_handler, self.vacuum_entity_id, attribute="all")

    def event_change_handler(self, event_name, data, kwargs):
        self.debug('Received event change, {}, {}, {}'.format(event_name, data, kwargs))

        args = data.get('args', {});
        if not args:
            return

        tilt_degrees = to_float(args[0].get('degrees'))
        if not tilt_degrees:
            return

        self.log('Received tilt change, {}'.format(tilt_degrees))

        if tilt_degrees > 80:
            self.handle_dustbin_open()
        else:
            self.handle_dustbin_close()

    def handle_dustbin_open(self):
        if self.current_monitor_state() != AWAITING_DUSTBIN_REMOVAL_STATE:
            return

        self.update_clean_count(0)
        self.update_monitor_state(AWAITING_CLEANED_DUSTBIN_STATE)

    def handle_dustbin_close(self):
        if self.current_monitor_state() != AWAITING_CLEANED_DUSTBIN_STATE:
            return

        self.update_monitor_state(RETURNING_HOME_STATE)

    def vacuum_state_change_handler(self, entity, attribute, old, new, kwargs):
        self.debug('Received vacuum state change, {}, {}, {}, {}, {}'.format(entity, attribute, old, new, kwargs))

        if self.is_attribute_changed(old, new, 'cleaning_count'):
            self.handle_cleaning_count_change(new)
            return

        if self.is_attribute_changed(old, new, 'battery_level'):
            self.handle_battery_level_change(new)
            return

        if self.is_arrived_dumping_area(old, new):
            self.update_monitor_state(AWAITING_DUSTBIN_REMOVAL_STATE)
            return

        if self.is_state_changed(old, new):
            self.handle_state_change(new)
            return

    def is_state_changed(self, old, new):
        old_state = get_state(old)
        new_state = get_state(new)
        changed = old_state != new_state

        self.log('State changed, {} => {}'.format(old_state, new_state))

        return changed

    def is_attribute_changed(self, old, new, attribute_name):
        old_attribute = get_attribute(old, attribute_name)
        new_attribute = get_attribute(new, attribute_name)
        if old_attribute == new_attribute:
            return False;

        self.log('Attribute {} changed, {} => {}'.format(attribute_name, old_attribute, new_attribute))

        return True

    def handle_cleaning_count_change(self, vacuum_entity):
        existing_cleaned_area_count = to_int(self.get_state(self.cleaned_count_entity_id))
        new_cleaned_area_count = existing_cleaned_area_count + get_int_attribute(vacuum_entity, 'cleaned_area')
        self.update_clean_count(new_cleaned_area_count)

        if new_cleaned_area_count < self.cleaned_count_threshold:
            self.update_monitor_state(NONE_STATE)
            return

        battery_level = get_int_attribute(vacuum_entity, 'battery_level')
        if battery_level < 100:
            self.update_monitor_state(AWAITING_FULL_CHARGE_STATE)
        else:
            self.go_to_dumping_area()

    def handle_battery_level_change(self, vacuum_entity):
        battery_level = get_int_attribute(vacuum_entity, 'battery_level')

        if battery_level < 100:
            return

        if self.current_monitor_state() != AWAITING_FULL_CHARGE_STATE:
            return

        self.go_to_dumping_area()

    def is_arrived_dumping_area(self, old, new):
        if self.current_monitor_state() != HEADING_TO_LAUNDRY_ROOM_STATE:
            return False

        old_state = get_state(old)
        new_state = get_state(new)
        if old_state != 'cleaning' or new_state != 'idle':
            return False

        old_status = get_attribute(old, 'status')
        new_status = get_attribute(new, 'status')

        if old_status != 'Going to target' or new_status != 'Idle':
            return False

        self.log('Arrived dumping area')

        return True

    def handle_state_change(self, vacuum_entity):
        state = get_state(vacuum_entity)

        if state != 'returning':
            return

        if self.current_monitor_state() != AWAITING_DUSTBIN_REMOVAL_STATE:
            return

        self.update_monitor_state(NONE_STATE)
        self.update_clean_count(0)

    def go_to_dumping_area(self):
        self.update_monitor_state(HEADING_TO_LAUNDRY_ROOM_STATE)
        self.call_service(
            'xiaomi_miio/vacuum_goto',
            entity_id=self.vacuum_entity_id,
            x_coord=self.dumping_spot_x_coord,
            y_coord=self.dumping_spot_y_coord)

    def update_clean_count(self, count):
        self.call_service('input_number/set_value', entity_id=self.cleaned_count_entity_id, value=count)

    def update_monitor_state(self, state):
        self.set_state(self.monitor_state_entity_id, state=state)

    def current_monitor_state(self):
        return self.get_state(self.monitor_state_entity_id)
