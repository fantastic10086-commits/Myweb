"""Keep shipment batches and the legacy PI summary consistent."""
from datetime import datetime
from sqlalchemy import text
from models import db, ShippingBatch


def migrate_shipping_batches():
    # Idempotent: preserve dates, attribution, images and historical completeness.
    db.session.execute(text("""
        INSERT INTO shipping_batches
            (pi_id, batch_no, status, is_final, shipping_date, tracking_no,
             note, attachment, recorded_at, recorded_by, updated_at, updated_by)
        SELECT id, 1,
               CASE WHEN shipping_completed = 1 OR shipping_paused = 1 OR shipping_recorded_at IS NOT NULL
                    THEN 'shipped' ELSE 'draft' END,
               CASE WHEN shipping_completed = 1 OR shipping_paused = 1 THEN 1 ELSE 0 END,
               shipping_date, coalesce(shipping_tracking_no, ''),
               coalesce(shipping_record_note, ''), coalesce(shipping_attachment, ''),
               shipping_recorded_at, coalesce(shipping_recorded_by, ''),
               coalesce(updated_at, created_at, CURRENT_TIMESTAMP), coalesce(shipping_recorded_by, '')
          FROM pis
         WHERE (shipping_completed = 1 OR shipping_paused = 1 OR shipping_recorded_at IS NOT NULL
                OR shipping_date IS NOT NULL OR coalesce(shipping_tracking_no, '') != ''
                OR coalesce(shipping_record_note, '') != '' OR coalesce(shipping_attachment, '') != '')
           AND NOT EXISTS (SELECT 1 FROM shipping_batches sb WHERE sb.pi_id = pis.id)
    """))
    db.session.commit()


def legacy_batch(pi):
    if not (pi.shipping_completed or pi.shipping_paused or pi.shipping_recorded_at or
            pi.shipping_date or pi.shipping_tracking_no or pi.shipping_record_note or pi.shipping_attachment):
        return None
    return ShippingBatch(batch_no=1,
        status='shipped' if pi.shipping_completed or pi.shipping_paused or pi.shipping_recorded_at else 'draft',
        is_final=bool(pi.shipping_completed or pi.shipping_paused), shipping_date=pi.shipping_date,
        tracking_no=pi.shipping_tracking_no or '', note=pi.shipping_record_note or '',
        attachment=pi.shipping_attachment or '', recorded_at=pi.shipping_recorded_at,
        recorded_by=pi.shipping_recorded_by or '', updated_by=pi.shipping_recorded_by or '')


def ensure_batches(pi):
    if not pi.shipping_batches:
        batch = legacy_batch(pi)
        if batch:
            pi.shipping_batches.append(batch)
    return pi.shipping_batches


def sync_summary(pi):
    """Drafts never erase shipment facts; cancelled rows remain available for audit."""
    shipped = [b for b in pi.shipping_batches if b.status == 'shipped']
    pi.shipping_completed = bool(any(b.is_final for b in shipped) and not pi.shipping_paused)
    latest = max(shipped, key=lambda b: b.batch_no) if shipped else None
    pi.shipping_date = latest.shipping_date if latest else None
    pi.shipping_tracking_no = '；'.join(b.tracking_no for b in shipped if b.tracking_no)[:200]
    pi.shipping_record_note = latest.note if latest else ''
    pi.shipping_attachment = latest.attachment if latest else ''
    pi.shipping_recorded_at = latest.recorded_at if latest else None
    pi.shipping_recorded_by = latest.recorded_by if latest else ''
    pi.procurement_status = '发货完成' if pi.shipping_completed else ('采购完成' if pi.procurement_confirmed else '待采购')
    pi.updated_at = datetime.utcnow()  # Batch edits share the PI optimistic lock.


def batch_snapshot(batch):
    return dict(id=batch.id, batch_no=batch.batch_no, status=batch.status, is_final=bool(batch.is_final),
                shipping_date=batch.shipping_date.isoformat() if batch.shipping_date else '',
                tracking_no=batch.tracking_no or '', note=batch.note or '', attachment=batch.attachment or '',
                recorded_at=batch.recorded_at.isoformat() if batch.recorded_at else '',
                recorded_by=batch.recorded_by or '', updated_by=batch.updated_by or '')
