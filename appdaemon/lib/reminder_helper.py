from datetime import datetime

from lib.calendar_helper import CalendarEventFetcher, is_no_school_event
from lib.component import Component
from lib.helper import concat_list, to_float
from lib.presence_helper import PRESENCE_MODE_SOMEONE_IS_HOME, PRESENCE_MODE_EVERYONE_IS_HOME
from lib.travel_time_helper import TravelTimeFetcher

TIME_TRIGGER_METHOD = 'time'
MOTION_TRIGGER_METHOD = 'motion'


def get_reminder_provider(app, config):
    provider = config['provider'];
    if provider == 'device_battery':
        return DeviceBatteryReminder(app, config)
    elif provider == 'travel_time':
        return TravelTimeReminder(app, config)
    elif provider == 'school_time':
        return SchoolDropOffTimeReminder(app, config)
    elif provider == 'drink_water':
        return DrinkWaterReminder(app, config)
    elif provider == 'bad_air_quality':
        return BadAirQualityReminder(app, config)
    elif provider == 'exceeds_threshold':
        return ExceedsThresholdMonitor(app, config)
    elif provider == 'climate_away_mode':
        return ClimateAwayModeReminder(app, config)
    else:
        raise ValueError("Invalid reminder provider config: {}".format(config))


class ReminderProvider(Component):
    def __init__(self, app, reminder_config):
        super().__init__(app, reminder_config)

        self._enabled = self.cfg.value('enabled', True)
        self._interval = self.cfg.int('interval', 30)
        self._trigger_method = self.cfg.value('trigger_method', TIME_TRIGGER_METHOD)

    @property
    def interval(self):
        return self._interval

    @property
    def enabled(self):
        return self._enabled

    @property
    def trigger_method(self):
        return self._trigger_method

    def can_provide(self, context):
        mode = context.presence_mode
        return mode == PRESENCE_MODE_SOMEONE_IS_HOME or mode == PRESENCE_MODE_EVERYONE_IS_HOME

    def provide(self, context):
        pass


class DeviceBatteryReminder(ReminderProvider):
    def __init__(self, app, reminder_config):
        super().__init__(app, reminder_config)

    def provide(self, context):
        device_monitor = self.app.get_app('device_monitor')
        checker_result = device_monitor.get_checker_result('battery_level')

        if checker_result is None or not checker_result.has_error_device_result:
            return

        low_battery_device_names = []

        for result in checker_result.error_device_results:
            friendly_name = self.get_state(result.entity_id, attribute='friendly_name')
            low_battery_device_names.append(friendly_name)

        if not low_battery_device_names:
            return None

        if len(low_battery_device_names) == 1:
            return '{} is running low'.format(
                low_battery_device_names[0])

        device_names = concat_list(low_battery_device_names)
        return '{} are running low in battery'.format(device_names)


class SchoolDropOffTimeReminder(ReminderProvider):

    def __init__(self, app, reminder_config):
        super().__init__(app, reminder_config)

        self.events_fetcher = CalendarEventFetcher(
            self,
            self.cfg.value('calendar_api_base_url', None),
            self.cfg.value('calendar_api_token', None),
        )

        self.calendar_entity_id = self.cfg.value('calendar_entity_id', None)
        self.start_time = self.cfg.value('start_time', None)
        self.end_time = self.cfg.value('end_time', None)
        self.school_time = self.cfg.value('school_time', None)
        self.workday_entity_id = self.cfg.value('workday_entity_id', None)

    def can_provide(self, context):
        if not super().can_provide(context):
            return False

        if not self.app.now_is_between(self.start_time, self.end_time):
            self.debug('Skipping SchoolDropOffTimeReminder, not between {} and {}'.format(self.start_time,
                                                                                          self.end_time))
            return False

        if not self.get_state(self.workday_entity_id) == 'on':
            self.debug('Skipping SchoolDropOffTimeReminder, not workday')
            return False

        return True

    def provide(self, context):
        events = self.events_fetcher.fetch_all_day_events(
            self.calendar_entity_id,
            datetime.today())

        self.debug('Found {} events, events={}'.format(len(events), events))
        no_school_events = [e for e in events if is_no_school_event(e)]
        self.debug('Found {} no school events, events={}'.format(len(no_school_events), no_school_events))

        if no_school_events:
            return None

        school_time = self.parse_time(self.school_time)
        time_diff = (school_time - datetime.now())
        time_diff_in_min = time_diff.total_seconds() / 60
        current_time = datetime.now().strftime('%H:%M')

        self.debug('time_diff_in_min={} vs threshold=15'.format(time_diff_in_min))

        if time_diff_in_min > 15:
            return 'It\'s {}, time to get ready for school'.format(
                current_time)

        return 'It\'s {}, you\'re running late for school'.format(current_time)


