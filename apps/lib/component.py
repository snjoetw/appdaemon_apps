from lib.helper import to_int, to_float


class Component:
    def __init__(self, app, config):
        self._app = app
        self._config = config

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

    def config(self, key, default=None):
        value = self._config.get(key, default)

        if str(value).startswith("state:"):
            value = self.get_state(value.split(':')[1])

        return value

    def int_config(self, key, default=None):
        return to_int(self.float_config(key, default))

    def float_config(self, key, default=None):
        value = self.config(key, default)
        return to_float(value, default)

    def list_config(self, key, default=None):
        value = self._config.get(key, default)

        if isinstance(value, list):
            return self._flatten_list_config(value)

        return [value]

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
        now = self._app.get_now()
        datetime = self.parse_time(time_str)
        return datetime < now

    def now_is_before(self, time_str):
        now = self._app.get_now()
        datetime = self.parse_time(time_str)
        return now < datetime

    def parse_time(self, time_str):
        time = self._app.parse_time(time_str)
        now = self._app.get_now()
        return now.replace(
            hour=time.hour,
            minute=time.minute,
            second=time.second
        )

    def __repr__(self):
        return "{}(config={})".format(
            self.__class__.__name__,
            self._config)
