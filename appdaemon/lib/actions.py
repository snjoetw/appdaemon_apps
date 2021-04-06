import random
import time
from datetime import timedelta, datetime
from typing import List

from alarm_notifier import AlarmNotifier
from announcer import Announcer
from base_automation import do_action
from lib.constraints import Constraint
from lib.constraints import get_constraint
from lib.core.component import Component
from lib.helper import to_int, list_value
from lib.schedule_job import cancel_job, schedule_job, schedule_repeat_job
from notifier import Message, NotifierType, Notifier


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
        return TurnOnMediaPLayerAction(app, config)
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
    elif platform == "announcement":
        return AnnouncementAction(app, config)
    elif platform == "enable_dnd":
        return EnablePlayerDndAction(app, config)
    elif platform == "disable_dnd":
        return DisablePlayerDndAction(app, config)
    elif platform == "debug":
        return DebugAction(app, config)
    elif platform == "motion_announcer":
        return MotionAnnouncementAction(app, config)
    elif platform == "persistent_notification":
        return PersistentNotificationAction(app, config)
    elif platform == "alarm_notifier":
        return AlarmNotifierAction(app, config)
    elif platform == "set_cover_position":
        return SetCoverPositionAction(app, config)
    elif platform == "camera_snapshot":
        return CameraSnapshotAction(app, config)
    elif platform == "repeat":
        return RepeatActionWrapper(app, config)
    elif platform == "delay":
        return DelayActionWrapper(app, config)
    elif platform == "set_state":
        return SetStateAction(app, config)
    elif platform == "hue_activate_scene":
        return HueActivateScene(app, config)
    elif platform == "fire_event":
        return FireEvent(app, config)
    elif platform == "trigger_pathway_light":
        return TriggerPathwayLightAction(app, config)
    else:
        raise ValueError("Invalid action config: {}".format(config))


DEFAULT_BRIGHTNESS = 255
DEFAULT_TRANSITION_TIME = 1.5
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
        brightness = config.get("brightness", DEFAULT_BRIGHTNESS)
        full_transition_time = config.get("transition", DEFAULT_TRANSITION_TIME)

        if app.get_state(entity_id) == 'on':
            brightness = 0

        attributes["brightness"] = brightness
        attributes["transition"] = figure_transition_time(app, entity_id, brightness, full_transition_time)

        if "rgb_color" in config:
            attributes["rgb_color"] = config.get("rgb_color")

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
    _constraints: List[Constraint]

    def __init__(self, app, action_config):
        super().__init__(app, action_config)

        self._constraints = [get_constraint(app, c) for c in self.cfg.list('constraints', [])]

    def check_action_constraints(self, trigger_info):
        if not self._constraints:
            return True

        for constraint in self._constraints:
            if not constraint.check(trigger_info):
                self.app.debug('Action constraint does not match {}'.format(constraint))
                return False

        self.app.debug('All action constraints passed')
        return True

    def do_action(self, trigger_info):
        raise NotImplementedError()


class DelayableAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

    def do_action(self, trigger_info):
        delay = self.cfg.value("delay", 0)
        if delay > 0:
            self.schedule_job(delay, trigger_info=trigger_info)
            return

        cancel_job(self.app, trigger_info)
        self.job_runner({
            'trigger_info': trigger_info
        })

    def schedule_job(self, delay, trigger_info):
        schedule_job(self.app, self.job_runner, delay, trigger_info=trigger_info)

    def job_runner(self, kwargs={}):
        raise NotImplementedError()


class RepeatableAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

    def do_action(self, trigger_info):
        repeat = self.cfg.value("repeat", 0)
        delay = self.cfg.value("delay", repeat)

        if repeat > 0:
            start_at = datetime.now() + timedelta(seconds=delay)
            schedule_repeat_job(self.app, self.job_runner, start_at, repeat, trigger_info=trigger_info)
            return

        cancel_job(self.app, trigger_info)
        self.job_runner({
            'trigger_info': trigger_info
        })

    def job_runner(self, kwargs={}):
        raise NotImplementedError()


class NotifiableAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

    def do_action(self, trigger_info):
        notify_target = self.cfg.value("notify_target", None)
        notify_message = self.cfg.value("notify_message", None)

        if notify_target and notify_message:
            notify(self.app, notify_target, notify_message)


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

    def do_action(self, trigger_info):
        entity_ids = figure_light_settings(self.cfg.value('entity_ids', None))

        cancel_job(self.app, trigger_info)

        self.debug('About to run TurnOnAction: {}'.format(entity_ids))

        for entity_id, config in entity_ids.items():
            config = config or {}
            should_turn_on = self.should_turn_on(entity_id, config)

            self.debug({
                'entity_id': entity_id,
                'config': config,
                'should_turn_on': should_turn_on,
                'trigger_info': trigger_info,
            })

            if should_turn_on:
                turn_on_entity(self.app, entity_id, config)

    def should_turn_on(self, entity_id, config):
        if config.get("force_on", True):
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

    def do_action(self, trigger_info):
        entity_ids = figure_light_settings(self.cfg.value('entity_ids', None))
        if self.should_dim_lights(entity_ids):
            self.dim_lights(entity_ids)

            schedule_job(self.app, self.turn_off_lights_job_runner, DEFAULT_DIMMED_DURATION, trigger_info=trigger_info)
            return

        self.turn_off_lights_job_runner({
            'trigger_info': trigger_info
        })

    def turn_off_lights_job_runner(self, kwargs={}):
        entity_ids = figure_light_settings(self.cfg.value('entity_ids', None))
        trigger_info = kwargs.get('trigger_info')
        self.debug('About to run TurnOffAction: {}'.format(entity_ids))

        for entity_id, config in entity_ids.items():
            config = config or {}
            force_off = config.get("force_off", True)

            self.debug({
                'entity_id': entity_id,
                'config': config,
                'trigger_info': trigger_info,
            })

            if self.get_state(entity_id) == "on" or force_off:
                turn_off_entity(self.app, entity_id, config)

    def should_dim_lights(self, entity_ids):
        if not self.cfg.value('dim_light_before_turn_off', True):
            return False

        for entity_id in entity_ids.keys():
            if entity_id.startswith('light'):
                return True

        return False

    def dim_lights(self, entity_ids):
        for entity_id in entity_ids.keys():
            entity = self.get_state(entity_id, attribute='all')

            if entity is None:
                self.error('Unable to find entity: {}'.format(entity_id))
                continue

            if entity.get('state') != 'on':
                continue

            brightness = entity.get('attributes', {}).get('brightness')
            if not brightness or brightness <= DEFAULT_DIMMED_BRIGHTNESS:
                continue

            turn_on_entity(self.app, entity_id, {
                'brightness': DEFAULT_DIMMED_BRIGHTNESS
            })


class ToggleAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

    def do_action(self, trigger_info):
        entity_ids = figure_light_settings(self.cfg.value('entity_ids', None))
        for entity_id, config in entity_ids.items():
            config = config or {}

            self.debug({
                'entity_id': entity_id,
                'config': config,
                'trigger_info': trigger_info,
            })

            toggle_entity(self.app, entity_id, config)


class TriggerPathwayLightAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

    def do_action(self, trigger_info):
        app_name = self.cfg.value('app_name')
        motion_lighting_app = self.app.get_app(app_name)
        motion_lighting_app.trigger_pathway_light()


class SetCoverPositionAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

    def do_action(self, trigger_info):
        entity_ids = self.cfg.list("entity_id", [])
        position = self.cfg.value("position", None)
        position_difference_threshold = self.cfg.value("position_difference_threshold", 3)

        for entity_id in entity_ids:
            set_cover_position(self.app, entity_id, position, position_difference_threshold)


class LockAction(NotifiableAction):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

    def do_action(self, trigger_info):
        entity_id = self.cfg.value("entity_id", None)
        force_lock = self.cfg.value("force_lock", False)

        if self.get_state(entity_id) == 'locked' and not force_lock:
            return

        self.call_service("lock/lock", entity_id=entity_id)

        super().do_action(trigger_info)


class UnlockAction(NotifiableAction):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

    def do_action(self, trigger_info):
        entity_id = self.cfg.value("entity_id", None)
        self.call_service("lock/unlock", entity_id=entity_id)

        super().do_action(trigger_info)


class TurnOffMediaPLayerAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

    def do_action(self, trigger_info):
        entity_ids = self.cfg.list('entity_id', [])
        self.call_service("media_player/media_stop", entity_id=entity_ids)
        self.call_service("media_player/turn_off", entity_id=entity_ids)


class TurnOnMediaPLayerAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

    def do_action(self, trigger_info):
        entity_ids = self.cfg.list('entity_id', [])
        volume = self.cfg.value("volume", None)
        source = self.cfg.value("source", None)
        shuffle = self.cfg.value("shuffle", False)
        repeat = self.cfg.value("repeat", "all")

        self.call_service("media_player/turn_on", entity_id=entity_ids)

        if volume is not None:
            self.call_service("media_player/volume_set", entity_id=entity_ids, volume_level=volume)

        if source is not None:
            self.call_service("media_player/select_source", entity_id=entity_ids, source=source)

        if shuffle:
            self.call_service("media_player/shuffle_set", entity_id=entity_ids, shuffle=shuffle)

        self.call_service("media_player/repeat_set", entity_id=entity_ids, repeat=repeat)


class SelectInputSelectOptionAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

    def do_action(self, trigger_info):
        entity_id = self.cfg.value("entity_id", None)
        option = self.cfg.value("option", None)

        current_option = self.get_state(entity_id)
        if current_option != option:
            self.select_option(entity_id, option)


class AddInputSelectOptionAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

    def do_action(self, trigger_info):
        entity_id = self.cfg.value("entity_id")
        option = self.cfg.value("option")
        options = self.get_state(entity_id, attribute='options')

        if option not in options:
            options.append(option)
            self.call_service("input_select/set_options", **{
                'entity_id': entity_id,
                'options': options
            })
            self.select_option(entity_id, option)


class RemoveInputSelectOptionAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

    def do_action(self, trigger_info):
        entity_id = self.cfg.value("entity_id", None)
        option = self.cfg.value("option")
        options = self.get_state(entity_id, attribute='options')

        if option in options:
            options.remove(option)
            self.call_service("input_select/set_options", **{
                'entity_id': entity_id,
                'options': options
            })
            self.select_option(entity_id, options[-1])


class SetInputSelectOptionsAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

    def do_action(self, trigger_info):
        entity_id = self.cfg.value("entity_id", None)
        options = self.cfg.value("options", None)

        self.call_service("input_select/set_options", **{
            'entity_id': entity_id,
            'options': options
        })

        self.select_option(entity_id, options[-1])


class SetValueAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

    def do_action(self, trigger_info):
        entity_id = self.cfg.value("entity_id", None)
        new_value = self.cfg.value("value", None)
        current_value = self.get_state(entity_id)

        if current_value != new_value:
            data = {
                'entity_id': entity_id,
                'value': new_value
            }
            self.call_service("input_text/set_value", **data)


class NotifyAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

    def do_action(self, trigger_info):
        title = self.cfg.value("title", None)
        message = self.cfg.value("message", None)
        notifier_types = [NotifierType(n) for n in self.cfg.list('notifier')]
        recipients = self.cfg.list('recipient')
        camera_entity_id = self.cfg.value('camera_entity_id', None)

        notifier: Notifier = self.app.get_app('notifier')
        notifier.notify(Message(notifier_types, recipients, title, message, camera_entity_id, {
            NotifierType.IOS.value: self.cfg.value(NotifierType.IOS.value, {})
        }))


class AlarmNotifierAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

    def do_action(self, trigger_info):
        title = self.cfg.value("title", None)
        message = self.cfg.value("message", None)
        image_filename = self.cfg.value("image_filename", None)
        trigger_entity_id = self.cfg.value("trigger_entity_id", None)
        notifier_types = [NotifierType(n) for n in self.cfg.list('notifier', [])]

        notifier: AlarmNotifier = self.app.get_app('alarm_notifier')
        notifier.notify(notifier_types, title, message, trigger_entity_id, image_filename, {
            NotifierType.IOS.value: self.cfg.value(NotifierType.IOS.value, {})
        })


class CancelJobAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

    def do_action(self, trigger_info):
        cancel_all = self.cfg.value('cancel_all', False)

        if cancel_all:
            cancel_job(self.app)
        else:
            cancel_job(self.app, trigger_info)


class PersistentNotificationAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

    def do_action(self, trigger_info):
        default = {}
        data = self.cfg.value("data", default)
        data['notification_id'] = "pn_{}".format(time.time())

        self.call_service("persistent_notification/create", **data)


class ServiceAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

    def do_action(self, trigger_info):
        service = self.cfg.value("service", None)
        default = {}
        data = self.cfg.value("data", default)

        self.call_service(service, **data)


class SetFanMinOnTimeAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

    def do_action(self, trigger_info):
        entity_id = self.cfg.value('entity_id', None)
        fan_min_on_time = self.cfg.value('fan_min_on_time', None)

        current_fan_min_on_time = self.get_state(entity_id, attribute='fan_min_on_time')

        if current_fan_min_on_time == fan_min_on_time:
            self.debug('Skipping set_fan_min_on_time')
            return

        self.call_service('ecobee/set_fan_min_on_time', entity_id=entity_id, fan_min_on_time=fan_min_on_time)


class AnnouncementAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

    def do_action(self, trigger_info):
        message = self.cfg.value("tts_message", None)
        player_entity_id = self.cfg.list('player_entity_id', [])
        use_cache = self.cfg.value('use_cache', True)
        prelude_name = self.cfg.value('prelude_name', None)

        announcer: Announcer = self.app.get_app('announcer')
        announcer.announce(message, use_cache=use_cache, player_entity_ids=player_entity_id, prelude_name=prelude_name)


class EnablePlayerDndAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

    def do_action(self, trigger_info):
        player_entity_ids = self.cfg.list('player_entity_id', [])
        announcer: Announcer = self.app.get_app('announcer')
        for player_entity_id in player_entity_ids:
            announcer.enable_do_not_disturb(player_entity_id)


class DisablePlayerDndAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

    def do_action(self, trigger_info):
        player_entity_ids = self.cfg.list('player_entity_id', [])
        announcer: Announcer = self.app.get_app('announcer')
        for player_entity_id in player_entity_ids:
            announcer.disable_do_not_disturb(player_entity_id)


class MotionAnnouncementAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

    def do_action(self, trigger_info):
        message_entity_id = self.cfg.value("message_entity_id", None)
        message_from_entity_id = self.cfg.value("message_from_entity_id", None)

        triggered_entity_id = trigger_info.data.get('entity_id')
        message = self.get_state(message_entity_id)
        message_from = self.get_state(message_from_entity_id)

        if not triggered_entity_id or not message or not message_from:
            return

        message = 'Incoming message from {}: {}'.format(message_from, message)

        announcer: Announcer = self.app.get_app('announcer')
        announcer.announce(message, use_cache=False, motion_entity_id=triggered_entity_id)


class DebugAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

    def do_action(self, trigger_info):
        template_value = self.cfg.value('template', None)
        self.log("Debugging, trigger_info={}, template_value={}".format(trigger_info, template_value))


class CameraSnapshotAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

    def do_action(self, trigger_info):
        entity_id = self.cfg.value("entity_id", None)
        filename = self.cfg.value("filename", None)
        if not filename.startswith('/'):
            filename = '/config/www/snapshot/{}'.format(filename)

        data = {
            'entity_id': entity_id,
            'filename': filename
        }

        self.call_service('camera/snapshot', **data)


class RepeatActionWrapper(RepeatableAction):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

        self.actions = []

        for config in self.cfg.list('actions'):
            self.actions.append(get_action(app, config))

    def job_runner(self, kwargs={}):
        trigger_info = kwargs.get('trigger_info')

        for action in self.actions:
            do_action(action, trigger_info)


class DelayActionWrapper(DelayableAction):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

        self.actions = []

        for config in self.cfg.list('actions'):
            self.actions.append(get_action(app, config))

    def job_runner(self, kwargs={}):
        trigger_info = kwargs.get('trigger_info')

        self.debug('About to run delayed job, trigger_info={}'.format(trigger_info))

        for action in self.actions:
            do_action(action, trigger_info)


class SetStateAction(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

    def do_action(self, trigger_info):
        entity_ids = self.cfg.list('entity_id')
        state = self.cfg.value('state', None)

        for entity_id in entity_ids:
            self.set_state(entity_id, state=state)


class HueActivateScene(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

    def do_action(self, trigger_info):
        entity_ids = self.cfg.list('entity_id')
        scene_names = self.cfg.list('scene_name')

        scene_name = random.choice(scene_names)
        for entity_id in entity_ids:
            group_name = self.get_state(entity_id, attribute='friendly_name')

            self.call_service('hue/hue_activate_scene', group_name=group_name, scene_name=scene_name)


class FireEvent(Action):
    def __init__(self, app, action_config):
        super().__init__(app, action_config)

    def do_action(self, trigger_info):
        event = self.cfg.value('event')
        event_data = self.cfg.value('event_data')

        self.app.fire_event(event, **event_data)
