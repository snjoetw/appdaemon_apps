import random
import time
from datetime import timedelta, datetime

from lib.component import Component
from lib.constraints import get_constraint
from lib.helper import to_float, to_int, list_value
from lib.schedule_job import cancel_job, schedule_job, schedule_repeat_job


def get_action(app, config):
    platform = config["platform"]
    if platform == "turn_on":
        return TurnOnAction(app, config)
    elif platform == "turn_off":
        return TurnOffAction(app, config)
    elif platform == "toggle":
        return ToggleAction(app, config)
    elif platform == "lock":
        return LockAction(app, config)
    elif platform == "unlock":
        return UnlockAction(app, config)
    elif platform == "turn_off_media_player":
        return TurnOffMediaPLayerAction(app, config)
    elif platform == "turn_on_media_player":
        return PlayMediaPlayerAction(app, config)
    elif platform == "select_input_select_option":
        return SelectInputSelectOptionAction(app, config)
    elif platform == "add_input_select_option":
        return AddInputSelectOptionAction(app, config)
    elif platform == "remove_input_select_option":
        return RemoveInputSelectOptionAction(app, config)
    elif platform == "set_input_select_options":
        return SetInputSelectOptionsAction(app, config)
    elif platform == "set_value":
        return SetValueAction(app, config)
    elif platform == "cancel_job":
        return CancelJobAction(app, config)
    elif platform == "notify":
        return NotifyAction(app, config)
    elif platform == "service":
        return ServiceAction(app, config)
    elif platform == "set_fan_min_on_time":
        return SetFanMinOnTimeAction(app, config)
    elif platform == "sonos":
        return AnnouncementAction(app, config)
    elif platform == "adjust_heating_vent":
        return AdjustHeatingVentAction(app, config)
    elif platform == "debug":
        return DebugAction(app, config)
    elif platform == "motion_announcer":
        return MotionAnnouncementAction(app, config)
    elif platform == "persistent_notification":
        return PersistentNotificationAction(app, config)
    elif platform == "increment_input_number":
        return IncrementInputNumberAction(app, config)
    elif platform == "alarm_notifier":
        return AlarmNotifierAction(app, config)
    elif platform == "set_cover_position":
        return SetCoverPositionAction(app, config)
    elif platform == "camera_snapshot":
        return CameraSnapshotAction(app, config)
    elif platform == "stepped_brightness":
        return SteppedBrightnessAction(app, config)
    elif platform == "repeat":
        return RepeatActionWrapper(app, config)
    elif platform == "delay":
        return DelayActionWrapper(app, config)
    elif platform == "set_state":
        return SetStateAction(app, config)
    elif platform == "hue_activate_scene":
        return HueActivateScene(app, config)
    else:
        raise ValueError("Invalid action config: {}".format(config))


DEFAULT_BRIGHTNESS = 255
DEFAULT_TRANSITION_TIME = 2
DEFAULT_DIMMED_BRIGHTNESS = 80
DEFAULT_DIMMED_DURATION = 10


def turn_on_entity(app, entity_id, config={}):
    entity_type, entity_name = entity_id.split(".")
    attributes = {}

    if entity_type == "light" or entity_type == "group":
        brightness = config.get("brightness", DEFAULT_BRIGHTNESS)
        full_transition_time = config.get("transition", DEFAULT_TRANSITION_TIME)

        attributes["brightness"] = brightness
        attributes["transition"] = figure_transition_time(app, entity_id, brightness, full_transition_time)

        if "rgb_color" in config:
            attributes["rgb_color"] = config.get("rgb_color")

    app.log("Turning on {} with {}".format(entity_id, attributes))
    app.turn_on(entity_id, **attributes)


def turn_off_entity(app, entity_id, config={}):
    app.debug("About to turn off {} with {}".format(entity_id, config))

    entity_type, entity_name = entity_id.split(".")
    attributes = {}

    if entity_type == "light" or entity_type == "group":
        full_transition_time = config.get("transition", DEFAULT_TRANSITION_TIME)
        attributes["transition"] = figure_transition_time(app, entity_id, 0, full_transition_time)

    app.log("Turning off {} with {}".format(entity_id, attributes))
    app.turn_off(entity_id, **attributes)


