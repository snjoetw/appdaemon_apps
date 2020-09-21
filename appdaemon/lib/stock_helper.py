from datetime import datetime

import requests
from lib.component import Component
from lib.helper import to_float

TRADING_TIME_START = datetime.strptime('06:30:00', '%H:%M:%S').time()
TRADING_TIME_END = datetime.strptime('13:00:00', '%H:%M:%S').time()


class StockQuoteFetcher(Component):
    def __init__(self, app, api_key):
        super().__init__(app, {})

        self.quote_url = "https://finnhub.io/api/v1/quote?token={}&symbol=".format(api_key)

    def fetch_quote(self, symbol):
        self.debug('About to fetch quote with symbol={}'.format(symbol))

        response = requests.get(self.quote_url.format(symbol) + symbol)

        self.debug('Received API response={}, json={}'.format(response, response.json()))

        response.raise_for_status()

        return Quote(symbol, response.json())


class Quote:
    def __init__(self, symbol, json):
        self._symbol = symbol
        self._open = to_float(json['o'])
        self._high = to_float(json['h'])
        self._low = to_float(json['l'])
        self._price = to_float(json['c'])
        self._timestamp = datetime.fromtimestamp(to_float(json['t']))
        self._previous_close = to_float(json['pc'])
        self._change = round(self._price - self._previous_close, 2)
        self._change_percent = '{}%'.format(round(self._change / self._previous_close * 100))

    @property
    def symbol(self):
        return self._symbol

    @property
    def open(self):
        return self._open

    @property
    def high(self):
        return self._high

    @property
    def low(self):
        return self._low

    @property
    def price(self):
        return self._price

    @property
    def volume(self):
        return self._volume

    @property
    def timestamp(self):
        return self._timestamp

    @property
    def previous_close(self):
        return self._previous_close

    @property
    def change(self):
        return self._change

    @property
    def change_percent(self):
        return self._change_percent

    @property
    def is_currently_trading(self):
        delta = datetime.now() - self.timestamp

        if delta.days > 0:
            return False

        return TRADING_TIME_START <= self.timestamp.time() <= TRADING_TIME_END
