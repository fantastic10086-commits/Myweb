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

_daily_cache = {}

def usd_reference_rates(on=None):
    """Latest common published USD/CNY and USD/EUR observation on/before date."""
    from datetime import date, datetime, timedelta
    today = (datetime.utcnow() + timedelta(hours=8)).date()
    day = on or today
    if day > today:
        raise ValueError('到账日期不能晚于今天。')
    key = day.isoformat()
    with _lock:
        cached = _daily_cache.get(key)
        if cached and time.time() - cached[0] < 1800:
            return dict(cached[1])
        start = (day - timedelta(days=14)).isoformat()
        url = 'https://api.frankfurter.dev/v2/rates?base=USD&quotes=CNY,EUR&from=' + start + '&to=' + key
        with urlopen(url, timeout=5) as response:
            rows = json.loads(response.read(262144).decode('utf-8'))
        observations = {}
        for row in rows:
            observed = date.fromisoformat(row['date'])
            if observed <= day and row['quote'].upper() in ('CNY', 'EUR'):
                observations.setdefault(observed, {})[row['quote'].upper()] = positive_rate(row['rate'])
        common = [d for d, rates in observations.items() if 'CNY' in rates and 'EUR' in rates]
        if not common:
            raise ValueError('该日期暂无可用参考汇率。')
        latest = max(common)
        rates = observations[latest]
        result = dict(usd_rmb_rate=rates['CNY'], rmb_usd_rate=1 / rates['CNY'],
                      eur_usd_rate=1 / rates['EUR'], eur_rmb_rate=rates['CNY'] / rates['EUR'],
                      fx_reference_date=latest.isoformat(), fx_source='Frankfurter')
        if len(_daily_cache) > 512:
            _daily_cache.clear()
        _daily_cache[key] = (time.time(), result)
        return dict(result)


def currency_reference_rates(currency, on=None):
    """Rates per one unit of a configured ISO currency; CNY is stored as RMB."""
    import re
    from datetime import date, datetime, timedelta
    currency = (currency or 'USD').upper()
    if not re.fullmatch(r'[A-Z]{3}', currency):
        raise ValueError('币种代码无效。')
    if currency in ('USD','RMB','EUR'):
        rates = usd_reference_rates(on)
        usd = 1 if currency == 'USD' else rates['rmb_usd_rate'] if currency == 'RMB' else rates['eur_usd_rate']
        rmb = rates['usd_rmb_rate'] if currency == 'USD' else 1 if currency == 'RMB' else rates['eur_rmb_rate']
        return dict(currency=currency,currency_usd_rate=usd,currency_rmb_rate=rmb,
                    fx_reference_date=rates['fx_reference_date'],fx_source=rates['fx_source'])
    today = (datetime.utcnow() + timedelta(hours=8)).date()
    day = on or today
    if day > today:
        raise ValueError('到账日期不能晚于今天。')
    key = currency, day.isoformat()
    with _lock:
        cached = _daily_cache.get(key)
        if cached and time.time() - cached[0] < 1800:
            return dict(cached[1])
        url = ('https://api.frankfurter.dev/v2/rates?base=USD&quotes=CNY,' + currency +
               '&from=' + (day-timedelta(days=14)).isoformat() + '&to=' + day.isoformat())
        with urlopen(url,timeout=5) as response:
            rows = json.loads(response.read(262144).decode('utf-8'))
        observations = {}
        for row in rows:
            observed = date.fromisoformat(row['date'])
            if observed <= day and row['quote'].upper() in ('CNY',currency):
                observations.setdefault(observed,{})[row['quote'].upper()] = positive_rate(row['rate'])
        complete = [d for d,r in observations.items() if 'CNY' in r and currency in r]
        if not complete:
            raise ValueError('该币种暂无可用参考汇率。')
        latest = max(complete)
        rates = observations[latest]
        result = dict(currency=currency,currency_usd_rate=1/rates[currency],
                      currency_rmb_rate=rates['CNY']/rates[currency],
                      fx_reference_date=latest.isoformat(),fx_source='Frankfurter')
        if len(_daily_cache)>512:
            _daily_cache.clear()
        _daily_cache[key] = time.time(),result
        return dict(result)


def receipt_performance_snapshot(currency, received_on):
    currency = (currency or 'USD').upper()
    if currency == 'USD':
        return dict(performance_usd_rate=1.0, performance_date=received_on,
                    performance_reference_date=received_on.isoformat(), performance_source='USD原币')
    rates = currency_reference_rates(currency, received_on)
    return dict(performance_usd_rate=rates['currency_usd_rate'],
                performance_date=received_on, performance_reference_date=rates['fx_reference_date'],
                performance_source=rates['fx_source'])


def payment_to_usd(payment, pi, amount=None):
    """Frozen per-receipt rate; pre-migration/isolated legacy rows keep old rule."""
    value = payment.amount if amount is None else amount
    rate = getattr(payment, 'performance_usd_rate', None)
    if rate is not None:
        return float(value or 0) * positive_rate(rate)
    from currency_utils import to_usd
    return to_usd(pi, value, performance=True)