def toggle_entity(app, entity_id, config={}):
    entity_type, entity_name = entity_id.split(".")
    attributes = {}

    if entity_type == "light" or entity_type == "group":
        attributes["transition"] = config.get("transition", DEFAULT_TRANSITION_TIME)

    app.log("Toggling on {} with {}".format(entity_id, attributes))
    app.toggle(entity_id, **attributes)


def figure_transition_time(app, entity_id, target_brightness, full_transition_time):
    current_brightness = app.get_state(entity_id, attribute='brightness')
    if current_brightness is None:
        current_brightness = 0

    if current_brightness == target_brightness:
        return 0

    difference = abs(target_brightness - current_brightness)
    return round(difference / 255 * full_transition_time, 1)


def notify(app, target, message, recipient_target=None, data={}):
    app.log("Notifying {} with {}".format(target, message))
    app.call_service("notify/" + target, message=message, target=recipient_target, data=data)


def set_cover_position(app, entity_id, position, difference_threshold=0):
    if app.get_state(entity_id) == 'closed' and position > 0:
        app.call_service("cover/open_cover", entity_id=entity_id)

    current_position = app.get_state(entity_id, attribute='current_position')

    if current_position is None:
        app.warn('Unable to get current position for {}'.format(entity_id))
        # force update by making sure the diffrence will be more than threshold
        current_position = difference_threshold * -1 + 1

    position_difference = abs(current_position - position)

    if position_difference < difference_threshold:
        app.debug('Skipping {}... '
                  'current_position={}, '
                  'new_position={}, '
                  'difference_threshold={}'.format(entity_id,
                                                   current_position,
                                                   position,
                                                   difference_threshold))
        return

    app.log('Updating {} with position={} (from position={})'.format(entity_id, position, current_position))

    if position == 0:
        app.call_service("cover/close_cover", entity_id=entity_id)
        return

    app.call_service("cover/set_cover_position", entity_id=entity_id, position=position)


class Action(Component):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

        self._constraints = [get_constraint(app, c) for c in self.list_config('constraints', [])]

    def check_action_constraints(self, trigger_info):
        if not self._constraints:
            return True

        for constraint in self._constraints:
            if not constraint.check(trigger_info):
                self._app.debug('Action constraint does not match {}'.format(constraint))
                return False

            trigger_info.matched_constraints.append(constraint)

        self._app.debug('All action constraints passed')
        return True

    def do_action(self, trigger_info):
        raise NotImplementedError()


class DelayableAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

        self.delay = self.config("delay", 0)

    def do_action(self, trigger_info):
        delay = self.get_delay()

        self.debug({
            'trigger_info': trigger_info,
            'delay': delay,
            'action': self,
        })

        if delay > 0:
            self.schedule_job(delay, trigger_info=trigger_info)
            return

        cancel_job(self._app, trigger_info)
        self.job_runner({
            'trigger_info': trigger_info
        })

    def get_delay(self):
        return self.delay

    def schedule_job(self, delay, trigger_info):
        schedule_job(self._app, self.job_runner, delay, trigger_info=trigger_info)

    def job_runner(self, kwargs={}):
        raise NotImplementedError()


class RepeatableAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

        self.repeat = self.config("repeat", 0)
        self.delay = self.config("delay", self.repeat)

    def do_action(self, trigger_info):
        self.debug({
            'trigger_info': trigger_info,
            'repeat': self.repeat
        })

        if self.repeat > 0:
            start_at = datetime.now() + timedelta(seconds=self.delay)
            schedule_repeat_job(self._app, self.job_runner, start_at,
                                self.repeat, trigger_info=trigger_info)
            return

        cancel_job(self._app, trigger_info)
        self.job_runner({
            'trigger_info': trigger_info
        })

    def job_runner(self, kwargs={}):
        raise NotImplementedError()


class NotifiableAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)
        self.notify_target = self.config("notify_target")
        self.notify_message = self.config("notify_message")

    def do_action(self, trigger_info):
        if self.notify_target and self.notify_message:
            notify(self._app, self.notify_target, self.notify_message)


def figure_light_settings(entity_ids):
    if entity_ids is None:
        return {}

    if isinstance(entity_ids, dict):
        return entity_ids

    if isinstance(entity_ids, str):
        entity_ids = [entity_ids]

    if not isinstance(entity_ids, list):
        raise TypeError('entity_ids can only be str, dict or list: {}'.format(type(entity_ids)))
    else:
        entity_ids = list_value(entity_ids)

    settings = {}
    for entity_id in entity_ids:
        if isinstance(entity_id, str):
            settings[entity_id] = {
                'force_on': False,
                'force_off': False,
            }
        elif isinstance(entity_id, dict):
            setting = entity_id
            entity_id = setting['entity_id']
            settings[entity_id] = setting
        else:
            raise TypeError('item in entity_ids can only be dict or str')

    return settings


class TurnOnAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

        self.entity_ids = figure_light_settings(self.config('entity_ids'))

    def do_action(self, trigger_info):
        cancel_job(self._app, trigger_info)

        self.debug('About to run TurnOnAction: {}'.format(self.entity_ids))

        for entity_id, config in self.entity_ids.items():
            config = config or {}
            should_turn_on = self.should_turn_on(entity_id, config)

            self.debug({
                'entity_id': entity_id,
                'config': config,
                'should_turn_on': should_turn_on,
                'trigger_info': trigger_info,
            })

            if should_turn_on:
                turn_on_entity(self._app, entity_id, config)

    def should_turn_on(self, entity_id, config):
        if config.get("force_on", True):
            self.debug('force_on=True')
            return True

        current_state = self.get_state(entity_id)

        if current_state != "on":
            return True

        if "brightness" not in config:
            return False

        current_brightness = to_int(self.get_state(entity_id, attribute="brightness"), 0)
        brightness = to_int(config["brightness"])

        self.debug({
            'current_brightness': current_brightness,
            'brightness': brightness,
        })

        return current_brightness != brightness


class TurnOffAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

        self.entity_ids = figure_light_settings(self.config('entity_ids'))

    def do_action(self, trigger_info):
        if self.should_dim_lights():
            self.dim_lights()

            schedule_job(self.app, self.turn_off_lights_job_runner, DEFAULT_DIMMED_DURATION, trigger_info=trigger_info)
            return

        self.turn_off_lights_job_runner({
            'trigger_info': trigger_info
        })

    def turn_off_lights_job_runner(self, kwargs={}):
        trigger_info = kwargs.get('trigger_info')
        self.debug('About to run TurnOffAction: {}'.format(self.entity_ids))

        for entity_id, config in self.entity_ids.items():
            config = config or {}
            force_off = config.get("force_off", True)

            self.debug({
                'entity_id': entity_id,
                'config': config,
                'trigger_info': trigger_info,
            })

            if self.get_state(entity_id) == "on" or force_off:
                turn_off_entity(self._app, entity_id, config)

    def should_dim_lights(self):
        if not self.config('dim_light_before_turn_off', True):
            return False

        for entity_id in self.entity_ids.keys():
            if entity_id.startswith('light'):
                return True

        return False

    def dim_lights(self):
        for entity_id in self.entity_ids.keys():
            entity = self.get_state(entity_id, attribute='all')

            if entity is None:
                self.error('Unable to find entity: {}'.format(entity_id))
                continue

            if entity.get('state') != 'on':
                continue

            brightness = entity.get('attributes', {}).get('brightness')
            if not brightness or brightness <= DEFAULT_DIMMED_BRIGHTNESS:
                continue

            turn_on_entity(self._app, entity_id, {
                'brightness': DEFAULT_DIMMED_BRIGHTNESS
            })


class SteppedBrightnessAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

        self.entity_ids = self.list_config('entity_id')
        self.step = self.int_config('step')

    def do_action(self, trigger_info):
        for entity_id in self.entity_ids:
            brightness = self.get_state(entity_id, attribute='brightness')
            if not brightness:
                brightness = 0
            brightness += self.step

            if brightness > 255:
                brightness = 255
            elif brightness < 0:
                brightness = 0

            turn_on_entity(self._app, entity_id, {
                'brightness': brightness
            })


class ToggleAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

        self.entity_id = self._config["entity_id"]

    def do_action(self, trigger_info):
        toggle_entity(self._app, self.entity_id)


class SetCoverPositionAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

        self.entity_ids = self.list_config("entity_id", [])
        self.position = self._config["position"]
        self.position_difference_threshold = self._config.get(
            "position_difference_threshold", 3)

    def do_action(self, trigger_info):
        for entity_id in self.entity_ids:
            set_cover_position(self._app,
                               entity_id,
                               self.position,
                               self.position_difference_threshold)


