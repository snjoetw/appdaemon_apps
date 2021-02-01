import concurrent
import hashlib
import os
import re
import time
import traceback
from datetime import datetime, timedelta
from threading import Lock

import requests
from base_automation import BaseAutomation
from lib.component import Component
from pydub import AudioSegment


class MediaPlayer(Component):
    def __init__(self, app, config, media_manager):
        super().__init__(app, config)
        self.media_manager = media_manager
        self.player_entity_ids = self.cfg.list('player_entity_id', None)
        self.motion_entity_ids = self.cfg.list('motion_entity_id', None)
        self.volumes = self.cfg.value('volumes', None)
        self.targeted_only = self.cfg.value('targeted_only', False)

        if not self.player_entity_ids:
            raise ValueError('Missing player_entity_ids')

    def update_volume(self, volume_mode):
        for player_entity_id in self.player_entity_ids:
            self._update_volume(player_entity_id, volume_mode)

    def _update_volume(self, player_entity_id, volume_mode):
        if volume_mode is None:
            return

        volume = self.volumes.get(volume_mode, 0.2)
        current_volume = self.get_state(player_entity_id,
                                        attribute='volume_level')

        if current_volume is not None:
            current_volume = round(current_volume, 2)

        self.debug('Checking volume: {} vs {}'.format(
            current_volume,
            volume
        ))

        if current_volume != volume:
            self.call_service('media_player/volume_set',
                              entity_id=player_entity_id,
                              volume_level=volume)

    def play_media(self, medias, volume_mode):
        try:
            for player_entity_id in self.player_entity_ids:
                self._update_volume(player_entity_id, volume_mode)

                for media_data in medias:
                    self._play_media(player_entity_id, media_data)
        except:
            self.app.error("Unable to get play media, medias={}: {}".format(medias, traceback.format_exc()))

    def _play_media(self, player_entity_id, media_data):
        self.debug('About to play, entity={}, data={}'.format(player_entity_id, media_data))

        url = media_data.media_url
        self.call_service('media_player/play_media',
                          entity_id=player_entity_id,
                          media_content_id=url,
                          media_content_type='music')

        if media_data.duration:
            self._sleep(media_data.duration)

    def _sleep(self, duration):
        self.debug('About to sleep for {} sec'.format(duration))
        time.sleep(duration)


class GoogleMediaPlayer(MediaPlayer):
    def __init__(self, app, config, media_manager):
        super().__init__(app, config, media_manager)

        self.empty_media_url = '{}{}'.format(media_manager.api_base_url, LIBRARY_URL_PATH.format('empty.mp3'))

        if self.cfg.value('keep_alive', False):
            now = datetime.now() + timedelta(seconds=2)
            self.app.run_every(self._run_every_handler, now, 240)

    def _run_every_handler(self, time=None, **kwargs):
        self.app._announcer_lock.acquire()
        try:
            for player_entity_id in self.player_entity_ids:
                if self.get_state(player_entity_id) != 'playing':
                    self._play_media(player_entity_id, MediaData(self.empty_media_url, 0))
        finally:
            self.app._announcer_lock.release()


class SonosMediaPlayer(MediaPlayer):
    def __init__(self, app, config, media_manager):
        super().__init__(app, config, media_manager)

    def play_media(self, medias, volume_mode):
        requires_snapshot = self._requires_snapshot()
        if requires_snapshot:
            # take a snapshot of how sonos entities are joined
            self.call_service('sonos/snapshot',
                              entity_id=self.player_entity_ids,
                              with_group=False)

        # if we have mode than 1 sonos entities, join them together
        self._group_media_players()

        master_entity_id = self.player_entity_ids[0]

        self._update_volume(master_entity_id, volume_mode)
        for media_data in medias:
            self._play_media(master_entity_id, media_data)

        if requires_snapshot:
            # wait few seconds before restore
            self._sleep(2)

            # restore sonos entities based on snapshot
            self.call_service('sonos/restore',
                              entity_id=self.player_entity_ids,
                              with_group=True)

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

        self.call_service('sonos/join',
                          master=master_entity_id,
                          entity_id=to_join_entity_ids)


def create_player(app, config, media_manager):
    player_type = config.get('type')

    if player_type == 'sonos':
        return SonosMediaPlayer(app, config, media_manager)
    elif player_type == 'google':
        return GoogleMediaPlayer(app, config, media_manager)

    return MediaPlayer(app, config, media_manager)


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
    def initialize(self):
        self._announcer_lock = Lock()
        self._queue = []
        self._sleeping_time_entity_id = self.cfg.value('sleeping_time_entity_id')
        self._enabler_entity_id = self.cfg.value('enabler_entity_id')

        self._media_manager = MediaManager(self, self.args)
        self._players = [create_player(self, p, self._media_manager) for p in self.cfg.value('players')]

        self.listen_state(self._sleeping_time_state_change_handler, self._sleeping_time_entity_id)

    def _sleeping_time_state_change_handler(self, entity, attribute, old, new, kwargs):
        volume_mode = 'regular'
        if new == 'on':
            volume_mode = 'sleeping'

        for player in self._players:
            player.update_volume(volume_mode)

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


