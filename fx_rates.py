"""Latest published reference rates. No business/customer data is sent upstream."""
import json
import threading
import time
from urllib.request import urlopen
from currency_utils import positive_rate

_lock = threading.Lock()
_cache = None

def latest_eur_rates():
    global _cache
    with _lock:
        if _cache and time.time() - _cache[0] < 1800:
            return dict(_cache[1])
        with urlopen('https://api.frankfurter.dev/v2/rates?base=EUR&quotes=USD,CNY', timeout=5) as response:
            rows = json.loads(response.read(65536).decode('utf-8'))
        rates = {row['quote'].upper(): row for row in rows}
        if rates['USD']['date'] != rates['CNY']['date']:
            raise ValueError('汇率日期不一致，请手动填写。')
        result = {'eur_usd_rate': positive_rate(rates['USD']['rate']),
                  'eur_rmb_rate': positive_rate(rates['CNY']['rate']),
                  'fx_reference_date': rates['USD']['date'], 'fx_source': 'Frankfurter'}
        _cache = (time.time(), result)
        return dict(result)
