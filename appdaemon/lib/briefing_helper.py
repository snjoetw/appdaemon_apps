import calendar
from datetime import datetime, timedelta

from commute_time_monitor import CommuteTimeMonitor
from lib.calendar_helper import CalendarEventFetcher
from lib.component import Component
from lib.context import PartsOfDay
from lib.helper import to_int, concat_list
from lib.stock_helper import StockQuoteFetcher

SHORT_PAUSE = '<break time=".2s" />'
MEDIUM_PAUSE = '<break time=".3s" />'


def get_briefing_provider(app, config):
    app.debug(config)
    provider = config['provider'];
    if provider == 'greet':
        return GreetBriefingProvider(app, config)
    elif provider == 'weather_forecast':
        return WeatherForecastBriefingProvider(app, config)
    elif provider == 'commute_time':
        return CommuteTimeBriefingProvider(app, config)
    elif provider == 'calendar':
        return CalendarBriefingProvider(app, config)
    elif provider == 'reminder':
        return ReminderBriefingProvider(app, config)
    elif provider == 'stock':
        return StockPriceProvider(app, config)
    elif provider == 'low_battery_device':
        return LowBatteryDeviceBriefingProvider(app, config)
    else:
        raise ValueError("Invalid briefing provider config: " + config)


class BriefingProvider(Component):
    def __init__(self, app, briefing_config):
        super().__init__(app, briefing_config)

    def can_brief(self, context):
        return False

    def briefing(self, context):
        pass


class GreetBriefingProvider(BriefingProvider):
    def __init__(self, app, briefing_config):
        super().__init__(app, briefing_config)

    def can_brief(self, context):
        return True

    def briefing(self, context):
        if context.parts_of_day == PartsOfDay.MORNING:
            return 'Good morning!'
        elif context.parts_of_day == PartsOfDay.AFTERNOON:
            return 'Good afternoon!'
        elif context.parts_of_day == PartsOfDay.EVENING or context.parts_of_day == PartsOfDay.NIGHT:
            return 'Good evening!'


class CommuteTimeBriefingProvider(BriefingProvider):
    def __init__(self, app, briefing_config):
        super().__init__(app, briefing_config)

        self.workday_entity_id = self.cfg.value('workday_entity_id', None)
        self.start_time = self.cfg.value('start_time', None)
        self.end_time = self.cfg.value('end_time', None)

    def can_brief(self, context):
        return self.get_state(self.workday_entity_id) == 'on' \
               and self.is_in_monitoring_time()

    def is_in_monitoring_time(self):
        return self.app.now_is_between(self.start_time, self.end_time)

    def briefing(self, context):
        commute_time_monitor: CommuteTimeMonitor = self.app.get_app('commute_time_monitor')
        departure_time = datetime.now() + timedelta(minutes=10)
        routes = commute_time_monitor.get_routes(departure_time)

        if not routes:
            return
        best_route = routes[0]
        return 'Your commute to work is currently {} ' \
               'minute if you take skytrain from {}.' \
            .format(best_route.duration_in_min, best_route.name)


class WeatherForecastBriefingProvider(BriefingProvider):
    def __init__(self, app, briefing_config):
        super().__init__(app, briefing_config)

    def can_brief(self, context):
        return True

    def briefing(self, context):
        today_summary = self.transform_summary(
            self.get_state("sensor.dark_sky_hourly_summary"))
        max_temp = to_int(
            self.get_state("sensor.dark_sky_daytime_high_temperature_0d"))
        min_temp = to_int(
            self.get_state("sensor.dark_sky_overnight_low_temperature_0d"))
        current_temp = to_int(self.get_state("sensor.dark_sky_temperature"))
        current_summary = self.get_state("sensor.dark_sky_summary")

        message = "Right now in Burnaby it's {} degrees and {}. " \
                  "{}It's going to be {}, " \
                  "with a high of {} " \
                  "and low of {} degrees.".format(
            current_temp,
            current_summary,
            SHORT_PAUSE,
            today_summary,
            max_temp,
            min_temp)

        precipitation_type = self.get_state("sensor.dark_sky_precip_0d")
        precipitation_probability = to_int(
            self.get_state("sensor.dark_sky_precip_probability_0d"))

        if precipitation_probability > 30:
            message += "{} Remember to bring umbrella today as there's {}% chance of {}.".format(
                SHORT_PAUSE,
                precipitation_probability,
                precipitation_type)

        return message

    def transform_summary(self, summary_text):
        summary_text = summary_text.lower()
        summary_text = summary_text.replace('light rain', 'raining')
        return summary_text


