import traceback
from datetime import datetime

from configurable_automation import ConfigurableAutomation
from lib.actions import Action
from lib.briefing_helper import MEDIUM_PAUSE
from lib.context import Context
from lib.helper import figure_parts_of_day
from lib.reminder_helper import get_reminder_provider, TIME_TRIGGER_METHOD, MOTION_TRIGGER_METHOD
from notifier import Notifier, Message, NotifierType
from sonos_announcer import SonosAnnouncer


class Reminder(ConfigurableAutomation):

    def initialize(self):
        super().initialize()

        motion_entity_ids = self.list_arg('motion_entity_id')
        self.init_trigger('state', {
            'entity_id': motion_entity_ids
        })
        self.init_handler(self.create_handler(
            [self.create_constraint('triggered_state', {
                'entity_id': motion_entity_ids,
                'to': 'on',
            })],
            [ReminderAction(self, self.args, MOTION_TRIGGER_METHOD)]))
        self.init_handler(self.create_handler(
            [self.create_constraint('triggered_state', {
                'entity_id': motion_entity_ids,
                'to': 'off',
            })],
            []))

        self.init_trigger('time', {
            'seconds': 60,
        })
        self.init_handler(self.create_handler([], [ReminderAction(self, self.args, TIME_TRIGGER_METHOD)]))


class ReminderAction(Action):
    def __init__(self, app, action_config, trigger_method):
        super().__init__(app, action_config)

        self.trigger_method = trigger_method
        self.providers = [get_reminder_provider(app, p) for p in self.config_wrapper.list('providers', None)]
        self.provider_history = {}
        self.presence_mode_entity_id = self.config_wrapper.value('presence_mode_entity_id', None)

    def do_action(self, trigger_info):
        if self.trigger_method == TIME_TRIGGER_METHOD and trigger_info.trigger_time.minute % 5:
            return

        motion_entity_id = trigger_info.data.get('entity_id')
        message = self.build_reminder_text()

        if not message:
            self.debug('No reminder message, skipping ...')
            return

        announcer: SonosAnnouncer = self.app.get_app('sonos_announcer')
        announcer.announce(message, use_cache=False, motion_entity_id=motion_entity_id)

        notifier: Notifier = self.app.get_app('notifier')
        notifier.notify(Message([NotifierType.IOS], 'all', None, message, None, {}))

    def build_reminder_text(self):
        parts_of_day = figure_parts_of_day()
        presence_mode = self.get_state(self.presence_mode_entity_id)
        context = Context(parts_of_day, presence_mode=presence_mode)
        now = datetime.now()
        reminder_texts = []

        for provider in self.providers:
            if not provider.enabled:
                continue

            if not self.should_check_provider(context, provider, now):
                continue

            try:
                reminder_text = provider.provide(context)
                if reminder_text is not None:
                    self.debug('Building reminder text with: {}'.format(reminder_text))
                    reminder_texts.append(reminder_text)
                    self.provider_history[provider] = now
            except:
                self.app.error("Unable to get reminder text: {}".format(traceback.format_exc()))

        text = MEDIUM_PAUSE.join(reminder_texts)

        self.debug('Built reminder text: {}'.format(text))

        return text

    def should_check_provider(self, context, provider, now):
        if self.trigger_method != provider.trigger_method:
            self.debug('Skipping ... trigger_method ({} vs {}) not match'.format(self.trigger_method,
                                                                                 provider.trigger_method))
            return False

        last_runtime = self.provider_history.get(provider)
        if last_runtime is None:
            return provider.can_provide(context)

        difference = (now - last_runtime).total_seconds() / 60
        if difference <= provider.interval:
            self.debug('Skipping ... min interval ({}) not reached'.format(provider.interval))
            return False

        return provider.can_provide(context)
