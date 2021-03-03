import concurrent
from threading import Lock
from typing import List

from base_automation import BaseAutomation
from lib.annoucer.media_manager import MediaManager
from lib.annoucer.player import Player
from lib.annoucer.player import create_player
from lib.helper import list_value


class Announcement:
    def __init__(self, message, use_cache, prelude_name, is_critical):
        self._message = message
        self._use_cache = use_cache
        self._prelude_name = prelude_name
        self._is_critical = is_critical

    @property
    def message(self):
        return self._message

    @property
    def use_cache(self):
        return self._use_cache

    @property
    def prelude_name(self):
        return self._prelude_name

    @property
    def is_critical(self):
        return self._is_critical

    def __repr__(self):
        return "{}(message={}, use_cache={}, prelude_name={}, is_critical={})".format(
            self.__class__.__name__,
            self.message,
            self.use_cache,
            self.prelude_name,
            self.is_critical)

    def __eq__(self, other):
        if not isinstance(other, Announcement):
            return NotImplemented

        return self.message == other.message \
               and self.use_cache == other.use_cache \
               and self.prelude_name == other.prelude_name \
               and self.is_critical == other.is_critical


class SonosAnnouncer(BaseAutomation):
    _players: List[Player]
    _media_manager: MediaManager
    _dnd_entity_id: str
    _enabler_entity_id: str
    _sleeping_time_entity_id: str
    _queue: List
    _announcer_lock: Lock

    def initialize(self):
        self._announcer_lock = Lock()
        self._queue = []
        self._sleeping_time_entity_id = self.cfg.value('sleeping_time_entity_id')
        self._enabler_entity_id = self.cfg.value('enabler_entity_id')
        self._dnd_entity_id = self.cfg.value('dnd_entity_id')
        self._dnd_player_entity_ids = []

        self._media_manager = MediaManager(self, self.args)
        self._players = [self._create_player(p) for p in self.cfg.value('players')]

        self.listen_state(self._sleeping_time_state_change_handler, self._sleeping_time_entity_id)

    def _create_player(self, raw_player_config):
        self.debug('Creating player with player_config={}'.format(raw_player_config))
        raw_player_config['dnd_entity_id'] = self.cfg.value('dnd_entity_id')
        return create_player(self, raw_player_config, self._media_manager)

    def _sleeping_time_state_change_handler(self, entity, attribute, old, new, kwargs):
        volume_mode = 'regular'
        if new == 'on':
            volume_mode = 'sleeping'

        for player in self._players:
            player.update_volume(volume_mode)

    def enable_do_not_disturb(self, player_entity_id):
        enable_entity_ids = set(list_value(player_entity_id))
        dnd_entity_ids = sorted(self._current_do_not_disturb_entity_ids().union(enable_entity_ids))
        self._update_do_not_disturb(','.join(dnd_entity_ids))

    def disable_do_not_disturb(self, player_entity_id):
        disabled_entity_ids = set(list_value(player_entity_id))
        dnd_entity_ids = sorted(self._current_do_not_disturb_entity_ids() - disabled_entity_ids)
        self._update_do_not_disturb(','.join(dnd_entity_ids))

    def _current_do_not_disturb_entity_ids(self):
        value = self.get_state(self._dnd_entity_id)
        if value is None:
            return {}

        return set([v for v in value.split(',') if v.startswith('media_player.')])

    def _update_do_not_disturb(self, value):
        data = {
            'entity_id': self._dnd_entity_id,
            'value': value
        }
        self.call_service("input_text/set_value", **data)

    def announce(self, message, use_cache=True, player_entity_ids=[], motion_entity_id=None, prelude_name=None):
        if self.get_state(self._enabler_entity_id) != 'on':
            self.log('Skipping ... announcer disable')
            return

        players = self._figure_players(player_entity_ids, motion_entity_id)

        if not players:
            self.warn('Unble to find matching player with player_entity_ids={}, motion_entity_id={}'.format(
                player_entity_ids,
                motion_entity_id))
            return

        self.debug('Using {} players'.format(len(players)))

        self._queue.append(Announcement(message, use_cache, prelude_name, False))
        self._lock_and_announce(players)

    def _figure_players(self, player_entity_ids, motion_entity_id):
        self.debug('About to figure players player={}, motion={}'.format(player_entity_ids, motion_entity_id))

        if player_entity_ids:
            players = []

            for player in self._players:
                if all(id in player_entity_ids for id in player.player_entity_ids):
                    self.debug('Using {}'.format(player.player_entity_ids))
                    players.append(player)

            return players

        if motion_entity_id:
            for player in self._players:
                if motion_entity_id in player.motion_entity_ids:
                    self.debug('Using {}'.format(player))
                    return [player]
            return None

        return [p for p in self._players if not p.targeted_only]

    def _lock_and_announce(self, players):
        if not self._queue:
            self.debug('Nothing in the queue, skipping ...')
            return

        if not players:
            self.error('No player specified')
            return

        self._announcer_lock.acquire()
        try:
            self._do_announce(players)
        finally:
            self._announcer_lock.release()

    def _do_announce(self, players):
        queue = self._dequeue_all()
        if not queue:
            self.debug('Nothing in the queue, skipping ....')
            return

        with_chime = True
        medias = []
        previous_announcement = None

        while queue:
            announcement = queue.pop(0)

            if announcement == previous_announcement:
                self.debug('Skipping duplicate announcement: {}'.format(announcement))
                continue

            if announcement.prelude_name:
                with_chime = False

            media_data = self._media_manager.get_media(announcement, with_chime)
            medias.append(media_data)
            previous_announcement = announcement

            with_chime = False

        volume_mode = None

        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = {
                executor.submit(p.play_media, medias, volume_mode) for p in players
            }

            for future in concurrent.futures.as_completed(futures):
                future.result()

    def _dequeue_all(self):
        dequeued, self._queue[:] = self._queue[:], []
        return dequeued
