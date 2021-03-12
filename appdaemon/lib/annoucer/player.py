import traceback
from datetime import datetime, timedelta

from lib.annoucer.media_manager import MediaManager
from lib.core.app_accessible import AppAccessible


def create_player(app, raw_player_config, media_manager):
    app.debug('Creating player with config={}'.format(raw_player_config))

    player_config = PlayerConfig(raw_player_config)
    player_type = raw_player_config.get('type')
    if player_type == 'sonos':
        return SonosMediaPlayer(app, player_config, media_manager)
    elif player_type == 'google':
        return GoogleMediaPlayer(app, player_config, media_manager)

    raise ValueError('Unsupported player type: ' + raw_player_config)


class PlayerConfig:
    def __init__(self, raw_config):
        self._type = raw_config['type']
        self._player_entity_ids = raw_config['player_entity_id']
        self._motion_entity_ids = raw_config.get('motion_entity_id', ())
        self._targeted_only = raw_config.get('targeted_only', False)
        self._keep_alive = raw_config.get('keep_alive', False)
        self._volumes = raw_config.get('volume', {})

    @property
    def type(self):
        return self._type

    @property
    def player_entity_ids(self):
        if isinstance(self._player_entity_ids, list):
            return self._player_entity_ids
        return [self._player_entity_ids]

    @property
    def motion_entity_ids(self):
        if isinstance(self._motion_entity_ids, list):
            return self._motion_entity_ids
        return [self._motion_entity_ids]

    @property
    def targeted_only(self):
        return self._targeted_only

    @property
    def volumes(self):
        return self._volumes

    @property
    def keep_alive(self):
        return self._keep_alive


class Player(AppAccessible):
    _config: PlayerConfig
    _media_manager: MediaManager

    def __init__(self, app, config, media_manager):
        super().__init__(app)
        self._media_manager = media_manager
        self._config = config

    @property
    def config(self):
        return self._config

    @property
    def player_entity_ids(self):
        return self.config.player_entity_ids

    @property
    def motion_entity_ids(self):
        return self.config.motion_entity_ids

    @property
    def targeted_only(self):
        return self.config.targeted_only

    def update_volume(self, volume_mode):
        for player_entity_id in self.config.player_entity_ids:
            self.update_player_volume(player_entity_id, volume_mode)

    def update_player_volume(self, player_entity_id, volume_mode):
        self.debug('Updating {} to use volume_mode={}'.format(player_entity_id, volume_mode))

        if volume_mode is None:
            return

        volume = self.config.volumes.get(volume_mode, 0.2)
        self._set_volume(player_entity_id, volume)

    def _set_volume(self, player_entity_id, volume):
        current_volume = self.get_state(player_entity_id, attribute='volume_level')

        if current_volume is not None:
            current_volume = round(current_volume, 2)

        self.debug('Checking volume: {} vs {}'.format(current_volume, volume))

        if current_volume != volume:
            self.call_service('media_player/volume_set', entity_id=player_entity_id, volume_level=volume)

    def play_media(self, medias):
        try:
            for player_entity_id in self.config.player_entity_ids:
                for media_data in medias:
                    self._play_media(player_entity_id, media_data)
        except:
            self.error("Unable to get play media, medias={}: {}".format(medias, traceback.format_exc()))

    def _play_media(self, player_entity_id, media_data):
        self.debug('About to play, entity={}, data={}'.format(player_entity_id, media_data))

        url = media_data.media_url
        self.call_service('media_player/play_media', entity_id=player_entity_id, media_content_id=url,
                          media_content_type='music')

        if media_data.duration:
            self._sleep(media_data.duration)

    def _sleep(self, duration):
        self.app.sleep(duration)


class GoogleMediaPlayer(Player):
    def __init__(self, app, config, media_manager):
        super().__init__(app, config, media_manager)

        if config.keep_alive:
            now = datetime.now() + timedelta(seconds=2)
            self.app.run_every(self._run_every_handler, now, 240)

    def _run_every_handler(self, time=None, **kwargs):
        self.app._announcer_lock.acquire()
        try:
            for player_entity_id in self.player_entity_ids:
                if self.get_state(player_entity_id) != 'playing':
                    empty_media = self._media_manager.get_sound_media('empty', duration=0)
                    self._play_media(player_entity_id, empty_media)
        finally:
            self.app._announcer_lock.release()


class SonosMediaPlayer(Player):
    def __init__(self, app, config, media_manager):
        super().__init__(app, config, media_manager)

    def play_media(self, medias):
        requires_snapshot = self._requires_snapshot()
        if requires_snapshot:
            # take a snapshot of how sonos entities are joined
            self.call_service('sonos/snapshot', entity_id=self.player_entity_ids, with_group=False)

        # if we have mode than 1 sonos entities, join them together
        self._group_media_players()

        master_entity_id = self.player_entity_ids[0]

        for media_data in medias:
            self._play_media(master_entity_id, media_data)

        if requires_snapshot:
            # wait few seconds before restore
            self._sleep(2)

            # restore sonos entities based on snapshot
            self.call_service('sonos/restore', entity_id=self.player_entity_ids, with_group=True)

    def _all_player_paused(self):
        for entity_id in self.player_entity_ids:
            if self.get_state(entity_id) != 'paused':
                return False

        return True

    def _requires_snapshot(self):
        if self._all_player_paused():
            self.debug('No snapshot needed: all players paused')
            return False

        entities = [self.get_state(e, attribute='all') for e in self.player_entity_ids]

        for entity in entities:
            if entity is None:
                continue

            media_title = entity.get('attributes', {}).get('media_title')

            if media_title and not media_title.startswith('cached_'):
                self.debug('Snapshot needed: media_title starts with cache_')
                return True

        self.debug('No snapshot needed: media_title doesn\'t start with cache_')
        return False

    def _group_media_players(self):
        if len(self.player_entity_ids) == 1:
            self.debug('Skipping grouping: only one entity_id')
            return

        master_entity_id = self.player_entity_ids[0]
        to_join_entity_ids = self.player_entity_ids[1:]

        group = set(self.get_state(master_entity_id, attribute='sonos_group'))
        if set(to_join_entity_ids).issubset(group):
            self.debug('Skipping grouping: already grouped: {}'.format(group))
            return

        self.call_service('sonos/join', master=master_entity_id, entity_id=to_join_entity_ids)
