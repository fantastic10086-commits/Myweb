"""Backfill each historical receipt using its own Beijing arrival/registration date.
Preview by default. Run with --apply after a backup and the service environment loaded.
External quotes are resolved before one atomic database write. Reruns skip saved rates.
"""
import argparse
import json
import os
import sys
from datetime import timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def reprice(application, apply=False):
    from models import db, Payment, PI, FinanceReview, Customer
    from sqlalchemy import text
    from fx_rates import receipt_performance_snapshot, payment_to_usd

    def read_rows():
        rows = (db.session.query(Payment, PI).join(PI, Payment.pi_id == PI.id)
                .filter(Payment.deleted_at.is_(None), PI.deleted_at.is_(None)).all())
        dates = dict(db.session.query(FinanceReview.record_id, FinanceReview.occurred_on)
                     .filter(FinanceReview.kind == 'payment').all())
        return rows, dates

    def facts(payment, pi, dates):
        day = dates.get(payment.id)
        if day is None:
            if payment.created_at is None:
                raise ValueError('回款缺少到账和登记日期，无法推断汇率。')
            day = (payment.created_at + timedelta(hours=8)).date()
        return ((pi.currency or 'USD').upper(), day, payment.amount, payment.fee)

    with application.app.app_context():
        rows, dates = read_rows()
        pending = {p.id: facts(p, pi, dates) for p, pi in rows
                   if not p.performance_source or
                   (p.performance_source != 'Frankfurter' and p.performance_source != 'USD原币') or
                   p.performance_usd_rate is None or p.performance_date != facts(p, pi, dates)[1]}
        db.session.rollback()
    # No business/customer data leaves the server; only currency/date queries.
    quotes = {}
    for currency, day, _, _ in pending.values():
        key = currency, day
        if key not in quotes:
            quotes[key] = receipt_performance_snapshot(currency, day)
    with application.app.app_context():
        db.session.execute(text('BEGIN IMMEDIATE'))
        try:
            rows, dates = read_rows()
            selected = [(p, pi) for p, pi in rows if p.id in pending]
            if len(selected) != len(pending) or any(facts(p, pi, dates) != pending[p.id] for p, pi in selected):
                raise ValueError('回款在准备汇率期间发生变化，请重新运行。')
            before = sum(payment_to_usd(p, pi) for p, pi in selected)
            counts = {}
            reference_dates = set()
            for payment, pi in selected:
                currency, day, _, _ = pending[payment.id]
                snapshot = quotes[currency, day]
                for key, value in snapshot.items():
                    setattr(payment, key, value)
                reference_dates.add(snapshot['performance_reference_date'])
                counts[currency] = counts.get(currency, 0) + 1
            after = sum(payment_to_usd(p, pi) for p, pi in selected)
            summary = dict(applied=apply, receipt_counts=counts, count=len(selected),
                           date_rule='实际到账日期；缺失则北京时间登记日期',
                           reference_dates=sorted(reference_dates),
                           before_usd=round(before, 2), after_usd=round(after, 2))
            if apply:
                for customer in Customer.query.all():
                    application._recalculate_customer_deal(customer)
                application._audit('update', 'payment_performance_reprice',
                    summary='按各笔到账日期参考汇率重算历史回款业绩', after=summary)
                db.session.commit()
            else:
                db.session.rollback()
            return summary
        except Exception:
            db.session.rollback()
            raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    import app as application
    print(json.dumps(reprice(application, args.apply), ensure_ascii=False))


if __name__ == '__main__':
    main()
