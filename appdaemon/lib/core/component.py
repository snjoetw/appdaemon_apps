from base_automation import BaseAutomation
from lib.core.app_accessible import AppAccessible
from lib.core.config import Config
from lib.time_wrapper import NowWrapper


class Component(AppAccessible):
    _app: BaseAutomation
    _config: Config

    def __init__(self, app, config):
        super().__init__(app)
        self._config = Config(app, config)

    @property
    def cfg(self):
        return self._config

    @property
    def now(self):
        return NowWrapper(self.app)

    def __repr__(self):
        return "{}(config={})".format(
            self.__class__.__name__,
            self._config)