CACHE_FILE_MATCHER = re.compile(r'cached_(.+?)\.mp3')

TTS_BASE_FILEPATH = '/conf/tts/'
LOCAL_SPEECH_BASE_FILEPATH = '/conf/www/library/tts/'
LOCAL_TEMP_SPEECH_BASE_FILEPATH = '/conf/www/library/tts/tmp/'
CACHE_FILE_PATTERN = 'cached_{}@{}.mp3'
CHIME_FILEPATH = '/conf/www/library/sound/chime.mp3'
CACHE_KEY_PATTERN = '{0}_{1}'
CACHE_KEY_PATTERN_WITH_CHIME = '{0}_{1}_chime'
CHIME_FILE_SUFFIX = '_chime'
SPEECH_FILE_FORMAT = 'mp3'
MEDIA_TYPE_CACHED = 'cache'
MEDIA_TYPE_TEMP = 'temp'
# should be '/local/library/sound/{}' but looks like 404 also keeps speaker alive
LIBRARY_URL_PATH = '/local/library/sound/{}'
MEDIA_URL_PATH = '/local/library/tts/{}'
TEMP_MEDIA_URL_PATH = '/local/library/tts/tmp/{}'


def to_cache_key(announcement, with_chime):
    message = announcement.message
    prelude_name = announcement.prelude_name

    msg_hash = hashlib.sha1(bytes(message, 'utf-8')).hexdigest()
    message = re.sub(r'[^a-zA-Z0-9 ]+', '', message).replace(' ', '_')

    if prelude_name:
        message += '_' + prelude_name

    if with_chime:
        return CACHE_KEY_PATTERN_WITH_CHIME.format(msg_hash, message).lower()

    return CACHE_KEY_PATTERN.format(msg_hash, message).lower()


class MediaData:
    def __init__(self, media_url, duration):
        self._media_url = media_url
        self._duration = int(duration)

    @property
    def media_url(self):
        return self._media_url

    @property
    def duration(self):
        return self._duration

    def __repr__(self):
        return "{}(media_url={}, duration={})".format(self.__class__.__name__, self.media_url, self.duration)


def create_media_data(media_type, api_base_url, filepath, duration):
    filename = filepath.rsplit('/', 1)[-1]

    if media_type == MEDIA_TYPE_TEMP:
        return MediaData(api_base_url + TEMP_MEDIA_URL_PATH.format(filename), duration)
    else:
        return MediaData(api_base_url + MEDIA_URL_PATH.format(filename), duration)


AUDIO_FILEPATHS = {
    'alarm_siren': '/conf/www/library/sound/alarm_siren.mp3',
    'door_beep': '/conf/www/library/sound/door_beep.mp3',
    'window_beep': '/conf/www/library/sound/window_beep.mp3',
    'garage_beep': '/conf/www/library/sound/garage_beep.mp3',
}


