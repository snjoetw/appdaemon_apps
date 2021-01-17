from datetime import datetime

from jinja2 import Environment

from lib.config import Config
from lib.helper import to_int, to_float, to_datetime, is_float, is_int


class Component:
    def __init__(self, app, config):
        self._app = app
        self._config = config
        self._config_wrapper = Config(app, config)
        self._jinja_env = Environment()

        def get_state(entity_id, overrides={}):
            state = self.get_state(entity_id)
            return overrides.get(state, state)

        def get_state_attribute(entity_id, attribute):
            return self.get_state(entity_id, attribute=attribute)

        def is_state_attribute(entity_id, attribute, expected):
            value = get_state_attribute(entity_id, attribute)

            if value is None:
                return False

            return value == expected

        def get_friendly_name(entity_id):
            return self.get_state(entity_id, attribute="friendly_name")

        def format_date(date, format='%b %d'):
            if not isinstance(date, datetime):
                date = datetime.strptime(date, '%Y-%m-%d %H:%M:%S')

            return date.strftime(format)

        def get_age(date) -> str:
            def formatn(number: int, unit: str) -> str:
                """Add "unit" if it's plural."""
                if number == 1:
                    return "1 {}".format(unit)
                return "{:d} {}s".format(number, unit)

            def q_n_r(first: int, second: int):
                """Return quotient and remaining."""
                return first // second, first % second

            if not isinstance(date, datetime):
                date = to_datetime(date).replace(tzinfo=None)

            delta = datetime.utcnow() - date
            day = delta.days
            second = delta.seconds

            year, day = q_n_r(day, 365)
            if year > 0:
                return formatn(year, "year")

            month, day = q_n_r(day, 30)
            if month > 0:
                return formatn(month, "month")
            if day > 0:
                return formatn(day, "day")

            hour, second = q_n_r(second, 3600)
            if hour > 0:
                return formatn(hour, "hour")

            minute, second = q_n_r(second, 60)
            if minute > 0:
                return formatn(minute, "minute")

            return formatn(second, "second")

        self._jinja_env.globals['state'] = get_state
        self._jinja_env.globals['state_attr'] = get_state_attribute
        self._jinja_env.globals['is_state_attr'] = is_state_attribute
        self._jinja_env.globals['friendly_name'] = get_friendly_name
        self._jinja_env.globals['format_date'] = format_date
        self._jinja_env.globals['relative_time'] = get_age

        if hasattr(self._app, 'variables'):
            for name, value in self._app.variables.items():
                if name in self._jinja_env.globals:
                    raise ValueError('Variable {} already defined in template'.format(name))

                self._jinja_env.globals[name] = value

    def render_template(self, message, **kwargs):
        if isinstance(message, str) and ("{{" in message or "{%" in message):
            template = self._jinja_env.from_string(message)
            rendered = template.render(**kwargs)

            if is_int(rendered):
                rendered = to_int(rendered)
                self.debug('Template rendered in int: {}'.format(rendered))
                return rendered
            elif is_float(rendered):
                rendered = to_float(rendered)
                self.debug('Template rendered in float: {}'.format(rendered))
                return rendered
            else:
                self.debug('Template rendered in str: {}'.format(rendered))
                return rendered

        return message

    def apply_template(self, d, **kwargs):
        applied = {}
        for k, v in d.items():
            if isinstance(v, dict):
                applied[k] = self.apply_template(v)
            else:
                applied[k] = self.render_template(v, **kwargs)

        return applied

    @property
    def app(self):
        return self._app

    def get_state(self, entity=None, **kwargs):
        return self.app.get_state(entity, **kwargs)

    def set_state(self, entity_id, **kwargs):
        self.app.set_state(entity_id, **kwargs)

    def call_service(self, service, **kwargs):
        self.app.call_service(service, **kwargs)

    def select_option(self, entity_id, option, **kwargs):
        self.app.select_option(entity_id, option, **kwargs)

    def log(self, msg, level="INFO"):
        return self._app.log(msg, level=level)

    def debug(self, msg):
        return self._app.debug(msg)

    def error(self, msg):
        return self._app.error(msg)

    @property
    def config_wrapper(self):
        return self._config_wrapper

    def cfg(self, key, default=None):
        value = self._config.get(key, default)
        return ConfigValue(self.render_template, value)

    def config(self, key, default=None):
        return self.config_wrapper.value(key, default)

    def int_config(self, key, default=None):
        return self.config_wrapper.int(key, default)

    def float_config(self, key, default=None):
        return self.config_wrapper.float(key, default)

    def list_config(self, key, default=None):
        return self.config_wrapper.list(key, default)

    def _flatten_list_config(self, config_value):
        values = []
        for value in config_value:
            if isinstance(value, list):
                values.extend(self._flatten_list_config(value))
            else:
                values.append(value)

        return values

    def now_is_between(self, start_time_str, end_time_str, name=None):
        return self._app.now_is_between(start_time_str, end_time_str, name)

    def now_is_after(self, time_str):
        now = self.get_now()
        time = self.parse_time(time_str)
        return time < now

    def now_is_before(self, time_str):
        now = self.get_now()
        time = self.parse_time(time_str)
        return now < time

    def get_now(self):
        return self._app.get_now().astimezone(self._app.AD.tz)

    def parse_time(self, time_str):
        time = self._app.parse_time(time_str)
        now = self.get_now()
        return now.replace(
            hour=time.hour,
            minute=time.minute,
            second=time.second
        )

    def __repr__(self):
        return "{}(config={})".format(
            self.__class__.__name__,
            self._config)


class ConfigValue:
    def __init__(self, template_renderer, raw_value):
        self._template_renderer = template_renderer
        self._raw_value = raw_value

    def raw(self):
        return self._raw_value

    def value(self, default=None):
        raw = self.raw()
        if raw is None:
            return default
        return self._template_renderer(raw)

    def int(self, default=None):
        value = self.value()
        return to_int(value, default)

    def float(self, default=None):
        value = self.value()
        return to_float(value, default)

    def list(self, default=None):
        value = self.value()
        if value is None:
            return default
        if isinstance(value, list):
            return self._flatten_list_config(value)
        return [value]

    def template(self, **kwargs):
        raw = self.raw()
        return self._template_renderer(raw, **kwargs)

    def _flatten_list_config(self, config_value):
        values = []
        for value in config_value:
            if isinstance(value, list):
                values.extend(self._flatten_list_config(value))
            else:
                values.append(value)

        return values
