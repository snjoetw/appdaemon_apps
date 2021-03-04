import concurrent
from threading import Lock
from typing import List, Dict

from base_automation import BaseAutomation
from lib.annoucer.media_manager import MediaManager
from lib.annoucer.player import Player
from lib.annoucer.player import create_player


class AnnouncerConfig:
    _default_volume: Dict
    _enabler_entity_id: str
    _api_token: str
    _api_base_url: str
    _sleeping_time_entity_id: str

    def __init__(self, config):
        self._sleeping_time_entity_id = config['sleeping_time_entity_id']
        self._api_base_url = config['api_base_url']
        self._api_token = config['api_token']
        self._enabler_entity_id = config['enabler_entity_id']
        self._default_volume = config['default_volume']

    @property
    def sleeping_time_entity_id(self):
        return self._sleeping_time_entity_id

    @property
    def api_base_url(self):
        return self._api_base_url

    @property
    def api_token(self):
        return self._api_token

    @property
    def enabler_entity_id(self):
        return self._enabler_entity_id

    @property
    def default_volume(self):
        return self._default_volume


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
    _dnd_player_entity_ids: List
    _announcer_config: AnnouncerConfig
    _players: List[Player]
    _media_manager: MediaManager
    _dnd_entity_id: str
    _queue: List
    _announcer_lock: Lock

    def initialize(self):
        self._announcer_config = AnnouncerConfig({
            'api_base_url': self.cfg.value('api_base_url'),
            'api_token': self.cfg.value('api_token'),
            'default_volume': self.cfg.value('default_volume'),
            'enabler_entity_id': self.cfg.value('enabler_entity_id'),
            'sleeping_time_entity_id': self.cfg.value('sleeping_time_entity_id'),
        })

        self._announcer_lock = Lock()
        self._queue = []
        self._dnd_player_entity_ids = []

        self._media_manager = MediaManager(self, self.args)
        self._players = [self._create_player(p) for p in self.cfg.value('players')]

        self.listen_state(self._sleeping_time_state_change_handler, self._announcer_config.sleeping_time_entity_id)

        self.disable_do_not_disturb('media_player.office')

    def _create_player(self, raw_player_config):
        player_volume = raw_player_config.get('volume', {})
        raw_player_config['volume'] = {**self._announcer_config.default_volume, **player_volume}
        return create_player(self, raw_player_config, self._media_manager)

    def _sleeping_time_state_change_handler(self, entity, attribute, old, new, kwargs):
        self._update_player_volumes()

    def _update_player_volumes(self):
        for player in self._players:
            for player_entity_id in player.player_entity_ids:
                volume_mode = self._figure_volume_mode(player_entity_id)
                player.update_player_volume(player_entity_id, volume_mode)

    def _figure_volume_mode(self, player_entity_id):
        if player_entity_id in self._dnd_player_entity_ids:
            return 'dnd'

        if self.get_state(self._announcer_config.sleeping_time_entity_id) == 'on':
            return 'sleeping'

        return 'regular'

    def enable_do_not_disturb(self, player_entity_id):
        if player_entity_id not in self._dnd_player_entity_ids:
            self._dnd_player_entity_ids.append(player_entity_id)

        self._update_player_volumes()

    def disable_do_not_disturb(self, player_entity_id):
        if player_entity_id in self._dnd_player_entity_ids:
            self._dnd_player_entity_ids.remove(player_entity_id)

        self._update_player_volumes()

    def announce(self, message, use_cache=True, player_entity_ids=[], motion_entity_id=None, prelude_name=None):
        if self.get_state(self._announcer_config.enabler_entity_id) != 'on':
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
