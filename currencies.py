"""Configurable ISO currencies. Code stays immutable to preserve historical records."""
import re
from datetime import datetime
from models import db, Currency

DEFAULTS = [('USD','美元','$'), ('RMB','人民币','¥'), ('EUR','欧元','€'), ('HKD','港币','HK$')]


def seed_currencies():
    for code, name, symbol in DEFAULTS:
        if db.session.get(Currency, code) is None:
            db.session.add(Currency(code=code, name=name, symbol=symbol, enabled=True))
    db.session.commit()


def currency_allowed(code, previous=None):
    code = 'USD' if code is None else code.upper()
    if not re.fullmatch(r'[A-Z]{3}', code):
        return False
    row = db.session.get(Currency, code)
    return bool(row and (row.enabled or code == previous))


def currency_options(current=None):
    return [c for c in Currency.query.order_by(Currency.code).all() if c.enabled or c.code == current]


def register_currency_management(app, *, login_required, admin_required, audit, password):
    from flask import render_template, request, redirect, url_for, flash, abort
    from sqlalchemy.exc import IntegrityError
    import fx_rates

    @app.get('/currencies')
    @login_required
    def currency_list():
        return render_template('currencies.html', currencies=Currency.query.order_by(Currency.code).all())

    def values():
        name, symbol = request.form.get('name','').strip(), request.form.get('symbol','').strip()
        if not name or len(name) > 50 or not symbol or len(symbol) > 12:
            raise ValueError('请填写币种名称（最多50字）和符号（最多12字）。')
        return name, symbol

    @app.post('/currencies/add')
    @login_required
    def currency_add():
        if not password():
            return redirect(url_for('currency_list'))
        code = request.form.get('code','').strip().upper()
        try:
            name, symbol = values()
            if not re.fullmatch(r'[A-Z]{3}', code) or code == 'CNY':
                raise ValueError('请输入3位英文币种代码；人民币统一使用已有的RMB。')
            if db.session.get(Currency, code):
                raise ValueError('该币种已存在，请直接编辑或启用。')
            try:
                fx_rates.currency_reference_rates(code)
            except Exception:
                raise ValueError('现有汇率来源暂时无法取得该币种汇率，请确认代码或稍后重试。')
            row = Currency(code=code, name=name, symbol=symbol, enabled=True, verified_at=datetime.utcnow())
            db.session.add(row)
            audit('create','currency',summary='新增币种 '+code,after=dict(code=code,name=name,symbol=symbol))
            db.session.commit()
        except (ValueError, IntegrityError) as exc:
            db.session.rollback()
            flash(str(exc) if isinstance(exc,ValueError) else '币种已由其他用户添加，请刷新。','danger')
            return redirect(url_for('currency_list'))
        flash('币种已添加，汇率来源已验证。','success')
        return redirect(url_for('currency_list'))

    @app.post('/currencies/<code>/edit')
    @login_required
    def currency_edit(code):
        row = db.session.get(Currency, code)
        if row is None:
            abort(404)
        if not password():
            return redirect(url_for('currency_list'))
        try:
            name, symbol = values()
        except ValueError as exc:
            flash(str(exc),'danger')
            return redirect(url_for('currency_list'))
        before = dict(name=row.name,symbol=row.symbol)
        row.name,row.symbol = name,symbol
        audit('update','currency',summary='编辑币种 '+code,before=before,after=dict(name=name,symbol=symbol))
        db.session.commit()
        flash('币种已更新，代码及历史汇率保持原值。','success')
        return redirect(url_for('currency_list'))

    @app.post('/currencies/<code>/toggle')
    @admin_required
    def currency_toggle(code):
        row = db.session.get(Currency,code)
        if row is None:
            abort(404)
        if code in ('USD','RMB'):
            flash('美元和人民币是基础换算币种，需要保持启用。','danger')
            return redirect(url_for('currency_list'))
        if not row.enabled:
            try:
                fx_rates.currency_reference_rates(code)
            except Exception:
                flash('无法取得该币种参考汇率，暂不能启用。','danger')
                return redirect(url_for('currency_list'))
            row.verified_at = datetime.utcnow()
        row.enabled = not row.enabled
        audit('update','currency',summary=('启用' if row.enabled else '停用')+'币种 '+code,after=dict(enabled=row.enabled))
        db.session.commit()
        return redirect(url_for('currency_list'))
