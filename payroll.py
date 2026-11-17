"""Monthly payroll. Confirmed slips keep the inputs, order breakdown and amounts as paid."""
import calendar
import hashlib
import json
import re
from collections import Counter
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from fx_rates import payment_to_usd
from models import (db, PI, Payment, PayrollDefaults, PayrollExclusion, PayrollHoliday,
                    PayrollProfile, PayrollSlip, User)

D = Decimal
CENT = D('0.01')
MODES = {'hourly': '按工时', 'monthly': '固定月薪'}
# Mainland statutory days for 2026, excluding days off in lieu and weekends of a holiday break.
STATUTORY = {date(2026, month, day): name
             for month, days, name in [(1, [1], '元旦'), (2, [16, 17, 18, 19], '春节'),
                                       (4, [5], '清明节'), (5, [1, 2], '劳动节'), (6, [19], '端午节'),
                                       (9, [25], '中秋节'), (10, [1, 2, 3], '国庆节')] for day in days}
TIERS = [(7500, '0.01'), (10000, '0.012'), (15000, '0.014'),
         (20000, '0.016'), (25000, '0.018')]


def migrate_payroll_accounts(engine):
    """Copy the previous release's payroll once, leaving the source intact for rollback."""
    with engine.begin() as conn:
        conn.exec_driver_sql('BEGIN IMMEDIATE')
        tables = {r[0] for r in conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'payroll_profiles' not in tables or 'user_payroll_profiles' in tables:
            return
        users = conn.exec_driver_sql('SELECT id, username, salesperson_name FROM users').fetchall()
        staff = conn.exec_driver_sql("""
            SELECT old.employee_id, s.name
              FROM (SELECT employee_id FROM payroll_profiles UNION SELECT employee_id FROM payroll_slips) old
              LEFT JOIN salespersons s ON s.id = old.employee_id
        """).fetchall()
        PayrollProfile.__table__.create(conn)
        PayrollSlip.__table__.create(conn)
        for old_id, name in staff:
            if not name:
                raise RuntimeError(f'工资档案 {old_id} 缺少原业务员，无法对应用户。')
            matches = [uid for uid, _, binding in users if binding == name]
            if not matches:
                matches = [uid for uid, username, binding in users if not binding and username == name]
            if len(matches) != 1:
                raise RuntimeError(f'工资档案「{name}」无法唯一对应用户，请核对账号关联业务员后重试。')
            params = (matches[0], old_id)
            conn.exec_driver_sql("""
                INSERT INTO user_payroll_profiles (user_id, staff_no, mode, base, social, fund)
                SELECT ?, staff_no, mode, base, social, fund FROM payroll_profiles WHERE employee_id=?
            """, params)
            conn.exec_driver_sql("""
                INSERT INTO user_payroll_slips (user_id, month, inputs, confirmed, confirmed_by, confirmed_at, version)
                SELECT ?, month, inputs, confirmed, confirmed_by, confirmed_at, version
                FROM payroll_slips WHERE employee_id=?
            """, params)


def money(value):
    return D(value).quantize(CENT, rounding=ROUND_HALF_UP)


def number(form, key, label, maximum='999999999.99', optional=False):
    raw = form.get(key, '').strip()
    if optional and not raw:
        return None
    if not re.fullmatch(r'[0-9]{1,9}(?:\.[0-9]{1,2})?', raw) or D(raw) > D(maximum):
        raise ValueError(f'请检查「{label}」，可填 0 至 {maximum}，最多两位小数。')
    return str(money(raw))


def month_dates(value):
    if not re.fullmatch(r'20[0-9]{2}-(?:0[1-9]|1[0-2])', value):
        abort(400, '工资月份无效')
    first = date.fromisoformat(value + '-01')
    last = first.replace(day=calendar.monthrange(first.year, first.month)[1])
    return first, last, (last + timedelta(days=1)).replace(day=15)


def paid_dates(first, last):
    days = {day: name for day, name in STATUTORY.items() if first <= day <= last}
    days.update((item.day, item.name) for item in PayrollHoliday.query.filter(
        PayrollHoliday.day.between(first, last)).all())
    return {day.isoformat(): days[day] for day in sorted(days)}


def month_orders(receipt_query, first, last, employee=None):
    query, received = receipt_query()
    query = (query.add_entity(PayrollExclusion).outerjoin(PayrollExclusion, PI.id == PayrollExclusion.pi_id)
             .filter(received.between(first, last)))
    if employee is not None:
        query = query.filter(PI.salesperson == employee)
    grouped = {}
    for payment, pi, _, excluded in query.order_by(PI.id, Payment.id).all():
        orders = grouped.setdefault(pi.salesperson, {})
        if pi.id not in orders:
            orders[pi.id] = dict(id=pi.id, pi=pi.pi_number, customer=pi.customer.name if pi.customer else '',
                                 usd=D(0), reason=excluded.reason if excluded else '',
                                 operator=excluded.operator if excluded else '',
                                 changed_at=(excluded.changed_at + timedelta(hours=8)).isoformat(timespec='seconds')
                                 if excluded else '')
        orders[pi.id]['usd'] += D(str(payment_to_usd(payment, pi)))
    return grouped


def commission(orders):
    all_usd = money(sum(row['usd'] for row in orders))
    eligible = money(sum(row['usd'] for row in orders if not row['reason']))
    rate = next((D(rate) for limit, rate in TIERS if eligible <= limit), D('0.02'))
    return dict(total_usd=str(all_usd), excluded_usd=str(all_usd - eligible), eligible=str(eligible),
                percent=format(rate * 100, 'f').rstrip('0').rstrip('.'), commission=str(money(eligible * rate * 7)),
                orders=[dict(row, usd=str(money(row['usd']))) for row in orders])


def settled_pi_ids(slips):
    return {row['id'] for slip in slips if slip.confirmed
            for row in slip.confirmed['orders'] if not row['reason']}


def user_commission(user, orders, binding_counts, settled):
    linked_orders = orders.get(user.salesperson_name, {}) if user.salesperson_name else {}
    rows = [row for row in linked_orders.values() if row['id'] not in settled]
    conflict = bool(rows and binding_counts[user.salesperson_name] > 1)
    return dict(commission([] if conflict else rows), binding_conflict=conflict)


def calculate(profile, inputs, days, default_social, sales):
    required, actual = D(inputs['required']), D(inputs['actual'])
    hours = D(inputs['hours']) if inputs['hours'] is not None else actual * 8
    paid = D(inputs['paid']) if inputs['paid'] is not None else D(len(days))
    unpaid = D(inputs['unpaid']) if inputs['unpaid'] is not None else max(D(0), required - actual)
    if profile.mode == 'hourly':
        earned = profile.base / D('23.75') / 8 * (hours + paid * 8)
    else:
        earned = max(D(0), profile.base - profile.base / D('21.75') * unpaid)
    earned = money(earned)
    meal = money(actual * 10)
    award = 200 if required > 0 and actual >= required else 0
    social = inputs['social'] if inputs['social'] is not None else profile.social
    if social is None:
        social = default_social
    fund = money(inputs['fund'] if inputs['fund'] is not None else profile.fund)
    gross = earned + meal + award + D(sales['commission']) + D(inputs['merit']) + D(inputs['bonus'])
    return dict(sales, mode=profile.mode, base=str(profile.base), staff_no=profile.staff_no, days=days,
                required=str(required), actual=str(actual), hours=str(hours), paid=str(paid), unpaid=str(unpaid),
                earned=str(earned), meal=str(meal), award=str(award), merit=inputs['merit'], bonus=inputs['bonus'],
                social=str(money(social)) if social is not None else None, fund=str(fund), gross=str(gross),
                net=str(gross - money(social) - fund) if social is not None else None)


def token(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def check_current(value):
    if request.form.get('revision') != token(value):
        abort(409, '页面中的数据已更新，请重新打开本页，核对后再保存。')


def profile_data(profile):
    if profile:
        return dict(mode=profile.mode, base=str(profile.base), staff_no=profile.staff_no,
                    fund=str(profile.fund), social=str(profile.social) if profile.social is not None else None)


def register_payroll(app, *, admin_required, current_user, audit, receipt_query):
    bp = Blueprint('payroll', __name__, url_prefix='/admin/payroll')

    @bp.before_request
    @admin_required
    def protect():
        if request.method == 'POST':
            # Serialize the preview check and snapshot with concurrent receipt/configuration writes in SQLite.
            db.session.connection().exec_driver_sql('BEGIN IMMEDIATE')

    def default_social():
        settings = db.session.get(PayrollDefaults, 1)
        return settings.social if settings else None

    def period():
        today = (datetime.utcnow() + timedelta(hours=8)).date()
        previous = today.replace(day=1) - timedelta(days=1)
        month = request.args.get('month', previous.strftime('%Y-%m'))
        return month, month_dates(month)

    def employee_page(month, user_id, **kwargs):
        return url_for('payroll.sheet', month=month, user_id=user_id, **kwargs)

    def restore_order(excluded):
        audit('restore', 'payroll_commission', excluded.pi_id, '恢复 PI 计提', before={'reason': excluded.reason})
        db.session.delete(excluded)

    def sheet_sales(user, month, first, last):
        if not user.salesperson_name:
            return commission([])
        orders = month_orders(receipt_query, first, last, user.salesperson_name)
        counts = {user.salesperson_name: User.query.filter_by(salesperson_name=user.salesperson_name).count()}
        slips = PayrollSlip.query.filter_by(month=month).filter(PayrollSlip.confirmed.isnot(None)).all()
        return user_commission(user, orders, counts, settled_pi_ids(slips))

    @bp.get('/<month>/<int:legacy_employee_id>')
    def legacy_sheet(month, legacy_employee_id):
        month_dates(month)
        return redirect(url_for('payroll.index', month=month))

    @bp.get('')
    def index():
        month, (first, last, payday) = period()
        employees = User.query.order_by(User.active.desc(), User.username).all()
        profiles = {p.user_id: p for p in PayrollProfile.query.all()}
        slips = {s.user_id: s for s in PayrollSlip.query.filter_by(month=month).all()}
        orders = month_orders(receipt_query, first, last)
        days, social = paid_dates(first, last), default_social()
        counts = Counter(emp.salesperson_name for emp in employees if emp.salesperson_name)
        settled = settled_pi_ids(slips.values())
        show_inactive = request.args.get('inactive') == '1'
        rows = []
        for emp in employees:
            if not emp.active and emp.id not in slips and not show_inactive:
                continue
            slip, profile = slips.get(emp.id), profiles.get(emp.id)
            result = slip.confirmed if slip else None
            if result is None:
                sales = user_commission(emp, orders, counts, settled)
                result = calculate(profile, slip.inputs, days, social, sales) if slip and profile else sales
            rows.append(dict(emp=emp, result=result, profile=profile, slip=slip))
        return render_template('payroll/index.html', month=month, payday=payday, rows=rows, modes=MODES,
                               show_inactive=show_inactive, has_inactive=any(not u.active for u in employees))

    @bp.route('/settings', methods=['GET', 'POST'])
    def settings():
        month, (first, _, _) = period()
        year = first.year
        defaults = default_social()
        employees = User.query.order_by(User.active.desc(), User.username).all()
        profiles = {p.user_id: p for p in PayrollProfile.query.all()}
        error = ''
        if request.method == 'POST':
            action = request.form.get('action')
            try:
                if action == 'social':
                    check_current(defaults)
                    amount = number(request.form, 'social', '公司默认社保')
                    db.session.merge(PayrollDefaults(id=1, social=D(amount)))
                    audit('update', 'payroll_defaults', 1, '调整默认个人社保', before={'social': defaults}, after={'social': amount})
                elif action == 'user_profile':
                    emp = db.get_or_404(User, request.form.get('user_id', type=int))
                    profile = profiles.get(emp.id)
                    before = profile_data(profile)
                    check_current([emp.id, before])
                    mode = request.form.get('mode')
                    if mode not in MODES:
                        raise ValueError('请选择计薪方式。')
                    staff_no = request.form.get('staff_no', '').strip()
                    if len(staff_no) > 32:
                        raise ValueError('工号最多 32 个字符。')
                    base = D(number(request.form, 'base', '基本工资'))
                    social = number(request.form, 'social', '个人社保', optional=True)
                    fund = number(request.form, 'fund', '个人公积金')
                    profile = profile or PayrollProfile(user_id=emp.id)
                    profile.mode, profile.staff_no, profile.base = mode, staff_no, base
                    profile.social, profile.fund = D(social) if social is not None else None, D(fund)
                    db.session.add(profile)
                    audit('update', 'user_payroll_profile', emp.id, '保存员工计薪设置', before=before, after=profile_data(profile))
                elif action == 'restore_order':
                    excluded = db.get_or_404(PayrollExclusion, request.form.get('pi_id', type=int))
                    check_current([excluded.reason, excluded.operator, excluded.changed_at])
                    restore_order(excluded)
                elif action in ('add_day', 'remove_day'):
                    day = date.fromisoformat(request.form.get('day', ''))
                    if day.year != year or day in STATUTORY:
                        raise ValueError('请在当前年份中选择一个未预置的日期。')
                    holiday = db.session.get(PayrollHoliday, day)
                    if action == 'add_day':
                        name = request.form.get('name', '').strip()
                        if holiday or not 1 <= len(name) <= 60:
                            raise ValueError('该日期已存在，或假期名称为空或过长。')
                        db.session.add(PayrollHoliday(day=day, name=name))
                    else:
                        if not holiday:
                            abort(409, '该日期已移除。')
                        check_current(holiday.name)
                        name = holiday.name
                        db.session.delete(holiday)
                    audit(action, 'payroll_holiday', None, f'{day} {name}')
                else:
                    abort(400)
            except ValueError as exc:
                db.session.rollback()
                error = '请输入有效日期。' if 'isoformat' in str(exc) else str(exc)
            else:
                db.session.commit()
                flash('工资设置已保存。', 'success')
                return redirect(url_for('payroll.settings', month=month))
        days = paid_dates(date(year, 1, 1), date(year, 12, 31))
        exclusions = (db.session.query(PayrollExclusion, PI.pi_number).join(PI, PayrollExclusion.pi_id == PI.id)
                      .filter(PI.deleted_at.is_(None)).order_by(PI.pi_number).all())
        return render_template('payroll/settings.html', month=month, employees=employees, profiles=profiles,
                               modes=MODES, defaults=defaults, days=days, statutory={d.isoformat() for d in STATUTORY},
                               exclusions=exclusions, error=error, year=year, token=token,
                               profile_data=profile_data), (422 if error else 200)

    @bp.route('/<month>/users/<int:user_id>', methods=['GET', 'POST'])
    def sheet(month, user_id):
        first, last, payday = month_dates(month)
        emp = db.get_or_404(User, user_id)
        slip = db.session.get(PayrollSlip, (month, user_id))
        frozen = slip.confirmed if slip else None
        if request.method == 'POST' and frozen:
            abort(409, '本月工资已确认。')
        profile = db.session.get(PayrollProfile, emp.id)
        defaults, days = default_social(), paid_dates(first, last)
        if frozen:
            sales = result = frozen
        else:
            sales = sheet_sales(emp, month, first, last)
            result = calculate(profile, slip.inputs, days, defaults, sales) if slip and profile else None
            if result:
                result['employee'] = emp.username
                result['salesperson'] = emp.salesperson_name
        revision = [emp.id, emp.username, emp.salesperson_name, slip.version if slip else 0, profile_data(profile), defaults, days, sales]
        inputs = dict(slip.inputs) if slip else dict(required='', actual='', merit='0', bonus='0')
        error = ''
        if request.method == 'POST':
            check_current(revision)
            action = request.form.get('action')
            if not profile:
                abort(409, '请先设置该员工的基本工资和计薪方式。')
            if action == 'confirm':
                if sales.get('binding_conflict'):
                    abort(409, '多个用户关联了同一业务员，请先核对提成归属。')
                if not result or result['net'] is None:
                    abort(409, '请先保存考勤并核对个人社保。')
                slip.confirmed, slip.confirmed_by, slip.confirmed_at = result, current_user().username, datetime.utcnow()
                audit('confirm', 'user_payroll_slip', emp.id, f'确认 {month} 工资', after={'gross': result['gross'], 'net': result['net']})
            elif action == 'save':
                fields = [('required', '应出勤天数', last.day, False), ('actual', '实际出勤天数', last.day, False),
                          ('paid', '带薪假天数', last.day, True), ('hours', '实际工时', last.day * 24, True),
                          ('unpaid', '无薪缺勤天数', last.day, True), ('social', '社保', 999999999, True),
                          ('fund', '公积金', 999999999, True), ('merit', '绩效', 999999999, False),
                          ('bonus', '奖金', 999999999, False)]
                inputs = {key: request.form.get(key, '') for key, *_ in fields}
                try:
                    parsed = {key: number(inputs, key, label, limit, optional) for key, label, limit, optional in fields}
                    if parsed['unpaid'] is not None and D(parsed['unpaid']) > D(parsed['required']):
                        raise ValueError('无薪缺勤天数不能超过应出勤天数。')
                except ValueError as exc:
                    error = str(exc)
                else:
                    before = slip.inputs if slip else None
                    slip = slip or PayrollSlip(month=month, user_id=emp.id)
                    slip.inputs = parsed
                    db.session.add(slip)
                    audit('update', 'user_payroll_slip', emp.id, f'保存 {month} 工资草稿', before=before, after=parsed)
            else:
                abort(400)
            if not error:
                db.session.commit()
                flash('工资已确认。' if action == 'confirm' else '已保存并计算。', 'success')
                return redirect(employee_page(month, emp.id))
            db.session.rollback()
        return render_template('payroll/sheet.html', emp=emp, month=month, payday=payday, slip=slip, locked=bool(frozen),
                               result=result, sales=sales, inputs=inputs, modes=MODES, profile=profile, days=days,
                               defaults=defaults, error=error, token=token, revision=token(revision),
                               show_orders=request.args.get('orders') == '1'), (422 if error else 200)

    @bp.post('/<month>/users/<int:user_id>/orders/<int:pi_id>')
    def exclusion(month, user_id, pi_id):
        first, last, _ = month_dates(month)
        emp = db.get_or_404(User, user_id)
        slip = db.session.get(PayrollSlip, (month, emp.id))
        if slip and slip.confirmed:
            abort(409, '本月工资已确认。请从未确认月份的提成明细处理。')
        sales = sheet_sales(emp, month, first, last)
        order = next((row for row in sales['orders'] if row['id'] == pi_id), None)
        if not order:
            abort(404)
        check_current([order['reason'], order['operator'], order['changed_at']])
        excluded = db.session.get(PayrollExclusion, pi_id)
        if request.form.get('action') == 'exclude' and not excluded:
            reason = request.form.get('reason', '').strip()
            if not 1 <= len(reason) <= 200:
                flash('请填写排除原因，最多 200 字。', 'warning')
                return redirect(employee_page(month, emp.id, orders=1, _anchor='commission'))
            db.session.add(PayrollExclusion(pi_id=pi_id, reason=reason, operator=current_user().username))
            audit('exclude', 'payroll_commission', pi_id, '该 PI 不计提成', after={'reason': reason})
        elif request.form.get('action') == 'restore' and excluded:
            restore_order(excluded)
        else:
            abort(409, '该 PI 的计提状态已改变。')
        db.session.commit()
        flash('已更新该 PI 的提成设置。', 'success')
        return redirect(employee_page(month, emp.id, orders=1, _anchor='commission'))

    app.register_blueprint(bp)
