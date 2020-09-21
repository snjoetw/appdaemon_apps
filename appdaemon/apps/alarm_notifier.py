import json
import time
from enum import Enum

import appdaemon.plugins.hass.hassapi as hass
import requests

from lib.helper import create_ios_push_data


class AlarmNotifier(hass.Hass):
    def initialize(self):
        self.external_base_url = self.args['external_base_url']
        self.is_vacation_mode_entity_id = self.args[
            'is_vacation_mode_entity_id']
        self.presence_mode_entity_id = self.args['presence_mode_entity_id']
        self.ios_recipients = self.args['ios_recipients']
        self.facebook_recipients = self.args['facebook_recipients']
        self.facebook_access_token = self.args['facebook_access_token']
        self.entity_settings = self.args['entity_settings']
        self.messengers = (
            PersistentNotificationMessenger(self),
            IosMessenger(self, self.ios_recipients, self.external_base_url),
            FacebookMessenger(self,
                              self.facebook_access_token,
                              self.facebook_recipients)
        )

    def send(self, message, trigger_entity_id, messenger_types=[],
             image_filename=None):
        if not messenger_types:
            messenger_types = [MessengerType.PERSISTENT_NOTIFICATION,
                               MessengerType.IOS]

            is_vacation_mode = self.get_state(self.is_vacation_mode_entity_id)
            presence_mode = self.get_state(self.presence_mode_entity_id)
            if is_vacation_mode == 'on' and presence_mode == 'No One is Home':
                messenger_types.append(MessengerType.FACEBOOK)
        else:
            messenger_types = [MessengerType(x) for x in messenger_types]

        setting = self.entity_settings.get(trigger_entity_id, {})

        for messenger in self.get_messengers(messenger_types):
            messenger.send(message, setting.get('camera_entity_id'),
                           image_filename)

    def get_messengers(self, messenger_types):
        return [m for m in self.messengers if m.type in messenger_types]


class MessengerType(Enum):
    IOS = 'ios'
    FACEBOOK = 'facebook'
    PERSISTENT_NOTIFICATION = 'persistent_notification'


class Messenger:
    def __init__(self, app, messenger_type, recipients):
        self._app = app
        self._messenger_type = messenger_type
        self._recipients = recipients

    @property
    def type(self):
        return self._messenger_type

    def send(self, message, camera_entity_id=None, image_filename=None):
        if camera_entity_id:
            self.send_camera_snapshot(message, camera_entity_id)
        elif image_filename:
            self.send_message_with_image(message, image_filename)
        else:
            self.send_message(message)

    def send_camera_snapshot(self, message, camera_entity_id=None):
        raise NotImplementedError()

    def send_message_with_image(self, message, image_filename=None):
        raise NotImplementedError()

    def send_message(self, message):
        raise NotImplementedError()

    def call_service(self, service, **kwargs):
        self._app.log('Calling {} with {}'.format(service, kwargs))
        self._app.call_service(service, **kwargs)

    def log(self, msg, level='INFO'):
        return self._app.log(msg, level)


class IosMessenger(Messenger):
    def __init__(self, app, recipients, external_base_url):
        super().__init__(app, MessengerType.IOS, recipients)

        self._external_base_url = external_base_url

    def send_camera_snapshot(self, message, camera_entity_id=None):
        for recipient in self._recipients:
            data = create_ios_push_data('camera',
                                        entity_id=camera_entity_id,
                                        attachment={
                                            'content-type': 'jpeg'
                                        })

            self.call_service('notify/' + recipient,
                              message=message,
                              data=data)

    def send_message_with_image(self, message, image_filename=None):
        for recipient in self._recipients:
            self.call_service('notify/' + recipient,
                              message=message,
                              data={
                                  'attachment': {
                                      'url': '{}/local/snapshot/{}'.format(
                                          self._external_base_url,
                                          image_filename),
                                      'hide-thumbnail': False,
                                  },
                              })

    def send_message(self, message):
        for recipient in self._recipients:
            self.call_service('notify/' + recipient, message=message)


class FacebookMessenger(Messenger):
    def __init__(self, app, access_token, recipients):
        super().__init__(app, MessengerType.FACEBOOK, recipients)

        self._access_token = access_token

    def send_message_with_image(self, message, image_filename=None):
        params = {
            'access_token': self._access_token
        }

        for recipient in self._recipients:
            files = {
                'filedata': (
                    '{}'.format(image_filename),
                    open('/conf/www/snapshot/{}'.format(image_filename),
                         'rb'),
                    'image/jpeg')
            }
            data = {
                'recipient': json.dumps({
                    'id': recipient
                }),
                'message': json.dumps({
                    'attachment': {
                        'type': 'image',
                        'payload': {}
                    }
                }),
            }
            r = requests.post(
                'https://graph.facebook.com/v2.6/me/messages',
                params=params,
                data=data,
                files=files)

            self.log('Facebook API with data={} and got back {}'.format(data,
                                                                        r.text))

        self.send_message(message)

    def send_camera_snapshot(self, message, camera_entity_id):
        filename = '{}.jpg'.format(camera_entity_id)

        self.call_service('camera/snapshot', **{
            'entity_id': camera_entity_id,
            'filename': '/config/www/snapshot/{}'.format(filename)
        })

        self.send_message_with_image(message, filename)

    def send_message(self, message):
        self.call_service('notify/facebook_messenger',
                          message=message,
                          target=self._recipients)


class PersistentNotificationMessenger(Messenger):
    def __init__(self, app):
        super().__init__(app, MessengerType.PERSISTENT_NOTIFICATION, None)

    def send_camera_snapshot(self, message, camera_entity_id=None):
        self.send_message(message)

    def send_message_with_image(self, message, image_filename=None):
        self.send_message(
            message
            + '\n'
            + '![image](/local/snapshot/{}?t={})'.format(image_filename,
                                                         time.time()))

    def send_message(self, message):
        self.call_service('persistent_notification/create', **{
            'notification_id': 'pn_{}'.format(time.time()),
            'title': time.strftime('%m/%d %H:%M'),
            'message': message,
        })