class MediaManager(Component):
    def __init__(self, app, config):
        super().__init__(app, config)

        self.api_base_url = self.cfg.value('api_base_url', None)
        self.api_url = '{}/api/tts_get_url'.format(self.api_base_url)
        self.api_token = self.cfg.value('api_token', None)
        self.cache_file_path = LOCAL_SPEECH_BASE_FILEPATH
        self.cache = self._init_file_cache()

        self._cleanup_temp_cache()

    def _cleanup_temp_cache(self):
        deleted_count = 0

        for filename in os.listdir(LOCAL_TEMP_SPEECH_BASE_FILEPATH):
            file_path = os.path.join(LOCAL_TEMP_SPEECH_BASE_FILEPATH, filename)
            try:
                os.unlink(file_path)
                deleted_count += 1
            except Exception as e:
                self.error('Failed to delete {}. Reason: {}'.format(file_path, e))

        self.log('Deleted {} temp file in {}'.format(deleted_count, LOCAL_TEMP_SPEECH_BASE_FILEPATH))

    def _init_file_cache(self):
        self.debug('About to load file cache from {}'.format(self.cache_file_path))

        cache = {}
        for filename in os.listdir(self.cache_file_path):
            matched = CACHE_FILE_MATCHER.match(filename)
            if matched:
                cache_key, *data = matched.group(1).split('@')
                duration = 0 if not len(data) else int(data[0])
                cache[cache_key.lower()] = create_media_data(MEDIA_TYPE_CACHED,
                                                             self.api_base_url,
                                                             filename,
                                                             duration)

        self.debug('Loaded {} files'.format(len(cache)))

        return cache

    def get_media(self, announcement, with_chime):
        cache_key = to_cache_key(announcement, with_chime)
        cached = self.cache.get(cache_key)

        if announcement.use_cache and cached:
            self.debug('Found cached media file for announcement={}'.format(announcement))
            return cached

        tts_filename = self._get_tts_filename(announcement.message)
        tts_filepath = TTS_BASE_FILEPATH + tts_filename
        tts_data = TtsData(tts_filepath)
        prelude_filepath = AUDIO_FILEPATHS.get(announcement.prelude_name)

        if announcement.use_cache:
            return self._create_cached_audio_file(cache_key, tts_data, with_chime, prelude_filepath)

        return self._create_temp_audio_file(tts_data, with_chime, prelude_filepath)

    def _get_tts_filename(self, message):
        if not message.startswith('<speak>'):
            message = '<speak>' + message + '</speak>'

        self.debug('About to get tts filename: {}'.format(message))
        response = requests.post(self.api_url,
                                 json={
                                     'platform': 'amazon_polly',
                                     'message': message,
                                     'cache': True,
                                 },
                                 headers={
                                     'Authorization': self.api_token,
                                     'Content-Type': 'application/json'
                                 })

        self.debug('Received get_tts response: {}'.format(response))

        response.raise_for_status()
        tts_url = response.json().get('url')
        tts_filename = tts_url.rsplit('/', 1)[-1]

        self.debug('tts_filename={}'.format(tts_filename))

        return tts_filename

    def _build_cache_filepath(self, cache_key, duration):
        return self.cache_file_path + CACHE_FILE_PATTERN.format(cache_key, duration)

    def _create_cached_audio_file(self, audio_key, tts_data, with_chime,
                                  prelude_filepath):
        # create "not with_chime" version first
        cache_key = audio_key
        if cache_key.endswith(CHIME_FILE_SUFFIX):
            cache_key = cache_key.replace(CHIME_FILE_SUFFIX, '')
        else:
            cache_key = cache_key + CHIME_FILE_SUFFIX
        self._create_and_cache_audio_file(cache_key, tts_data, not with_chime, prelude_filepath)

        # then again create "with_chime" version
        cache_key = audio_key
        self._create_and_cache_audio_file(cache_key, tts_data, with_chime, prelude_filepath)

        return self.cache[cache_key]

    def _create_and_cache_audio_file(self, cache_key, tts_data, with_chime, prelude_filepath):
        audio = create_audio(tts_data, with_chime, prelude_filepath)
        duration = round(audio.duration_seconds)
        filepath = self._build_cache_filepath(cache_key, duration)
        audio.export(filepath, format=SPEECH_FILE_FORMAT)
        self.cache[cache_key] = create_media_data(MEDIA_TYPE_CACHED, self.api_base_url, filepath, duration)

        self.debug('Created cached audio file, filepath={}, with_chime={}'.format(filepath, with_chime))

    def _create_temp_audio_file(self, tts_data, with_chime, prelude_filepath):
        audio = create_audio(tts_data, with_chime, prelude_filepath)
        filepath = LOCAL_TEMP_SPEECH_BASE_FILEPATH + tts_data.filename
        audio.export(filepath, format=SPEECH_FILE_FORMAT)

        self.debug('Created temp audio file, filepath={}, with_chime={}'.format(filepath, with_chime))

        return create_media_data(MEDIA_TYPE_TEMP, self.api_base_url, filepath, round(audio.duration_seconds))


def create_audio(tts_data, with_chime, prelude_filepath=None):
    combined = AudioSegment.empty()

    if with_chime:
        chime = AudioSegment.from_mp3(CHIME_FILEPATH)
        combined += chime

    if prelude_filepath:
        prelude = AudioSegment.from_mp3(prelude_filepath)
        combined += prelude

    if tts_data:
        combined += tts_data.file

    return combined


class TtsData:
    def __init__(self, tts_filepath):
        self._filepath = tts_filepath
        self._filename = tts_filepath.rsplit('/', 1)[-1]
        self._file = AudioSegment.from_mp3(tts_filepath)
        self._duration = round(self._file.duration_seconds)

    @property
    def filepath(self):
        return self._filepath

    @property
    def filename(self):
        return self._filename

    @property
    def file(self):
        return self._file

    @property
    def duration(self):
        return self._duration
