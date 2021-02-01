from lib.config import Config


class Component:
    def __init__(self, app, config):
        self._app = app
        self._config_wrapper = Config(app, config)

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
        return self.app.log(msg, level=level)

    def debug(self, msg):
        return self.app.debug(msg)

    def error(self, msg):
        return self.app.error(msg)

    @property
    def config_wrapper(self):
        return self._config_wrapper

    def now_is_between(self, start_time_str, end_time_str, name=None):
        return self.app.now_is_between(start_time_str, end_time_str, name)

    def now_is_after(self, time_str):
        now = self.get_now()
        time = self.parse_time(time_str)
        return time < now

    def now_is_before(self, time_str):
        now = self.get_now()
        time = self.parse_time(time_str)
        return now < time

    def get_now(self):
        return self.app.get_now().astimezone(self.app.AD.tz)

    def parse_time(self, time_str):
        time = self.app.parse_time(time_str)
        now = self.get_now()
        return now.replace(
            hour=time.hour,
            minute=time.minute,
            second=time.second
        )

    def __repr__(self):
        return "{}(config={})".format(
            self.__class__.__name__,
            self._config_wrapper)
