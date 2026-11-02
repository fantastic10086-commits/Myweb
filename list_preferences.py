"""Remember only explicitly supported list queries, separately per login account."""
from datetime import date, timedelta
from flask import request, redirect, url_for, session
from sqlalchemy import insert
from models import db, UserListPreference

REPORT = {'salesperson', 'date_from', 'date_to', 'preset'}
FILTERS = {
    'customer_detail': {'pi_number','date_from','date_to','product','amount_min','amount_max'},
    'customer_list': {'search','sort','sp','deal_min','deal_max','date_from','date_to','customer_type','follow','page'},
    'product_list': {'search','filter','sort','page'},
    'pi_list': REPORT | {'pi_number','customer_name','country','payment_status','order_status','customs_status','freight_forwarder','tracking_no','stage','transition'},
    'procurement_select': REPORT | {'pi_number','customer_name','country','order_status'},
    'packing_list_index': REPORT | {'pi_number','customer_name','country','status'},
    'fees_report': REPORT | {'profit_status'},
    'sales_stats': {'sp','date_from','date_to','preset'},
    'audit_logs': {'entity_type','action','page'},
    'finance_reconciliation': {'tab','month','basis','q','salesperson','account','category','status','checked','missing','page'},
}


def register_list_preferences(app, current_user):
    @app.before_request
    def remember_list_query():
        endpoint = request.endpoint
        if request.method != 'GET' or endpoint not in FILTERS:
            return
        user = current_user()
        if not user or not user.active:
            return
        if endpoint not in ('customer_list','customer_detail','product_list','pi_list','sales_stats','packing_list_index') and user.role != 'admin':
            return
        allowed = FILTERS[endpoint]
        scope = endpoint + (':' + str(request.view_args['id']) if endpoint == 'customer_detail' else '')
        route_args = request.view_args or {}
        stored = db.session.get(UserListPreference, (user.id, scope))
        legacy = session.pop('procurement_filters', {}) if endpoint == 'procurement_select' else {}
        if request.args.get('clear_filters') == '1':
            params = {}
        elif allowed.intersection(request.args):
            params = {key: request.args.getlist(key)[:20] for key in allowed if key in request.args}
            params = {key: [value[:500] for value in values] for key, values in params.items()}
            # Freeze relative presets to the date range selected at that time.
            if endpoint == 'finance_reconciliation' and (params.get('month') or [''])[0]:
                try:
                    date.fromisoformat(params['month'][0] + '-01')
                except ValueError:
                    return
            preset = (params.get('preset') or [''])[0]
            today = date.today()
            if preset in ('this_month','last_month','this_year'):
                start, end = today.replace(day=1), today
                if preset == 'last_month':
                    end = start - timedelta(days=1)
                    start = end.replace(day=1)
                elif preset == 'this_year':
                    start = today.replace(month=1, day=1)
                params.update(date_from=[start.isoformat()], date_to=[end.isoformat()])
                params.pop('preset', None)
        else:
            params = stored.parameters if stored else {key: [value] for key,value in legacy.items() if key in allowed}
            if params:
                if not stored:
                    _store(user.id, scope, params)
                restore = dict(params)
                if endpoint == 'customer_detail' and request.args.get('return_to'):
                    restore['return_to'] = request.args['return_to']
                return redirect(url_for(endpoint, **route_args, **restore))
            return
        if not stored or stored.parameters != params:
            _store(user.id, scope, params)
        if request.args.get('clear_filters') == '1':
            return redirect(url_for(endpoint, **route_args))

    def _store(user_id, endpoint, params):
        statement = insert(UserListPreference.__table__).prefix_with('OR REPLACE').values(
            user_id=user_id, endpoint=endpoint, parameters=params)
        db.session.execute(statement)
        db.session.commit()
