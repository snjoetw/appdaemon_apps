import unittest
from datetime import datetime
from unittest.mock import patch

from lib.stock_helper import Quote

QUOTE_JSON = {
    "c": 261.74,
    "h": 263.31,
    "l": 260.68,
    "o": 261.07,
    "pc": 259.45,
    "t": 1599833000
}


class StockQuoteTest(unittest.TestCase):

    def test_quote_json(self):
        current_time = datetime(2020, 9, 11, 7, 23, 51)
        quote = Quote(current_time, 'IBM', QUOTE_JSON)

        self.assertTrue(quote.symbol == 'IBM')
        self.assertTrue(quote.price == 261.74)
        self.assertTrue(quote.high == 263.31)
        self.assertTrue(quote.low == 260.68)
        self.assertTrue(quote.open == 261.07)
        self.assertTrue(quote.previous_close == 259.45)
        self.assertTrue(quote.timestamp.year == 2020)
        self.assertTrue(quote.timestamp.month == 9)
        self.assertTrue(quote.timestamp.day == 11)
        self.assertTrue(quote.change == 2.29)
        self.assertTrue(quote.change_percent == '1%')

    def test_quote_is_in_trading_time(self):
        current_time = datetime(2020, 9, 11, 7, 23, 51)

        quote = Quote(current_time, 'AAPL', QUOTE_JSON)
        self.assertTrue(quote.is_currently_trading)

    def test_quote_is_not_in_trading_time(self):
        current_time = datetime(2020, 9, 11, 14, 23, 51)
        QUOTE_JSON['t'] = current_time.timestamp()

        quote = Quote(current_time, 'AAPL', QUOTE_JSON)
        self.assertFalse(quote.is_currently_trading)

    def test_quote_is_different_in_trading_day(self):
        current_time = datetime(2020, 9, 12, 7, 23, 51)

        quote = Quote(current_time, 'AAPL', QUOTE_JSON)
        self.assertFalse(quote.is_currently_trading)
