import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import unittest
from types import SimpleNamespace
from unittest.mock import patch

# Provide dummy pyupbit module if missing
if 'pyupbit' not in sys.modules:
    sys.modules['pyupbit'] = SimpleNamespace(Upbit=lambda *a, **k: None)
if 'requests' not in sys.modules:
    sys.modules['requests'] = SimpleNamespace(post=lambda *a, **k: None)
if 'pandas' not in sys.modules:
    sys.modules['pandas'] = SimpleNamespace(DataFrame=object)
if 'dotenv' not in sys.modules:
    sys.modules['dotenv'] = SimpleNamespace(load_dotenv=lambda *a, **k: None)

from trading_bot.executor import execute_trade
from trading_bot.config import LIVE_MODE

class ExecuteTradeTest(unittest.TestCase):
    def test_avg_price_reset_on_full_sell(self):
        if LIVE_MODE:
            self.skipTest("LIVE_MODE enabled")
        ctx = SimpleNamespace(
            equity=100000.0,
            krw=0.0,
            btc=0.1,
            avg_price=50000.0,
            price=500000.0,
            atr15=0.0,
        )
        with patch('trading_bot.executor.save_account') as mock_save:
            executed, pct = execute_trade(ctx, False, True, 'test')
            self.assertTrue(executed)
            self.assertEqual(ctx.btc, 0.0)
            self.assertEqual(ctx.avg_price, 0.0)
            mock_save.assert_called_once()

if __name__ == '__main__':
    unittest.main()
