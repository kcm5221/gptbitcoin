import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import importlib
from pathlib import Path
from unittest.mock import patch
import unittest

class ConfigEnvPathTest(unittest.TestCase):
    def test_load_dotenv_called_with_resolved_path(self):
        sys.modules.pop('trading_bot.config', None)
        with patch('dotenv.load_dotenv') as mock_load:
            import trading_bot.config as cfg
            expected = Path(cfg.__file__).resolve().parent.parent / ".env"
            mock_load.assert_called_once_with(expected)


class ConfigLogEnvInfoTest(unittest.TestCase):
    def test_openai_api_key_masked_in_log(self):
        sys.modules.pop('trading_bot.config', None)
        with patch('dotenv.load_dotenv'), patch.dict(os.environ, {"OPENAI_API_KEY": "abcd1234efgh5678"}):
            import trading_bot.config as cfg
            with self.assertLogs(cfg.logger, level="INFO") as cm:
                cfg.log_env_info()
            log_output = "\n".join(cm.output)
            self.assertNotIn("abcd1234efgh5678", log_output)
            self.assertIn("abcd...5678", log_output)

if __name__ == '__main__':
    unittest.main()

