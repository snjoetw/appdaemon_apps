import re
from datetime import datetime, timedelta

from base_automation import BaseAutomation
from lib.helper import to_datetime


class LightRuntimeMonitor(BaseAutomation):
    def initialize(self):
        self._thresholds = self.cfg.value('thresholds')

        now = datetime.now() + timedelta(seconds=2)
        self.run_every(self._run_every_handler, now, self.cfg.value('check_frequency'))

    def _run_every_handler(self, time=None, **kwargs):
        checked_entities = []

        for entity_id, entity in self.get_state().items():
            if entity is None:
                continue

            for config in self._thresholds:
                if re.match(config['entity_id'], entity_id):
                    if entity_id in checked_entities:
                        continue

                    checked_entities.append(entity_id)

                    if config.get('ignore', False):
                        continue

                    if self.runtime_exceeds_threshold(config, entity):
                        self.turn_off(entity_id)

    def runtime_exceeds_threshold(self, config, entity):
        runtime = get_entity_runtime(entity)
        if runtime is None:
            return False

        threshold = config['threshold_in_minute']

        self.debug('entity_id={}, runtime={}, threshold={}'.format(
            entity['entity_id'],
            runtime,
            threshold
        ))

        exceeds_threshold = runtime > threshold

        if exceeds_threshold:
            self.log('Runtime exceeds threshold, '
                     'entity_id={}, '
                     'threshold={}, '
                     'runtime={}'.format(entity['entity_id'],
                                         threshold,
                                         runtime))

        return exceeds_threshold


def get_entity_runtime(entity):
    if entity.get('state') != 'on':
        return None

    last_changed = to_datetime(entity.get('last_changed'))
    if last_changed is None:
        return None

    last_changed = last_changed.replace(tzinfo=None)
    difference = datetime.utcnow() - last_changed

    return difference.total_seconds() / 60