class CalendarBriefingProvider(BriefingProvider):
    def __init__(self, app, briefing_config):
        super().__init__(app, briefing_config)

        self.events_fetcher = CalendarEventFetcher(
            self,
            self.cfg.value('api_base_url', None),
            self.cfg.value('api_token', None),
        )

        self.calendar_entity_id = self.cfg.value('calendar_entity_id', None)

    def can_brief(self, context):
        return True

    def briefing(self, context):
        regular_events = self.fetch_regular_events()
        if not regular_events:
            return

        return 'Today you have {} {}, {}'.format(
            len(regular_events),
            'appointments' if len(regular_events) > 1 else 'appointment',
            create_regular_event_text(regular_events),
        )

    def fetch_regular_events(self):
        regular_events = self.events_fetcher.fetch_regular_events(
            self.calendar_entity_id,
            datetime.today())

        self.debug('Found {} events'.format(len(regular_events)))
        for e in regular_events:
            self.debug(
                '- {}: {} to {}, location={}, all_day={}, today={}, tomorrow={}'.format(
                    e.title,
                    e.start_time,
                    e.end_time,
                    e.location,
                    e.is_all_day,
                    e.is_today,
                    e.is_tomorrow
                ))

        now = datetime.now()
        filtered = [e for e in regular_events if
                    e.start_time.replace(tzinfo=None) > now]

        self.debug('Found {} future events'.format(len(filtered)))

        for e in filtered:
            self.debug('- {}: {}-{}, all_day={}, today={}, tomorrow={}'.format(
                e.title,
                e.start_time,
                e.end_time,
                e.is_all_day,
                e.is_today,
                e.is_tomorrow
            ))

        return filtered


def create_regular_event_text(regular_events):
    regular_events.sort(key=lambda e: e.start_time)

    last_regular_event = regular_events.pop()

    if not regular_events:
        return to_event_briefing_text(last_regular_event)

    text = ', '.join([to_event_briefing_text(e) for e in regular_events])
    text += '{} and {}'.format(
        SHORT_PAUSE,
        to_event_briefing_text(last_regular_event),
    )

    return text


def to_event_briefing_text(event):
    start_time_text = event.start_time.strftime("%I:%M %p")
    if start_time_text == '12:00 PM':
        start_time_text = 'noon'

    return '{} at {}{}{}'.format(MEDIUM_PAUSE,
                                 start_time_text,
                                 SHORT_PAUSE,
                                 event.title)


class ReminderBriefingProvider(BriefingProvider):
    def __init__(self, app, briefing_config):
        super().__init__(app, briefing_config)

        self.events_fetcher = CalendarEventFetcher(
            self,
            self.cfg.value('api_base_url', None),
            self.cfg.value('api_token', None),
        )

        self.waste_collection_calendar_entity_id = self.cfg.value('waste_collection_calendar_entity_id', None)

    def can_brief(self, context):
        return True

    def briefing(self, context):
        waste_collection_event = self.events_fetcher.fetch_waste_collection_event(
            self.waste_collection_calendar_entity_id,
            datetime.today(),
        )

        self.debug('Found waste_collection_event: {}'.format(
            waste_collection_event)
        )

        if waste_collection_event is None:
            return

        return '{} is {}'.format(
            to_event_date_briefing_text(waste_collection_event),
            to_waste_collection_briefing_text(waste_collection_event)
        )


