import json
import random
import tempfile
from pathlib import Path
from types import ModuleType
import sys

# stub dotenv if not installed
mock = ModuleType('dotenv')
mock.dotenv_values = lambda path: {}
sys.modules['dotenv'] = mock

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trading_bot.env_utils import parse_suggestion, update_env_vars

# 1) generate dummy 15m candle data
candles = []
for i in range(100):
    candles.append({
        'datetime': f"2023-01-01T00:{i:02d}:00",
        'open': round(random.uniform(10000, 11000), 2),
        'high': round(random.uniform(11000, 12000), 2),
        'low':  round(random.uniform(9000, 10000), 2),
        'close':round(random.uniform(10000, 11000), 2),
        'volume':round(random.uniform(1, 10), 2),
    })

print('Recent candles JSON snippet:')
print(json.dumps(candles[:2], indent=2) + '\n...')

# 2) pretend AI responded with suggestions
ai_response = '{"SMA_WINDOW":35, "ATR_WINDOW":20}'
print('AI raw response:', ai_response)

# 3) parse suggestions
suggestions = parse_suggestion(ai_response)
print('Parsed ->', suggestions)

# 4) simulate .env
env_text = 'SMA_WINDOW=30\nATR_WINDOW=14  # atr window\nOTHER=1\n'
print('\nOriginal .env:\n' + env_text)

with tempfile.TemporaryDirectory() as td:
    env_path = Path(td)/'.env'
    env_path.write_text(env_text)
    update_env_vars(suggestions, env_path)
    updated = env_path.read_text()
    print('Updated .env:\n' + updated)
