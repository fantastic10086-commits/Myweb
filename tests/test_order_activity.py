"""Business update ordering against real records in a disposable database.

Run independently: venv/bin/python tests/test_order_activity.py
"""
import json
import os
import unittest
from datetime import date, datetime, timedelta

from sqlalchemy import event, select

import security_smoke as fixture
from models import (
    AuditLog, Customer, CustomerFile, CustomsDocument, Expense, FinanceReview,
    PackingBatch, PackingList, Payment, PI, ProcurementAttachment, ShippingBatch,
    User, db,
)
from order_activity import effective_order_updates
from order_list_sorting import sort_order_list


application = fixture.application
CREATED = datetime(2026, 1, 1, 1, 0)
BASELINE = datetime(2026, 1, 2, 2, 0)
OTHER_UPDATE = datetime(2026, 1, 5, 5, 0)
CHANGED = datetime(2026, 1, 8, 8, 0)
LATER = datetime(2026, 1, 9, 9, 0)


class OrderActivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.SecuritySmokeTests.setUpClass()

    def setUp(self):
        self.context = application.app.app_context()
        self.context.push()
        self.addCleanup(self.context.pop)
        self.addCleanup(db.session.remove)
        self.pi = self.make_pi(self._testMethodName)
        self.other = self.make_pi(self._testMethodName + '-other', OTHER_UPDATE)
        db.session.commit()
        # Keep scalar state loaded so assertions cannot trigger autoflush.
        self.pi_id, self.other_id = self.pi.id, self.other.id

    def make_pi(self, suffix, updated=BASELINE):
        pi = PI(pi_number='PI-ACTIVITY-' + suffix,
                customer_id=fixture.SecuritySmokeTests.alice_customer,
                salesperson='Alice', currency='USD', total_amount=100,
                created_at=CREATED, updated_at=updated,
                issue_date=date(2030, 12, 31))
        db.session.add(pi)
        db.session.flush()
        return pi

    def audit(self, kind, record_id, action='update', stamp=CHANGED, before=None):
        row = AuditLog(entity_type=kind, entity_id=record_id, action=action,
                       username='alice', created_at=stamp,
                       before_json=json.dumps(before) if before is not None else '')
        db.session.add(row)
        return row

    def assert_activity(self, expected):
        updates = effective_order_updates([self.pi, self.other])
        self.assertEqual(updates[self.pi_id], expected)
        self.assertEqual(updates[self.other_id], OTHER_UPDATE)
        with application.app.test_request_context('/pi/list'):
            orders, _ = sort_order_list([self.pi, self.other])
        expected_first = self.pi_id if expected > OTHER_UPDATE else self.other_id
        self.assertEqual(orders[0].id, expected_first)

    def test_packing_plan_and_independent_batch_edits_move_order_first(self):
        plan = PackingList(pi_id=self.pi_id, created_at=CREATED, updated_at=CHANGED,
                           packing_date=date(2030, 12, 30))
        db.session.add(plan)
        db.session.commit()
        self.assert_activity(CHANGED)
        batch = PackingBatch(packing_list_id=plan.id, batch_no=1,
                             created_at=CREATED, updated_at=LATER,
                             planned_shipping_date=date(2031, 1, 1))
        db.session.add(batch)
        db.session.commit()
        self.assert_activity(LATER)
        self.assertEqual(self.pi.updated_at, BASELINE)

    def test_shipping_record_edit_uses_edit_timestamp_not_shipping_date(self):
        batch = ShippingBatch(pi_id=self.pi_id, batch_no=1, status='shipped',
                              recorded_at=CHANGED, updated_at=CREATED,
                              shipping_date=date(2025, 1, 1))
        db.session.add(batch)
        db.session.commit()
        self.assert_activity(CHANGED)
        batch.note = '更正物流资料'
        batch.updated_at = LATER
        db.session.commit()
        self.assert_activity(LATER)

    def test_customs_edits_and_procurement_attachment_deletion_are_activity(self):
        document = CustomsDocument(pi_id=self.pi_id, created_at=CREATED, updated_at=CHANGED)
        attachment = ProcurementAttachment(pi_id=self.pi_id,
            stored_name=self._testMethodName + '.png', original_name='采购.png',
            created_at=CREATED, deleted_at=LATER)
        db.session.add_all([document, attachment])
        db.session.commit()
        self.assert_activity(LATER)
        self.assertEqual(effective_order_updates([self.pi])[self.pi_id], LATER)

    def test_expense_creation_and_edit_audit_move_order_first(self):
        expense = Expense(pi_id=self.pi_id, category='运费', amount=12,
                          currency='RMB', created_at=CHANGED)
        db.session.add(expense)
        db.session.commit()
        self.assert_activity(CHANGED)
        expense.amount = 18
        self.audit('expense', expense.id, stamp=LATER)
        db.session.commit()
        self.assert_activity(LATER)

    def test_physically_deleted_expense_survives_in_audit_snapshot(self):
        expense = Expense(pi_id=self.pi_id, category='运费', amount=12,
                          currency='RMB', created_at=CREATED)
        db.session.add(expense)
        db.session.commit()
        expense_id = expense.id
        self.audit('expense', expense_id, action='delete', before=expense.to_dict())
        # Malformed historic rows must not break a list or attach to this PI.
        malformed = self.audit('expense', expense_id + 1000, action='delete', stamp=LATER)
        malformed.before_json = '{not valid JSON'
        self.audit('expense', expense_id + 1001, action='delete', stamp=LATER)
        db.session.delete(expense)
        db.session.commit()
        self.assertIsNone(db.session.get(Expense, expense_id))
        self.assert_activity(CHANGED)

    def test_payment_edit_and_date_audit_use_audit_time(self):
        payment = Payment(pi_id=self.pi_id, amount=20, created_at=CREATED,
                          performance_date=date(2025, 1, 1))
        db.session.add(payment)
        db.session.commit()
        self.audit('payment', payment.id)
        payment.amount = 21
        db.session.commit()
        self.assert_activity(CHANGED)
        self.audit('finance_payment_date', payment.id, stamp=LATER)
        db.session.commit()
        self.assert_activity(LATER)

    def test_finance_date_and_expense_review_audits_both_change_order_activity(self):
        payment = Payment(pi_id=self.pi_id, amount=20, created_at=CREATED)
        expense = Expense(pi_id=self.pi_id, category='运费', amount=1, created_at=CREATED)
        db.session.add_all([payment, expense])
        db.session.flush()
        payment_review = FinanceReview(kind='payment', record_id=payment.id,
                                       occurred_on=date(2030, 12, 31))
        expense_review = FinanceReview(kind='expense', record_id=expense.id,
                                       paid_on=date(2030, 12, 31))
        db.session.add_all([payment_review, expense_review])
        db.session.commit()
        # The accounting dates themselves are not evidence of a recent edit.
        self.assert_activity(BASELINE)
        self.audit('finance_review', payment_review.id)
        db.session.commit()
        self.assert_activity(CHANGED)
        self.audit('finance_review', expense_review.id, stamp=LATER)
        db.session.commit()
        self.assert_activity(LATER)

    def test_export_preview_and_automatically_archived_files_do_not_change_activity(self):
        for kind in ('pi', 'procurement'):
            for action in ('export', 'preview', 'download', 'view'):
                self.audit(kind, self.pi_id, action=action, stamp=LATER)
        automatic = CustomerFile(customer_id=self.pi.customer_id, pi_id=self.pi_id,
            stored_name=self._testMethodName + '-auto.pdf', original_name='PI.pdf',
            created_by='系统自动归档', note='PI PDF', created_at=CHANGED, deleted_at=LATER)
        contract = CustomerFile(customer_id=self.pi.customer_id, pi_id=self.pi_id,
            stored_name=self._testMethodName + '-contract.xlsx', original_name='采购合同.xlsx',
            created_by='alice', note='采购合同', created_at=CHANGED, deleted_at=LATER)
        db.session.add_all([automatic, contract])
        db.session.flush()
        for file in (automatic, contract):
            self.audit('customer_file', file.id, action='create', stamp=LATER)
            self.audit('customer_file', file.id, action='soft_delete', stamp=LATER)
        db.session.commit()
        self.assert_activity(BASELINE)

    def test_manual_customer_order_attachment_is_business_activity(self):
        uploaded = CustomerFile(customer_id=self.pi.customer_id, pi_id=self.pi_id,
            stored_name=self._testMethodName + '.pdf', original_name='报关资料.pdf',
            created_by='alice', note='', created_at=CHANGED)
        db.session.add(uploaded)
        db.session.commit()
        self.assert_activity(CHANGED)
        self.audit('customer_file', uploaded.id, action='update', stamp=LATER)
        db.session.commit()
        self.assert_activity(LATER)

    def test_generated_pdf_excel_cache_and_real_archive_keep_original_activity(self):
        # Exercise the real automatic archive event, not only synthetic files.
        pdf_name = self._testMethodName + '.pdf'
        excel_name = self._testMethodName + '.xlsx'
        for name in (pdf_name, excel_name):
            with open(os.path.join(application.app.config['PDF_DIR'], name), 'wb') as target:
                target.write(('test cache ' + name).encode())
        self.pi.pdf_path = pdf_name
        self.pi.excel_path = excel_name
        db.session.commit()
        archived = CustomerFile.query.filter_by(pi_id=self.pi_id).all()
        self.assertEqual(len(archived), 2)
        self.assertTrue(all(file.created_by == '系统自动归档' for file in archived))
        self.assertEqual(self.pi.updated_at, BASELINE)
        self.assert_activity(BASELINE)

    def test_real_pi_notes_change_updates_timestamp_but_noop_save_does_not(self):
        before = datetime.utcnow()
        self.pi.notes = '业务员更新订单要求'
        db.session.commit()
        updated = self.pi.updated_at
        self.assertGreaterEqual(updated, before)
        self.assertLessEqual(updated, datetime.utcnow())
        self.assert_activity(updated)
        version = self.pi.version
        self.pi.notes = self.pi.notes
        db.session.commit()
        self.assertEqual(self.pi.updated_at, updated)
        self.assertEqual(self.pi.version, version)

    def test_queries_do_not_flush_pending_changes_or_change_optimistic_versions(self):
        pi_id, version, stamp = self.pi.id, self.pi.version, self.pi.updated_at
        self.other.id, self.other.updated_at, self.other.created_at
        self.pi.notes = '尚未保存的输入'
        pending = Customer(name='Pending activity test customer')
        db.session.add(pending)
        statements = []

        def track(connection, cursor, statement, parameters, context, executemany):
            statements.append(statement.strip().split()[0].upper())

        event.listen(db.engine, 'before_cursor_execute', track)
        try:
            self.assert_activity(BASELINE)
            self.assertEqual(effective_order_updates([]), {})
        finally:
            event.remove(db.engine, 'before_cursor_execute', track)
        self.assertFalse({'INSERT', 'UPDATE', 'DELETE'} & set(statements), statements)
        self.assertIsNone(pending.id)
        self.assertEqual(self.pi.version, version)
        self.assertEqual(self.pi.updated_at, stamp)
        with db.engine.connect() as connection:
            persisted = connection.execute(select(PI.notes, PI.version, PI.updated_at)
                                           .where(PI.id == pi_id)).one()
        self.assertEqual(tuple(persisted), ('', version, stamp))
        self.assertEqual(self.pi.notes, '尚未保存的输入')
        db.session.rollback()

    def test_over_one_thousand_orders_respect_sqlite_bind_limit_and_sort_across_batches(self):
        prefix = 'PI-ACTIVITY-BATCH-'
        db.session.execute(PI.__table__.insert(), [dict(
            pi_number=prefix + str(index).zfill(4),
            customer_id=fixture.SecuritySmokeTests.alice_customer,
            salesperson='Alice', currency='USD', total_amount=100,
            issue_date=date(2026, 1, 1), created_at=CREATED, updated_at=BASELINE,
        ) for index in range(1001)])
        db.session.commit()
        orders = PI.query.filter(PI.pi_number.startswith(prefix)).order_by(PI.id).all()
        self.assertEqual(len(orders), 1001)
        for index, stamp in ((0, CHANGED), (500, LATER), (1000, OTHER_UPDATE)):
            self.audit('pi', orders[index].id, stamp=stamp)
        db.session.commit()
        # Reload expired scalars before counting the aggregation's SQL queries.
        orders = PI.query.filter(PI.pi_number.startswith(prefix)).order_by(PI.id).all()
        statements = []

        def track(connection, cursor, statement, parameters, context, executemany):
            statements.append((statement.strip().split()[0].upper(), len(parameters)))

        event.listen(db.engine, 'before_cursor_execute', track)
        try:
            with application.app.test_request_context('/pi/list'):
                ordered, context = sort_order_list(orders)
            self.assertEqual(len(statements), 3)
            self.assertTrue(all(command == 'SELECT' and count <= 999
                                for command, count in statements), statements)
            statements.clear()
            effective_order_updates(orders[:2])
            self.assertEqual(len(statements), 1)
        finally:
            event.remove(db.engine, 'before_cursor_execute', track)
        self.assertEqual([pi.id for pi in ordered[:3]],
                         [orders[500].id, orders[0].id, orders[1000].id])
        self.assertEqual(len(context['order_updated_at']), 1001)
        self.assertEqual(context['order_updated_at'][orders[500].id], LATER + timedelta(hours=8))
        self.assertEqual(context['order_updated_at'][orders[1000].id], OTHER_UPDATE + timedelta(hours=8))
        self.assertEqual(context['order_updated_at'][orders[999].id], BASELINE + timedelta(hours=8))
        self.assertFalse(db.session.dirty)

    def test_read_only_preview_export_pages_do_not_mutate_order(self):
        client = application.app.test_client()
        user = User.query.filter_by(username='alice').one()
        with client.session_transaction() as session:
            session.update(user_id=user.id, auth_version=user.auth_version)
        version, pi_id = self.pi.version, self.pi_id
        for suffix in ('preview', 'export'):
            response = client.get('/pi/%s/%s' % (pi_id, suffix))
            self.assertEqual(response.status_code, 200, response.get_data(as_text=True)[:500])
        # Requests may replace scoped-session objects; reload before asserting.
        self.pi = db.session.get(PI, pi_id)
        self.assertEqual(self.pi.version, version)
        self.assertEqual(self.pi.updated_at, BASELINE)
        self.assert_activity(BASELINE)


if __name__ == '__main__':
    unittest.main()
