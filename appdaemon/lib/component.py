from lib.config import Config
from lib.time_wrapper import NowWrapper


class Component:
    _config: Config

    def __init__(self, app, config):
        self._app = app
        self._config = Config(app, config)

    @property
    def app(self):
        return self._app

    @property
    def cfg(self):
        return self._config

    @property
    def now(self):
        return NowWrapper(self.app)

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

    def __repr__(self):
        return "{}(config={})".format(
            self.__class__.__name__,
            self._config)
