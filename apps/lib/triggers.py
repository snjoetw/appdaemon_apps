from datetime import datetime, timedelta

from lib.component import Component


def get_trigger(app, config, callback):
    platform = config["platform"]
    if platform == "state":
        return StateTrigger(app, config, callback)
    elif platform == "time":
        return TimeTrigger(app, config, callback)
    elif platform == "event":
        return EventTrigger(app, config, callback)
    elif platform == "sunrise":
        return SunriseTrigger(app, config, callback)
    elif platform == "sunset":
        return SunsetTrigger(app, config, callback)
    else:
        raise ValueError("Invalid trigger config: " + config)


class TriggerInfo:
    def __init__(self, platform, data={}):
        self._platform = platform
        self._data = data
        self._matched_constraints = []
        self._time = datetime.now()

    @property
    def platform(self):
        return self._platform

    @property
    def data(self):
        return self._data

    @property
    def matched_constraints(self):
        return self._matched_constraints

    @property
    def trigger_time(self):
        return self._time

    def __deepcopy__(self, memodict={}):
        cpyobj = type(self)(self._platform, self._data)
        cpyobj._time = self._time
        return cpyobj

    def __repr__(self):
        return "{}(platform={}, data={}, matched_constraints={})".format(
            self.__class__.__name__,
            self._platform,
            self._data,
            self._matched_constraints)


class Trigger(Component):
    def __init__(self, app, trigger_config, callback):
        super().__init__(app, trigger_config)

        self._callback = callback

        self._app.debug('Registered trigger {} with {}'.format(self,
                                                               trigger_config))


class StateTrigger(Trigger):
    def __init__(self, app, trigger_config, callback):
        super().__init__(app, trigger_config, callback)

        settings = {}

        if "from" in self._config:
            settings["old"] = self._config["from"]

        if "to" in self._config:
            settings["new"] = self._config["to"]

        if "duration" in self._config:
            settings["duration"] = self._config["duration"]

        if "immediate" in self._config:
            settings["immediate"] = self._config["immediate"]

        if "attribute" in self._config:
            settings["attribute"] = self._config["attribute"]

        entity_ids = self.list_config('entity_ids', [])
        if not entity_ids:
            entity_ids.extend(self.list_config('entity_id', []))

        for entity_id in entity_ids:
            self._app.listen_state(self._state_change_handler, entity_id, **settings)

    def _state_change_handler(self, entity_id, attribute, old, new, kwargs):
        if old == new:
            return

        self._callback(TriggerInfo("state", {
            "entity_id": entity_id,
            "attribute": attribute,
            "from": old,
            "to": new,
        }))


class TimeTrigger(Trigger):
    def __init__(self, app, trigger_config, callback):
        super().__init__(app, trigger_config, callback)

        minutes = self._config.get("minutes", 0)
        seconds = self._config.get("seconds", 0)
        interval_in_seconds = minutes * 60 + seconds
        if interval_in_seconds > 0:
            self._app.debug(
                'Scheduled time trigger to run every {} sec'.format(
                    interval_in_seconds))
            now = datetime.now() + timedelta(seconds=2)
            self._app.run_every(self._run_every_handler, now, interval_in_seconds)
        elif self._config.get("time") is not None:
            time = datetime.strptime(self._config.get("time"),
                                     '%H:%M:%S').time()
            self._app.debug('Scheduled time trigger to run at {}'.format(time))
            self._app.run_daily(self._run_every_handler, time)

    def _run_every_handler(self, time=None, **kwargs):
        self._callback(TriggerInfo("time", {
            "time": time,
        }))


class EventTrigger(Trigger):
    def __init__(self, app, trigger_config, callback):
        super().__init__(app, trigger_config, callback)

        event_type = self._config.get("event_type")
        entity_ids = self.list_config('entity_ids', [])

        if entity_ids:
            for entity_id in entity_ids:
                self._app.listen_event(self._event_change_handler,
                                       event_type,
                                       entity_id=entity_id)
        else:
            self._app.listen_event(self._event_change_handler, event_type)

    def _event_change_handler(self, event_name, data, kwargs):
        self._callback(TriggerInfo("event", {
            "event_name": event_name,
            "data": data,
        }))


class SunriseTrigger(Trigger):
    def __init__(self, app, trigger_config, callback):
        super().__init__(app, trigger_config, callback)

        offset = self._config.get("offset", 0)
        self._app.run_at_sunrise(self._run_at_sunrise_handler, offset=offset)

    def _run_at_sunrise_handler(self, kwargs):
        self._app.log(kwargs)
        self._callback(TriggerInfo("sunrise", {
        }))


class SunsetTrigger(Trigger):
    def __init__(self, app, trigger_config, callback):
        super().__init__(app, trigger_config, callback)

        offset = self._config.get("offset", 0)
        self._app.run_at_sunset(self._run_at_sunset_handler, offset=offset)

    def _run_at_sunset_handler(self, kwargs):
        self._app.log(kwargs)
        self._callback(TriggerInfo("sunset", {
        }))