class LockAction(NotifiableAction):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

        self.entity_id = self.config("entity_id")
        self.force_lock = self.config("force_lock", False)

    def do_action(self, trigger_info):
        if self.get_state(self.entity_id) == 'locked' and not self.force_lock:
            return

        self.call_service("lock/lock", entity_id=self.entity_id)

        super().do_action(trigger_info)


class UnlockAction(NotifiableAction):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

        self.entity_id = self.config("entity_id")

    def do_action(self, trigger_info):
        self.call_service("lock/unlock", entity_id=self.entity_id)

        super().do_action(trigger_info)


class TurnOffMediaPLayerAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

        self.entity_ids = self.list_config('entity_id', [])

    def do_action(self, trigger_info):
        self.log("Turning off {}".format(self.entity_ids))
        self.call_service("media_player/turn_off", entity_id=self.entity_ids)


class PlayMediaPlayerAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

        self.entity_ids = self.list_config('entity_id', [])
        self.volume = self._config.get("volume")
        self.source = self._config.get("source")
        self.shuffle = self._config.get("shuffle", False)

    def do_action(self, trigger_info):
        self.log("Turning on {}".format(self.entity_ids))
        self.call_service("media_player/turn_on",
                          entity_id=self.entity_ids)

        if self.volume is not None:
            self.call_service("media_player/volume_set",
                              entity_id=self.entity_ids,
                              volume_level=self.volume)

        if self.source is not None:
            self.call_service("media_player/select_source",
                              entity_id=self.entity_ids,
                              source=self.source)

        if self.shuffle:
            self.call_service("media_player/shuffle_set",
                              entity_id=self.entity_ids,
                              shuffle=self.shuffle)


class SelectInputSelectOptionAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

        self.entity_id = self._config["entity_id"]
        self.option = self._config["option"]

    def do_action(self, trigger_info):
        current_option = self.get_state(self.entity_id)
        if current_option != self.option:
            self.log("Updating {} to {}".format(self.entity_id,
                                                self.option))
            self.select_option(self.entity_id, self.option)


class AddInputSelectOptionAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

        self.entity_id = self._config["entity_id"]
        self.option = self._config["option"]

    def do_action(self, trigger_info):
        option = self.render_template(self.option,
                                      trigger_info=trigger_info)
        options = self.get_state(self.entity_id,
                                 attribute='options')

        if option not in options:
            options.append(option)
            self.log("Updating {} options to {}".format(self.entity_id,
                                                        options))
            self.call_service("input_select/set_options", **{
                'entity_id': self.entity_id,
                'options': options
            })
            self.select_option(self.entity_id, option)


class RemoveInputSelectOptionAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

        self.entity_id = self._config["entity_id"]
        self.option = self._config["option"]

    def do_action(self, trigger_info):
        option = self.render_template(self.option,
                                      trigger_info=trigger_info)
        options = self.get_state(self.entity_id,
                                 attribute='options')

        if option in options:
            options.remove(option)
            self.log("Updating {} options to {}".format(self.entity_id,
                                                        options))
            self.call_service("input_select/set_options", **{
                'entity_id': self.entity_id,
                'options': options
            })
            self.select_option(self.entity_id, options[-1])


class SetInputSelectOptionsAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

        self.entity_id = self._config["entity_id"]
        self.options = self._config["options"]

    def do_action(self, trigger_info):
        self.log("Setting {} options to {}".format(self.entity_id,
                                                   self.options))

        self.call_service("input_select/set_options", **{
            'entity_id': self.entity_id,
            'options': self.options
        })

        self.select_option(self.entity_id, self.options[-1])


class SetValueAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

        self.entity_id = self._config["entity_id"]
        self.value = self._config["value"]

    def do_action(self, trigger_info):
        current_value = self.get_state(self.entity_id)
        new_value = self.render_template(self.value, trigger_info=trigger_info)

        if current_value != new_value:
            self.log("Updating {} to {}".format(self.entity_id,
                                                new_value))
            # self._app.set_value(self.entity_id, new_value)
            data = {
                'entity_id': self.entity_id,
                'value': new_value
            }
            self.call_service("input_text/set_value", **data)


class NotifyAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

        self.target = self._config["target"]
        self.message = self._config["message"]
        self.recipient_target = self._config.get("recipient_target")
        self.data = self._config.get("data") or {}

    def do_action(self, trigger_info):
        message = self.render_template(self.message, trigger_info=trigger_info)
        notify(self._app, self.target, message, self.recipient_target,
               self.data)


class CancelJobAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)
        self.cancel_all = self._config.get('cancel_all', False)

    def do_action(self, trigger_info):
        if self.cancel_all:
            cancel_job(self._app)
        else:
            cancel_job(self._app, trigger_info)


class PersistentNotificationAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

        self.data = self._config.get("data", {})

    def do_action(self, trigger_info):
        data = self.apply_template(self.data, trigger_info=trigger_info)
        data['notification_id'] = "pn_{}".format(time.time())

        self.log(
            "Calling service persistent_notification/create with {}".format(
                data))
        self.call_service("persistent_notification/create", **data)


class ServiceAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

        self.service = self._config["service"]
        self.data = self._config.get("data", {})

    def do_action(self, trigger_info):
        data = self.apply_template(self.data, trigger_info=trigger_info)

        self.call_service(self.service, **data)


class SetFanMinOnTimeAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

        self.entity_id = self._config['entity_id']
        self.fan_min_on_time = self._config['fan_min_on_time']

    def do_action(self, trigger_info):
        current_fan_min_on_time = self.get_state(self.entity_id, attribute='fan_min_on_time')

        if current_fan_min_on_time == self.fan_min_on_time:
            self.debug('Skipping set_fan_min_on_time')
            return

        self.call_service('ecobee/set_fan_min_on_time',
                          entity_id=self.entity_id,
                          fan_min_on_time=self.fan_min_on_time)


class AnnouncementAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

        self.message = self._config["tts_message"]
        self.player_entity_id = self.list_config('player_entity_id', [])
        self.use_cache = self.config('use_cache', True)
        self.prelude_name = self.config('prelude_name')

    def do_action(self, trigger_info):
        announcer = self._app.get_app('sonos_announcer')
        message = self.render_template(self.message, trigger_info=trigger_info)

        self.call_service("notify/all_ios", message=message)

        announcer.announce(message,
                           use_cache=self.use_cache,
                           player_entity_ids=self.player_entity_id,
                           prelude_name=self.prelude_name)


class MotionAnnouncementAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

        self.message_entity_id = self._config["message_entity_id"]
        self.message_from_entity_id = self._config["message_from_entity_id"]

    def do_action(self, trigger_info):
        triggered_entity_id = trigger_info.data.get('entity_id')
        message = self.get_state(self.message_entity_id)
        message_from = self.get_state(self.message_from_entity_id)

        if not triggered_entity_id or not message or not message_from:
            return

        message = 'Incoming message from {}: {}'.format(message_from, message)

        self.log('Announcing motion message: {}'.format(message))

        announcer = self._app.get_app('sonos_announcer')
        announcer.announce(message, use_cache=False,
                           motion_entity_id=triggered_entity_id)


class AdjustHeatingVentAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

        self.climate_entity_id = self._config["climate_entity_id"]
        self.temp_entity_id = self._config["temperature_entity_id"]
        self.vent_entity_ids = self.list_config("vent_entity_id")

        self.target_offset_high = self._config.get("target_offset_high", 0.1)
        self.target_offset_low = self._config.get("target_offset_low", -0.3)
        self.target_offset_scale = 1 / (
                self.target_offset_high - self.target_offset_low)

        self.min_open_percent = self._config.get("min_open_percent", 0.0)
        self.position_difference_threshold = self._config.get(
            "position_difference_threshold", 3)

    def do_action(self, trigger_info):
        current = to_float(self.get_state(self.temp_entity_id))
        target = self.target_temperature()
        adjusted_current = self.adjusted_current_temperature(target, current)
        open_percent = self.calculate_open_percent(target, adjusted_current)
        open_position = round(open_percent * 100)

        for vent_entity_id in self.vent_entity_ids:
            set_cover_position(self._app,
                               vent_entity_id,
                               open_position,
                               self.position_difference_threshold)

    def is_heating_mode(self):
        hvac_action = self.get_state(self.climate_entity_id,
                                     attribute='hvac_action')
        return hvac_action == "heating"

    def calculate_open_percent(self, target, adjusted_current):
        is_heating_mode = self.is_heating_mode()
        if is_heating_mode:
            target_high = target + self.target_offset_high
            open_percent = round((target_high - adjusted_current) * self.target_offset_scale, 1)
        else:
            target_low = target + self.target_offset_low
            open_percent = round((adjusted_current - target_low) * self.target_offset_scale, 1)

        if open_percent < self.min_open_percent:
            open_percent = self.min_open_percent

        self.debug(
            'calculate_open_percent: temp_entity_id={}, is_heating_mode={}, target_temp={}, adjusted_current={}, '
            'open_percent={}'.format(self.temp_entity_id,
                                     is_heating_mode,
                                     target,
                                     adjusted_current,
                                     open_percent,
                                     ))

        return open_percent

    def target_temperature(self):
        target = self.get_state(self.climate_entity_id,
                                attribute='temperature')

        if target is None:
            if self.is_heating_mode():
                target = self.get_state(self.climate_entity_id,
                                        attribute="target_temp_low")
            else:
                target = self.get_state(self.climate_entity_id,
                                        attribute="target_temp_high")

        return to_float(target)

    def adjusted_current_temperature(self, target, current):
        if current > target + self.target_offset_high:
            current = target + self.target_offset_high
        elif current < target + self.target_offset_low:
            current = target + self.target_offset_low

        return current


class DebugAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

    def do_action(self, trigger_info):
        template_value = self.render_template(self._config.get('template'))
        self.log("Debugging, trigger_info={}, template_value={}".format(trigger_info, template_value))


class IncrementInputNumberAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)
        self.entity_id = self._config["entity_id"]
        self.step = self._config["step"]
        self.step_entity_id = self._config.get("step_entity_id")

    def do_action(self, trigger_info):
        step = self.render_template(self.step,
                                    trigger_info=trigger_info)

        value = to_float(self.get_state(self.entity_id), 0)
        value += to_float(step)

        self.log("Updating {} to {}".format(self.entity_id, value))
        self.call_service("input_number/set_value",
                          entity_id=self.entity_id, value=value)


class AlarmNotifierAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

        self.message = self._config["message"]
        self.image_filename = self._config.get("image_filename")
        self.trigger_entity_id = self._config.get("trigger_entity_id")
        self.messenger_types = self._config.get("messenger_types", ())

    def do_action(self, trigger_info):
        notifier = self._app.get_app('alarm_notifier')
        trigger_entity_id = self.render_template(self.trigger_entity_id,
                                                 trigger_info=trigger_info)
        message = self.render_template(self.message, trigger_info=trigger_info)
        self.log("Notifying with message={} trigger_entity_id={}".format(
            message, trigger_entity_id))
        notifier.send(message, trigger_entity_id, self.messenger_types,
                      self.image_filename)


class CameraSnapshotAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

        self.entity_id = self.config("entity_id")

    def do_action(self, trigger_info):
        filename = self.cfg("filename").template(trigger_info=trigger_info)
        if not filename.startswith('/'):
            filename = '/config/www/snapshot/{}'.format(filename)

        data = {
            'entity_id': self.entity_id,
            'filename': filename
        }

        self.log('Adding snapshot with {}'.format(data))

        self.call_service('camera/snapshot', **data)


class RepeatActionWrapper(RepeatableAction):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

        self.actions = []

        for config in self.list_config('actions'):
            self.actions.append(get_action(app, config))

    def job_runner(self, kwargs={}):
        trigger_info = kwargs.get('trigger_info')

        for action in self.actions:
            action.do_action(trigger_info)


class DelayActionWrapper(DelayableAction):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

        self.actions = []

        for config in self.list_config('actions'):
            self.actions.append(get_action(app, config))

    def job_runner(self, kwargs={}):
        self.debug('About to run delayed job, trigger_info={}'.format(kwargs))
        trigger_info = kwargs.get('trigger_info')

        self.debug('About to run delayed job, trigger_info={}'.format(trigger_info))

        for action in self.actions:
            action.do_action(trigger_info)


class SetStateAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

        self.entity_ids = self.list_config('entity_id')
        self.state = self.config('state')

    def do_action(self, trigger_info):
        for entity_id in self.entity_ids:
            self.set_state(entity_id, state=self.state)


class HueActivateScene(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

        self.entity_ids = self.list_config('entity_id')
        self.scene_names = self.list_config('scene_name')

    def do_action(self, trigger_info):
        scene_name = self.figure_scene_name()
        for entity_id in self.entity_ids:
            group_name = self.get_state(entity_id, attribute='friendly_name')

            self.call_service('hue/hue_activate_scene',
                              group_name=group_name,
                              scene_name=scene_name)

    def figure_scene_name(self):
        return random.choice(self.scene_names)
