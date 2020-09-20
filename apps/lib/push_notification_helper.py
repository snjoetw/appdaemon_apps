from lib.component import Component


def get_push_notification_handler(app, push_category):
    pass


class Handler(Component):
    def __init__(self, app):
        super().__init__(app, {})

    def handle(self, data):
        pass
