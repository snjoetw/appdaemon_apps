from base_automation import BaseAutomation
from lib.core.monitored_callback import monitored_callback
from lib.helper import to_int

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
        self.cleaned_count_entity_id = self.cfg.value('runtime_entity_id')
        self.vacuum_entity_id = self.cfg.value('vacuum_entity_id')
        self.monitor_state_entity_id = self.cfg.value('monitor_state_entity_id')
        self.cleaned_count_threshold = self.cfg.value('cleaned_count_threshold', 100)
        self.dumping_spot_x_coord = self.cfg.value('dumping_spot_x_coord')
        self.dumping_spot_y_coord = self.cfg.value('dumping_spot_y_coord')

        self.listen_state(self.vacuum_state_change_handler, self.vacuum_entity_id, attribute="all")

    @monitored_callback
    def vacuum_state_change_handler(self, entity, attribute, old, new, kwargs):
        self.debug('Received vacuum state change, entity_id={}\nold={}\nnew={}'.format(entity, old, new))
        self.diff(old, new)

        if get_state(old) == 'unavailable' or get_state(new) == 'unavailable':
            self.debug('New state is unavailable, skipping ...')
            return

        if self.started_new_cleaning_job(old, new):
            self.update_monitor_state(NONE_STATE)

        current_monitor_state = self.current_monitor_state()

        if NONE_STATE == current_monitor_state:
            return self.handle_state_none(old, new)
        elif AWAITING_FULL_CHARGE_STATE == current_monitor_state:
            return self.handle_state_awaiting_full_charge(old, new)
        elif HEADING_TO_LAUNDRY_ROOM_STATE == current_monitor_state:
            return self.handle_state_heading_to_laundry_room(old, new)
        elif AWAITING_DUSTBIN_REMOVAL_STATE == current_monitor_state:
            return self.handle_state_awaiting_dustbin_removal(old, new)

        self.error('Unsupported monitor_state={}, old={}, new={}'.format(current_monitor_state, old, new))

    def handle_state_none(self, old_entity, new_entity):
        cleaned_area_count = to_int(self.get_state(self.cleaned_count_entity_id))

        if self.is_attribute_changed(old_entity, new_entity, 'cleaned_area'):
            cleaned_area_count = cleaned_area_count + get_int_attribute(new_entity, 'cleaned_area')
            self.update_clean_count(cleaned_area_count)

        if cleaned_area_count < self.cleaned_count_threshold:
            self.update_monitor_state(NONE_STATE)
            return

        battery_level = get_int_attribute(new_entity, 'battery_level')
        if battery_level < 100:
            self.update_monitor_state(AWAITING_FULL_CHARGE_STATE)
        else:
            self.go_to_dumping_area()

    def handle_state_awaiting_full_charge(self, old_entity, new_entity):
        battery_level = get_int_attribute(new_entity, 'battery_level')
        if battery_level < 100:
            return

        self.go_to_dumping_area()

    def handle_state_heading_to_laundry_room(self, old_entity, new_entity):
        if not self.is_arrived_dumping_area(old_entity, new_entity):
            self.debug('handle_state_heading_to_laundry_room => NOT arrived dumping area')
            self.diff(old_entity, new_entity)
            return

        self.update_monitor_state(AWAITING_DUSTBIN_REMOVAL_STATE)

    def handle_state_awaiting_dustbin_removal(self, old_entity, new_entity):
        state = get_state(new_entity)
        if state != 'returning':
            self.debug('handle_state_awaiting_dustbin_removal => NOT returning')
            self.diff(old_entity, new_entity)
            return

        self.update_monitor_state(NONE_STATE)
        self.update_clean_count(0)

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

    def started_new_cleaning_job(self, old, new):
        old_state = get_state(old)
        new_state = get_state(new)
        if old_state == 'cleaning' or new_state != 'cleaning':
            self.log('Not new cleaning job, {} vs {}'.format(old_state, new_state))
            return False

        old_status = get_attribute(old, 'status')
        new_status = get_attribute(new, 'status')
        if old_status == 'Segment cleaning' or new_status != 'Segment cleaning':
            self.log('Not new cleaning job, {} vs {}'.format(old_status, new_status))
            return False

        self.log('Started new cleaning job')

        return True

    def is_arrived_dumping_area(self, old, new):
        if self.current_monitor_state() != HEADING_TO_LAUNDRY_ROOM_STATE:
            self.debug('is_arrived_dumping_area => NOT HEADING_TO_LAUNDRY_ROOM_STATE')
            return False

        old_state = get_state(old)
        new_state = get_state(new)
        if old_state != 'cleaning' or new_state != 'idle':
            self.debug('is_arrived_dumping_area => old_state ({}) NOT cleaning or new_state NOT idle ({})'.format(
                old_state, new_state))
            return False

        old_status = get_attribute(old, 'status')
        new_status = get_attribute(new, 'status')

        if old_status != 'Going to target' or new_status != 'Idle':
            self.debug('is_arrived_dumping_area => old_state ({}) NOT "Going to target" or new_state NOT Idle ({})'
                       .format(old_status, new_status))
            return False

        self.log('Arrived dumping area')

        return True

    def go_to_dumping_area(self):
        self.call_service(
            'xiaomi_miio/vacuum_goto',
            entity_id=self.vacuum_entity_id,
            x_coord=self.dumping_spot_x_coord,
            y_coord=self.dumping_spot_y_coord)
        self.update_monitor_state(HEADING_TO_LAUNDRY_ROOM_STATE)

    def update_clean_count(self, count):
        self.call_service('input_number/set_value', entity_id=self.cleaned_count_entity_id, value=count)

    def update_monitor_state(self, state):
        self.select_option(self.monitor_state_entity_id, state)

    def current_monitor_state(self):
        return self.get_state(self.monitor_state_entity_id)

    def diff(self, old, new):
        msg = 'Current: state={}, status={}\n'.format(get_state(new), get_attribute(new, 'status'))
        old_state = get_state(old)
        new_state = get_state(new)
        if old_state != new_state:
            msg = msg + 'state: {}->{}\n'.format(old_state, new_state)

        for attribute in ['status', 'cleaning_time', 'cleaned_area', 'battery_level', 'clean_start', 'clean_stop']:
            old_attribute = get_attribute(old, attribute)
            new_attribute = get_attribute(new, attribute)
            if old_attribute != new_attribute:
                msg = msg + '{}: {}->{}\n'.format(attribute, old_attribute, new_attribute)

        if msg:
            self.log(msg)
