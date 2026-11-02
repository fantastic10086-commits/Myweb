"""Customer invoice adjustments, distinct from internal Expense costs."""
def adjustment_rows(pi):
    rows = getattr(pi, 'customer_adjustments', None)
    if rows is not None:
        return list(rows)
    amount = getattr(pi, 'shipping_cost', 0) or 0
    if not amount:
        return []
    return [{'amount': amount, 'name': getattr(pi, 'shipping_note', '') or 'Other Charges',
             'english': getattr(pi, 'shipping_note_en', '') or getattr(pi, 'shipping_note', '') or 'Other Charges'}]


def adjustment_description(pi):
    rows = adjustment_rows(pi)
    if len(rows) <= 1:
        return rows[0]['english'] if rows else ''
    currency = getattr(pi, 'currency', 'USD') or 'USD'
    return '\n'.join('%s: %s %+.2f' % (row['english'], currency, row['amount']) for row in rows)
