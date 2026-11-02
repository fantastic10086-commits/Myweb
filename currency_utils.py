"""Explicit PI currency conversions; historical USD/RMB rules are preserved."""
import math

SYMBOLS = {'USD': '$', 'RMB': '¥', 'EUR': '€'}

def currency_symbol(currency):
    return SYMBOLS.get((currency or 'USD').upper(), currency or 'USD')

def positive_rate(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError('请填写有效的欧元汇率。')
    if not math.isfinite(result) or result <= 0:
        raise ValueError('欧元汇率必须大于 0。')
    return result

def to_usd(pi, amount, performance=False):
    currency = (pi.currency or 'USD').upper()
    if currency == 'EUR':
        return float(amount or 0) * positive_rate(pi.eur_usd_rate)
    if currency == 'RMB':
        return float(amount or 0) / (7.0 if performance else positive_rate(pi.exchange_rate))
    return float(amount or 0)

def to_rmb(pi, amount, currency=None):
    currency = (currency or pi.currency or 'USD').upper()
    if currency == 'RMB':
        return float(amount or 0)
    if currency == 'EUR':
        return float(amount or 0) * positive_rate(pi.eur_rmb_rate)
    return float(amount or 0) * positive_rate(pi.exchange_rate)