class TravelTimeReminder(ReminderProvider):
    travel_time_fetcher: TravelTimeFetcher

    def __init__(self, app, reminder_config):
        super().__init__(app, reminder_config)

        self.events_fetcher = CalendarEventFetcher(
            self,
            self.cfg.value('calendar_api_base_url', None),
            self.cfg.value('calendar_api_token', None),
        )

        self.home_location = self.cfg.value('map_home_location', None)
        self.travel_time_fetcher = TravelTimeFetcher(self, self.cfg.value('map_api_key', None))

        self.calendar_entity_id = self.cfg.value('calendar_entity_id', None)
        self.buffer_time = self.cfg.int('buffer_time', None)

    def provide(self, context):
        event = self.events_fetcher.fetch_upcoming_event(
            self.calendar_entity_id,
            datetime.today())

        if not event:
            return

        time_diff = (event.start_time.replace(tzinfo=None) - datetime.now())
        time_diff_in_min = time_diff.total_seconds() / 60
        self.debug('Found upcoming event: {} - {} at {}, time_diff={}'.format(
            event.title,
            event.start_time,
            event.location,
            time_diff))

        if time_diff_in_min > 90 or time_diff_in_min < 5:
            return None

        travel_time = self.travel_time_fetcher.fetch_travel_time(
            self.home_location,
            event.location,
            'driving',
            departure_time=datetime.now()
        )

        self.debug('event_time={}, buffer_time={}, travel_time={}'.format(
            event.start_time,
            self.buffer_time,
            travel_time.duration_in_min,
        ))

        if time_diff_in_min > travel_time.duration_in_min + self.buffer_time:
            return None

        # if travel time is more than 2 hours, then probably the location is set incorrectly
        if travel_time.duration_in_min > 120:
            return None

        return 'You\'re running late for {}, it will take {} min to {}'.format(
            event.title,
            travel_time.duration_in_min,
            travel_time.destination
        )


class TeslaBatteryReminder(ReminderProvider):
    travel_time_fetcher: TravelTimeFetcher

    def __init__(self, app, reminder_config):
        super().__init__(app, reminder_config)

        # sensor.tesla_estimated_range
        self.range_entity_id = self.cfg.value('range_entity_id', None)
        self.reserved_range = self.cfg.value('reserved_range', 50)
        self.events_fetcher = CalendarEventFetcher(
            self,
            self.cfg.value('calendar_api_base_url', None),
            self.cfg.value('calendar_api_token', None),
        )
        self.home_location = self.cfg.value('map_home_location', None)
        self.travel_time_fetcher = TravelTimeFetcher(self, self.cfg.value('map_api_key', None))

    def provide(self, context):
        current_range = self.get_state(
            self.range_entity_id) - self.reserved_range
        if current_range <= 0:
            return 'Model X is running low in battery.'

        event = self.events_fetcher.fetch_upcoming_event(
            self.calendar_entity_id,
            datetime.today())

        if not event or not event.location:
            return

        travel_time = self.travel_time_fetcher.fetch_travel_time(
            self.home_location,
            event.location,
            'driving',
            departure_time=datetime.now()
        )

        if not travel_time:
            return

        round_trip_distance = travel_time.distance * 2
        if round_trip_distance < current_range:
            return

        return 'Model X does not have enough range to get to {}'.format(
            event.title
        )


class DrinkWaterReminder(ReminderProvider):
    def __init__(self, app, reminder_config):
        super().__init__(app, reminder_config)
        self.start_time = self.cfg.value('start_time', None)
        self.end_time = self.cfg.value('end_time', None)

    def can_provide(self, context):
        if not super().can_provide(context):
            return False

        if not self.app.now_is_between(self.start_time, self.end_time):
            return False

        return True

    def provide(self, context):
        return 'Remember to drink water'


class ExceedsThresholdMonitor(ReminderProvider):
    def __init__(self, app, reminder_config):
        super().__init__(app, reminder_config)
        self.settings = self.cfg.list('settings')
        self.threshold = self.cfg.int('threshold')
        self.reminder_text = self.cfg.value('reminder_text')

    def provide(self, context):
        exceeds_thresholds = []

        for setting in self.settings:
            entity_id = setting.get('entity_id')
            area_name = setting.get('name')
            current_level = to_float(self.app.get_state(entity_id))

            if current_level >= self.threshold:
                exceeds_thresholds.append(area_name)

        if not exceeds_thresholds:
            return

        return self.reminder_text.format(area_names=concat_list(exceeds_thresholds))


class BadAirQualityReminder(ReminderProvider):
    def __init__(self, app, reminder_config):
        super().__init__(app, reminder_config)
        self.bad_air_quality_mode_entity_id = self.cfg.value('bad_air_quality_mode_entity_id', None)

    def can_provide(self, context):
        if not super().can_provide(context):
            return False

        bad_air_quality_mode = self.app.get_state(self.bad_air_quality_mode_entity_id)
        if bad_air_quality_mode == 'off':
            return False

        return True

    def provide(self, context):
        names = self.app.get_app('air_quality_monitor').bad_air_quality_names()

        if not names:
            return

        name = concat_list(names)
        return 'Attention, air quality is bad in {}'.format(name)


class ClimateAwayModeReminder(ReminderProvider):
    def __init__(self, app, reminder_config):
        super().__init__(app, reminder_config)
        self.climate_entity_id = self.cfg.value('climate_entity_id', None)

    def can_provide(self, context):
        if not super().can_provide(context):
            return False

        preset_mode = self.app.get_state(self.climate_entity_id, attribute='preset_mode')
        return preset_mode == 'Away'

    def provide(self, context):
        return 'Ecobee is still in away mode'
