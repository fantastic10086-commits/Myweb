"""Explicit PI currency conversions; historical USD/RMB rules are preserved."""
import math

SYMBOLS = {'USD': '$', 'RMB': '¥', 'EUR': '€', 'HKD': 'HK$'}

def currency_symbol(currency):
    code = (currency or 'USD').upper()
    from flask import has_app_context, has_request_context, g
    if has_app_context():
        from models import Currency
        if has_request_context():
            if not hasattr(g, 'currency_symbols'):
                g.currency_symbols = {c.code: c.symbol for c in Currency.query.all()}
            return g.currency_symbols.get(code, SYMBOLS.get(code, code))
        row = Currency.query.filter_by(code=code).first()
        if row:
            return row.symbol
    return SYMBOLS.get(code, code)

def positive_rate(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError('请填写有效的汇率。')
    if not math.isfinite(result) or result <= 0:
        raise ValueError('汇率必须大于 0。')
    return result

def to_usd(pi, amount, performance=False):
    currency = (pi.currency or 'USD').upper()
    if currency == 'EUR':
        return float(amount or 0) * positive_rate(pi.eur_usd_rate)
    if currency == 'RMB':
        return float(amount or 0) / (7.0 if performance else positive_rate(pi.exchange_rate))
    if currency != 'USD':
        return float(amount or 0) * positive_rate(getattr(pi, 'currency_usd_rate', None))
    return float(amount or 0)

def to_rmb(pi, amount, currency=None):
    currency = (currency or pi.currency or 'USD').upper()
    if currency == 'RMB':
        return float(amount or 0)
    if currency == 'EUR':
        return float(amount or 0) * positive_rate(pi.eur_rmb_rate)
    if currency != 'USD':
        return float(amount or 0) * positive_rate(getattr(pi, 'currency_rmb_rate', None))
    return float(amount or 0) * positive_rate(pi.exchange_rate)
