"""Read-only, shared business-activity timestamps for order lists.

Related records do not all update PI.updated_at.  Aggregate their persisted
timestamps and write audits without changing orders or optimistic-lock versions.
Business dates (invoice/receipt/shipping dates) are deliberately not timestamps
of edits.  Missing historical evidence falls back to the PI creation time.
"""
from sqlalchemy import and_, case, func, select, union_all

from models import (
    AuditLog, CustomerFile, CustomsDocument, Expense, FinanceReview, PackingBatch,
    PackingList, Payment, Procurement, ProcurementAttachment, ShippingBatch, db,
)


_WRITE_ACTIONS = ('create', 'update', 'save', 'complete', 'confirm', 'unlock',
                  'cancel', 'delete', 'soft_delete', 'restore')


def effective_order_updates(pis):
    """Return {PI id: latest known UTC datetime (or None)} in batch queries.

    No lazy-loaded relationships are accessed, and no backfill or write occurs.
    The caller should pass persisted PI objects whose scalar fields are loaded.
    """
    updates = {}
    for pi in pis:
        if pi.id is not None:
            times = [value for value in (pi.updated_at, pi.created_at) if value]
            updates[pi.id] = max(times) if times else None
    if not updates:
        return updates

    sources = []

    def timestamp_source(model, column, *conditions):
        sources.append(select(model.pi_id.label('pi_id'), column.label('changed_at'))
                       .where(column.isnot(None), *conditions))

    for model, columns in (
        (PackingList, ('created_at', 'updated_at')),
        (ShippingBatch, ('recorded_at', 'updated_at')),
        (CustomsDocument, ('created_at', 'updated_at')),
        (Payment, ('created_at', 'deleted_at')),
        (Expense, ('created_at',)),
        (Procurement, ('created_at',)),
        (ProcurementAttachment, ('created_at', 'deleted_at')),
    ):
        for name in columns:
            timestamp_source(model, getattr(model, name))

    # Packing batches can be edited independently of the parent packing plan.
    sources.append(select(PackingList.pi_id, PackingBatch.updated_at)
                   .join(PackingBatch, PackingBatch.packing_list_id == PackingList.id))

    # Exporting a purchase contract and synchronizing archived copies are not
    # order edits.  Ordinary customer/customs/mobile uploads remain activity.
    manual_file = and_(CustomerFile.created_by != '系统自动归档',
                       CustomerFile.note != '采购合同')
    for column in (CustomerFile.created_at, CustomerFile.deleted_at):
        timestamp_source(CustomerFile, column, manual_file)

    write_audit = AuditLog.action.in_(_WRITE_ACTIONS)
    sources.append(select(AuditLog.entity_id, AuditLog.created_at).where(
        AuditLog.entity_type.in_(('pi', 'procurement')), write_audit))

    # Payment date/amount changes and deletions are retained in audit history,
    # even when the underlying record has no updated_at column.
    for model, kinds in (
        (Payment, ('payment', 'finance_payment_date', 'payment_performance_rate')),
        (Expense, ('expense',)),
        (PackingList, ('packing_list',)),
        (ShippingBatch, ('shipping_batch',)),
        (CustomsDocument, ('customs_document',)),
        (ProcurementAttachment, ('procurement_attachment',)),
    ):
        sources.append(select(model.pi_id, AuditLog.created_at)
                       .join(AuditLog, and_(AuditLog.entity_id == model.id,
                                          AuditLog.entity_type.in_(kinds)))
                       .where(write_audit))

    sources.append(select(CustomerFile.pi_id, AuditLog.created_at)
                   .join(AuditLog, and_(AuditLog.entity_id == CustomerFile.id,
                                      AuditLog.entity_type == 'customer_file'))
                   .where(write_audit, manual_file))

    # Finance review edits include actual receipt date, expense payment status,
    # and reconciliation metadata; they do not always update the PI itself.
    for model, kind in ((Payment, 'payment'), (Expense, 'expense')):
        sources.append(select(model.pi_id, AuditLog.created_at)
                       .join(FinanceReview, and_(FinanceReview.record_id == model.id,
                                                FinanceReview.kind == kind))
                       .join(AuditLog, and_(AuditLog.entity_id == FinanceReview.id,
                                          AuditLog.entity_type == 'finance_review'))
                       .where(write_audit))

    # Expense records are physically deleted.  Their original pi_id survives
    # in the audit snapshot.  Guard malformed/empty legacy JSON before using
    # SQLite JSON extraction (also used elsewhere in this application).
    deleted_pi_id = case(
        (func.json_valid(AuditLog.before_json),
         func.json_extract(AuditLog.before_json, '$.pi_id')),
        else_=None,
    )
    sources.append(select(deleted_pi_id, AuditLog.created_at).where(
        AuditLog.entity_type == 'expense', AuditLog.action == 'delete'))

    activity = union_all(*sources).subquery('order_business_activity')
    pi_ids = list(updates)
    # Calling this helper must not flush unrelated pending form changes.
    # Keep room for the audit-type/action parameters on SQLite installations
    # with the older 999-bind limit; one query still handles ordinary lists.
    with db.session.no_autoflush:
        for offset in range(0, len(pi_ids), 500):
            query = (select(activity.c.pi_id, func.max(activity.c.changed_at))
                     .where(activity.c.pi_id.in_(pi_ids[offset:offset + 500]))
                     .group_by(activity.c.pi_id))
            for pi_id, changed_at in db.session.execute(query):
                if changed_at and (updates[pi_id] is None or changed_at > updates[pi_id]):
                    updates[pi_id] = changed_at
    return updates
