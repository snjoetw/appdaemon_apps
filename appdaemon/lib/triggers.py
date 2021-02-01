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
    elif platform == "action":
        return ActionTrigger(app, config, callback)
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
        self._time = datetime.now()

    @property
    def platform(self):
        return self._platform

    @property
    def data(self):
        return self._data

    @property
    def trigger_time(self):
        return self._time

    def __deepcopy__(self, memodict={}):
        cpyobj = type(self)(self._platform, self._data)
        cpyobj._time = self._time
        return cpyobj

    def __repr__(self):
        return "{}(platform={}, data={})".format(
            self.__class__.__name__,
            self._platform,
            self._data)


class Trigger(Component):
    def __init__(self, app, trigger_config, callback):
        super().__init__(app, trigger_config)

        self._callback = callback

        self.app.debug('Registered trigger {} with {}'.format(self, trigger_config))


class StateTrigger(Trigger):
    def __init__(self, app, trigger_config, callback):
        super().__init__(app, trigger_config, callback)

        settings = {}

        from_state = self.config_wrapper.value("from", None)
        if from_state is not None:
            settings["old"] = from_state

        to_state = self.config_wrapper.value("to", None)
        if to_state is not None:
            settings["new"] = to_state

        duration = self.config_wrapper.value("duration", None)
        if duration is not None:
            settings["duration"] = duration

        immediate = self.config_wrapper.value("immediate", None)
        if immediate is not None:
            settings["immediate"] = immediate

        attribute = self.config_wrapper.value("attribute", None)
        if attribute is not None:
            settings["attribute"] = attribute

        entity_ids = self.config_wrapper.list('entity_ids', [])
        if not entity_ids:
            entity_ids.extend(self.config_wrapper.list('entity_id', []))

        for entity_id in entity_ids:
            self.app.listen_state(self._state_change_handler, entity_id, **settings)

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

        minutes = self.config_wrapper.value("minutes", 0)
        seconds = self.config_wrapper.value("seconds", 0)
        interval_in_seconds = minutes * 60 + seconds
        if interval_in_seconds > 0:
            self.app.debug('Scheduled time trigger to run every {} sec'.format(interval_in_seconds))
            now = datetime.now() + timedelta(seconds=2)
            self.app.run_every(self._run_every_handler, now, interval_in_seconds)
        elif self.config_wrapper.value("time", None) is not None:
            time = datetime.strptime(self.config_wrapper.value("time", None), '%H:%M:%S').time()
            self.app.debug('Scheduled time trigger to run at {}'.format(time))
            self.app.run_daily(self._run_every_handler, time)

    def _run_every_handler(self, time=None, **kwargs):
        self._callback(TriggerInfo("time", {
            "time": time,
        }))


class EventTrigger(Trigger):
    def __init__(self, app, trigger_config, callback):
        super().__init__(app, trigger_config, callback)

        default = {}
        self._event_data = self.config_wrapper.value("event_data", default)

        event_type = self.config_wrapper.value("event_type", None)
        entity_ids = self.config_wrapper.list('entity_ids', [])

        if entity_ids:
            for entity_id in entity_ids:
                self.app.listen_event(self._event_change_handler, event_type, entity_id=entity_id)
        else:
            self.app.listen_event(self._event_change_handler, event_type)

    def _event_change_handler(self, event_name, data, kwargs):
        for data_key, data_value in self._event_data.items():
            if data.get(data_key) != data_value:
                self.debug('Event data ({}) does not match constraint ({}/{} - {}), skipping'.format(
                    data,
                    data_key,
                    data_value,
                    self._event_data))
                return

        self._callback(TriggerInfo("event", {
            "event_name": event_name,
            "data": data,
        }))


class SunriseTrigger(Trigger):
    def __init__(self, app, trigger_config, callback):
        super().__init__(app, trigger_config, callback)

        offset = self.config_wrapper.value("offset", 0)
        self.app.run_at_sunrise(self._run_at_sunrise_handler, offset=offset)

    def _run_at_sunrise_handler(self, kwargs):
        self.app.log(kwargs)
        self._callback(TriggerInfo("sunrise", {
        }))


class SunsetTrigger(Trigger):
    def __init__(self, app, trigger_config, callback):
        super().__init__(app, trigger_config, callback)

        offset = self.config_wrapper.value("offset", 0)
        self.app.run_at_sunset(self._run_at_sunset_handler, offset=offset)

    def _run_at_sunset_handler(self, kwargs):
        self.app.log(kwargs)
        self._callback(TriggerInfo("sunset", {
        }))


class ActionTrigger(Trigger):
    def __init__(self, app, trigger_config, callback):
        super().__init__(app, trigger_config, callback)

        self.app.listen_event(self._event_change_handler, 'ios.action_fired')
        self._target_name = self.config_wrapper.value('action_name', None)

    def _event_change_handler(self, event_name, data, kwargs):
        action_name = data.get('actionName')
        if self._target_name is not None and self._target_name != action_name:
            return

        self._callback(TriggerInfo('action', {
            'action_name': action_name,
            'data': data,
        }))