def to_event_date_briefing_text(event):
    if event.is_today:
        return 'Today'
    if event.is_tomorrow:
        return 'Tomorrow'

    return event.start_time.strftime('%A %B %d')


def to_waste_collection_briefing_text(event):
    return event.title + ' day'


class StockPriceProvider(BriefingProvider):
    def __init__(self, app, briefing_config):
        super().__init__(app, briefing_config)

        self.quote_fetcher = StockQuoteFetcher(app, self.cfg.value('api_key', None))
        self.stock_symbols = self.cfg.list('stock_symbols')
        self.workday_entity_id = self.cfg.value('workday_entity_id', None)

    def can_brief(self, context):
        return self.get_state(self.workday_entity_id) == 'on'

    def briefing(self, context):
        quotes = [self.quote_fetcher.fetch_quote(s) for s in self.stock_symbols]

        if quotes[0].is_currently_trading:
            self.debug('Now is in trading time')
            return to_stock_current_price_briefing_text(quotes)

        return to_stock_closed_price_briefing_text(quotes)


def to_stock_current_price_briefing_text(quotes):
    parts = []

    for quote in quotes:
        parts.append('{} is {} {}, to ${}'.format(
            to_stock_name(quote),
            to_stock_direction(quote),
            to_stock_change(quote),
            to_stock_price(quote),
        ))

    return 'Currently, {}{}'.format(
        SHORT_PAUSE,
        concat_list(parts, ', ' + SHORT_PAUSE))


def to_stock_closed_price_briefing_text(quotes):
    last_trading_day = quotes[0].timestamp
    delta = datetime.now() - last_trading_day
    day = None

    if delta.days == 0:
        day = 'Today'
    elif delta.days == 1:
        day = 'Yesterday'
    else:
        day = 'Last {}'.format(calendar.day_name[last_trading_day.weekday()])

    parts = []

    for quote in quotes:
        parts.append('{} was {} {}, to ${}'.format(
            to_stock_name(quote),
            to_stock_direction(quote),
            to_stock_change(quote),
            to_stock_price(quote),
        ))

    return '{}, {}{}'.format(
        day,
        SHORT_PAUSE,
        concat_list(parts, ', ' + SHORT_PAUSE))


def to_stock_name(quote):
    if quote.symbol == 'AAPL':
        return 'Apple'
    elif quote.symbol == 'TSLA':
        return 'Tesla'

    return quote.symbol


def to_stock_direction(quote):
    change = quote.change

    if change >= 0:
        return 'up'

    return 'down'


def to_stock_change(quote):
    change_percent = quote.change_percent
    change_percent = float(change_percent.replace('%', ''))
    change_percent = round(change_percent, 1)

    if change_percent >= 1 or change_percent <= -1:
        return '{}%'.format(change_percent)

    change = quote.change
    change = round(change, 2)
    return '${}'.format(change)


def to_stock_price(quote):
    price = quote.price
    price = round(price, 2)
    return price


class LowBatteryDeviceBriefingProvider(BriefingProvider):
    def __init__(self, app, briefing_config):
        super().__init__(app, briefing_config)

    def can_brief(self, context):
        return True

    def briefing(self, context):
        device_monitor = self.app.get_app('device_monitor')
        checker_result = device_monitor.get_checker_result('battery_level')

        if checker_result is None or not checker_result.has_error_device_result:
            return

        device_results = checker_result.error_device_results

        if len(device_results) == 1:
            device_result = device_results[0]
            friendly_name = self.get_state(device_result.entity_id, attribute='friendly_name')
            return '{} is running low, please change the battery soon.'.format(friendly_name)

        return 'There {} devices that are running low in battery, please change the battery soon.'.format(
            len(device_results))
