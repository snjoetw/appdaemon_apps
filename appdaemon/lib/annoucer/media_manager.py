import hashlib
import os
import re

import requests
from pydub import AudioSegment

from lib.component import Component

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
