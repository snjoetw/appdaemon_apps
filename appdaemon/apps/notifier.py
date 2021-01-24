import json
import os.path
import time
from datetime import datetime

import requests
from enum import Enum
from typing import List

from base_automation import BaseAutomation


class NotifierType(Enum):
    IOS = 'ios'
    FACEBOOK_MESSENGER = 'facebook_messenger'
    PERSISTENT_NOTIFICATION = 'persistent_notification'


class Message:
    _notifier_types: List[NotifierType]
    _recipients: List[str]
    _title: str
    _message_text: str
    _camera_entity_id: str

    def __init__(self, notifier_types, recipients, title, message_text, camera_entity_id=None, settings={}):
        self._notifier_types = notifier_types
        self._recipients = recipients
        self._title = title
        self._message_text = message_text
        self._camera_entity_id = camera_entity_id
        self._settings = settings

    @property
    def notifier_types(self):
        return self._notifier_types

    @property
    def recipients(self):
        return self._recipients

    @property
    def camera_entity_id(self):
        return self._camera_entity_id

    @property
    def title(self):
        return self._title

    @property
    def message_text(self):
        return self._message_text

    @property
    def settings(self):
        if self._settings is None:
            return {}
        return self._settings

    def __repr__(self):
        return "{}(notifier_types={}, recipients={}, title={}, text={}, camera_entity_id={}, settings={})".format(
            self.__class__.__name__,
            self.notifier_types,
            self.recipients,
            self.title,
            self.message_text,
            self.camera_entity_id,
            self.settings)


class Messenger:
    def __init__(self, app, config, notifier_type):
        self._app = app
        self._notifier_type = notifier_type
        self._camera_snapshot_filepath = config.get('camera_snapshot_filepath', '/config/www/snapshot')
        self._recipients = config.get(notifier_type.value, {}).get('recipients')

    @property
    def app(self):
        return self._app

    @property
    def notifier_type(self):
        return self._notifier_type

    def call_service(self, service, **kwargs):
        self.app.call_service(service, **kwargs)

    def log(self, msg, level='INFO'):
        return self.app.log(msg, level)

    def send(self, message: Message):
        raise NotImplementedError()

    def get_camera_snapshot(self, camera_entity_id):
        filename = '{}-{}.jpg'.format(camera_entity_id, datetime.now().replace(microsecond=0).isoformat())
        data = {
            'entity_id': camera_entity_id,
            'filename': '{}/{}'.format(self._camera_snapshot_filepath, filename)
        }

        self.call_service('camera/snapshot', **data)

        return '/snapshot/{}'.format(filename)


class IosMessenger(Messenger):
    def __init__(self, app, config):
        super().__init__(app, config, NotifierType.IOS)

        self._external_base_url = config.get(NotifierType.IOS.value).get('external_base_url')

    def send(self, message: Message):
        recipients = self.figure_recipients(message)
        service_data = {
            'data': self.create_data(message),
            'message': message.message_text,
        }

        if message.title:
            service_data['title'] = message.title

        for recipient in recipients:
            self.call_service('notify/' + recipient, **service_data)

    def figure_recipients(self, message: Message):
        if 'all' in message.recipients:
            return ['all_ios']
        return [self._recipients.get(r) for r in message.recipients]

    def create_data(self, message: Message):
        data = {}

        if message.camera_entity_id:
            snapshot_filepath = self.get_camera_snapshot(message.camera_entity_id)
            snapshot_url = '{}/local{}'.format(self._external_base_url, snapshot_filepath)
            data['attachment'] = {
                'url': snapshot_url,
                'hide-thumbnail': False,
            }

        settings = message.settings.get(NotifierType.IOS.value)
        if settings is None:
            return data

        url = settings.get('url')
        if url is not None:
            data['url'] = url

        push = {}
        thread_id = settings.get('thread_id')
        if thread_id is not None:
            push['thread-id'] = thread_id

        category = settings.get('category')
        if category is not None:
            push['category'] = category

        critical = settings.get('critical')
        if critical:
            push['sound'] = {
                'name': 'default',
                'critical': 1,
                'volume': settings.get('volume', 0.5),
            }

        if push:
            data['push'] = push

        return data


class FacebookMessenger(Messenger):
    def __init__(self, app, config):
        super().__init__(app, config, NotifierType.FACEBOOK_MESSENGER)

        self._access_token = config.get(NotifierType.FACEBOOK_MESSENGER.value).get('access_token')

    def send(self, message: Message):
        recipients = self.figure_recipients(message)

        if message.camera_entity_id:
            snapshot_filepath = self.get_camera_snapshot(message.camera_entity_id)
            self.send_image_message(recipients, snapshot_filepath)

        return self.send_text_message(recipients, message.message_text)

    def figure_recipients(self, message: Message):
        if 'all' in message.recipients:
            return self._recipients.values()
        return [self._recipients.get(r) for r in message.recipients]

    def send_image_message(self, recipients, image_filepath):
        image_filename = os.path.basename(image_filepath)
        params = {
            'access_token': self._access_token
        }
        files = {
            'filedata': (image_filename, open('/conf/www/{}'.format(image_filepath), 'rb'), 'image/jpeg')
        }

        for recipient in recipients:
            data = {
                'recipient': json.dumps({
                    'id': recipient
                }),
                'message': json.dumps({
                    'attachment': {
                        'type': 'image',
                        'payload': {
                            "url": "http://www.messenger-rocks.com/image.jpg",
                            "is_reusable": True
                        }
                    }
                }),
            }
            r = requests.post(
                'https://graph.facebook.com/v2.6/me/messages',
                params=params,
                data=data,
                files=files)

            self.log('Facebook API with data={} and got back {}'.format(data, r.text))

    def send_text_message(self, recipients, text):
        self.call_service('notify/facebook_messenger', message=text, target=recipients)


class PersistentNotificationMessenger(Messenger):
    def __init__(self, app, config):
        super().__init__(app, config, NotifierType.PERSISTENT_NOTIFICATION)

    def send_image_message(self, message: Message):
        snapshot_filepath = self.get_camera_snapshot(message.camera_entity_id)
        self.send_text_message(
            message.message_text
            + '\n'
            + '![image](/local{})'.format(snapshot_filepath))

    def send_text_message(self, text):
        self.call_service('persistent_notification/create', **{
            'notification_id': 'pn_{}'.format(time.time()),
            'title': time.strftime('%m/%d %H:%M'),
            'message': text,
        })

    def send(self, message: Message):
        if message.camera_entity_id:
            self.send_image_message(message)
            return

        return self.send_text_message(message.message_text)


class Notifier(BaseAutomation):
    _messengers: List[Messenger]

    def initialize(self):
        self._messengers = (
            PersistentNotificationMessenger(self, self.args),
            IosMessenger(self, self.args),
            FacebookMessenger(self, self.args)
        )

    def notify(self, message: Message):
        messengers = [m for m in self._messengers if m.notifier_type in message.notifier_types]

        self.debug('About to send message={} with messengers={}'.format(message, messengers))

        for messenger in messengers:
            messenger.send(message)
