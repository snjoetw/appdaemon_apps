from lib.helper import to_int, to_float
from lib.template_renderer import TemplateRenderer


class Config:
    def __init__(self, app, config_dict):
        self._template_renderer = TemplateRenderer(app)
        self._config_dict = config_dict
        self._trigger_info = None

    @property
    def trigger_info(self):
        return self._trigger_info

    @trigger_info.setter
    def trigger_info(self, value):
        self._trigger_info = value

    def raw(self, key, default=None):
        return self._config_dict.get(key, default)

    def value(self, key, default=None):
        raw = self.raw(key)
        if raw is None:
            return default
        return self._template_renderer.render(raw, trigger_info=self._trigger_info)

    def int(self, key, default=None):
        value = self.value(key)
        return to_int(value, default)

    def float(self, key, default=None):
        value = self.value(key)
        return to_float(value, default)

    def list(self, key, default=None):
        value = self.value(key)
        if value is None:
            return default

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
