"""Shared, persistent ordering for operational PI lists."""
import math
from datetime import datetime, timedelta

from flask import request, url_for

from currency_utils import to_rmb
from list_preferences import FILTERS
from order_activity import effective_order_updates


def sort_order_list(pis, allow_amount=True):
    """Return sorted orders and the matching header/link context.

    Lists already load their filtered records for workflow calculations. Sort
    that complete set, never just the visible rows in the browser. Amounts use
    each order's saved business rate, without requesting live exchange rates.
    """
    keys = ('pi_number', 'updated_at', 'amount') if allow_amount else ('pi_number', 'updated_at')
    key = request.args.get('sort', 'updated_at')
    direction = request.args.get('direction', 'desc')
    if key not in keys:
        key, direction = 'updated_at', 'desc'
    if direction not in ('asc', 'desc'):
        direction = 'desc'
    updates = effective_order_updates(pis)
    ordered = sorted(pis, key=lambda pi: (updates.get(pi.id) or datetime.min, pi.id), reverse=True)
    if key == 'pi_number':
        ordered.sort(key=lambda pi: (pi.pi_number or '').casefold(), reverse=direction == 'desc')
    elif key == 'amount':
        amounts = {}
        for pi in pis:
            try:
                amount = to_rmb(pi, pi.grand_total)
                if math.isfinite(amount):
                    amounts[pi.id] = round(amount, 2)
            except (ValueError, TypeError, OverflowError):
                # Legacy orders missing a usable rate stay visible, at the end
                # in either direction; never silently compare unlike currencies.
                pass
        known = [pi for pi in ordered if pi.id in amounts]
        known.sort(key=lambda pi: amounts[pi.id], reverse=direction == 'desc')
        ordered = known + [pi for pi in ordered if pi.id not in amounts]
    elif direction == 'asc':
        ordered.sort(key=lambda pi: updates.get(pi.id) or datetime.min)

    params = {name: request.args.getlist(name) for name in FILTERS[request.endpoint]
              if name in request.args and name not in ('sort', 'direction')}
    urls = {name: url_for(request.endpoint, **dict(params, sort=name,
            direction=('asc' if direction == 'desc' else 'desc') if name == key else 'desc'))
            for name in keys}
    return ordered, dict(sort_key=key, sort_direction=direction, sort_urls=urls,
                        order_updated_at={pi_id: stamp + timedelta(hours=8) if stamp else None
                                          for pi_id, stamp in updates.items()})
