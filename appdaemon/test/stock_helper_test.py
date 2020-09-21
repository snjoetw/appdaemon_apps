import unittest
from datetime import datetime

from mock import patch

from lib.stock_helper import Quote

QUOTE_JSON = {
    "c": 261.74,
    "h": 263.31,
    "l": 260.68,
    "o": 261.07,
    "pc": 259.45,
    "t": 1582641000
}


class StockQuoteTest(unittest.TestCase):

    def test_quote_json(self):
        quote = Quote('IBM', QUOTE_JSON)

        self.assertTrue(quote.symbol == 'IBM')
        self.assertTrue(quote.price == 261.74)
        self.assertTrue(quote.high == 263.31)
        self.assertTrue(quote.low == 260.68)
        self.assertTrue(quote.open == 261.07)
        self.assertTrue(quote.previous_close == 259.45)
        self.assertTrue(quote.timestamp.year == 2020)
        self.assertTrue(quote.timestamp.month == 2)
        self.assertTrue(quote.timestamp.day == 25)
        self.assertTrue(quote.change == 2.29)
        self.assertTrue(quote.change_percent == '1%')

    def test_quote_is_in_trading_time(self):
        with patch('lib.stock_helper.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2020, 9, 11, 7, 23, 51)

            quote = Quote('AAPL', QUOTE_JSON)
            self.assertTrue(quote.is_currently_trading)

    def test_quote_is_not_in_trading_time(self):
        with patch('lib.stock_helper.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2020, 9, 11, 14, 23, 51)

            quote = Quote('AAPL', QUOTE_JSON)
            self.assertFalse(quote.is_currently_trading)

    def test_quote_is_different_in_trading_day(self):
        with patch('lib.stock_helper.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2020, 9, 12, 7, 23, 51)

            quote = Quote('AAPL', QUOTE_JSON)
            self.assertFalse(quote.is_currently_trading)
