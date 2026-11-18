"""Archive persisted order files independently of mutable business attachments."""
import hashlib
import mimetypes
import os
import shutil
import tempfile
from flask import current_app, has_app_context
from sqlalchemy import event
from sqlalchemy.orm import Session
from werkzeug.utils import secure_filename
from export_filenames import stored_pi_filename
from models import db, PI, PIItem, Payment, Expense, Procurement, CustomerFile, ShippingBatch


def sync_order_files(session, pi):
    if not pi or pi.deleted_at:
        return 0
    sources = [('UPLOAD_DIR', pi.shipping_attachment, '发货图片'),
               ('UPLOAD_DIR', (pi.advance_slip or {}).get('attachment'), '提前发货水单'),
               ('PDF_DIR', pi.pdf_path, 'PI PDF'), ('PDF_DIR', pi.excel_path, 'PI Excel')]
    sources += [('UPLOAD_DIR', p.attachment, '回款凭证') for p in pi.payments if not p.deleted_at]
    sources += [('UPLOAD_DIR', e.attachment, '费用附件') for e in pi.expenses]
    sources += [('UPLOAD_DIR', i.display_image, '订单产品图片') for i in pi.items]
    sources += [('UPLOAD_DIR', p.image_snapshot, '采购产品图片') for p in pi.procurements]
    sources += [('UPLOAD_DIR', b.attachment, '第 {} 批发货图片'.format(b.batch_no)) for b in pi.shipping_batches]
    existing = {f.stored_name for f in session.query(CustomerFile).filter_by(pi_id=pi.id)}
    count = 0
    for directory, name, label in sources:
        if not name or secure_filename(name) != name:
            continue
        path = os.path.join(current_app.config[directory], name)
        if not os.path.isfile(path):
            continue
        # Existing mobile/manual uploads already belong to this PI.
        if name in existing:
            continue
        digest = hashlib.sha256()
        with open(path, 'rb') as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b''):
                digest.update(chunk)
        stored = f'order_{pi.id}_{digest.hexdigest()}{os.path.splitext(name)[1].lower()}'
        if stored in existing:
            continue
        target = os.path.join(current_app.config['UPLOAD_DIR'], stored)
        # Atomic replacement also makes retry after a rolled-back transaction safe.
        fd, temporary = tempfile.mkstemp(dir=current_app.config['UPLOAD_DIR'], prefix='.archive-')
        os.close(fd)
        try:
            shutil.copyfile(path, temporary)
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)
        display_name = name
        if directory == 'PDF_DIR':
            extension = os.path.splitext(name)[1][1:].lower()
            display_name = stored_pi_filename(pi, extension)
        session.add(CustomerFile(customer_id=pi.customer_id, pi_id=pi.id,
            stored_name=stored, original_name=display_name[:255],
            mime_type=mimetypes.guess_type(name)[0] or 'application/octet-stream',
            size_bytes=os.path.getsize(target), note=label, created_by='系统自动归档'))
        existing.add(stored)
        count += 1
    return count


@event.listens_for(Session, 'before_flush')
def collect_order_changes(session, flush_context, instances):
    if not has_app_context():
        return
    changed = [obj for obj in session.new.union(session.dirty)
               if isinstance(obj, (PI, PIItem, Payment, Expense, Procurement, ShippingBatch))]
    if changed:
        session.info.setdefault('archive_order_changes', []).extend(changed)


@event.listens_for(Session, 'after_flush_postexec')
def archive_order_changes(session, flush_context):
    changed = session.info.pop('archive_order_changes', [])
    ids = {obj.id if isinstance(obj, PI) else obj.pi_id for obj in changed}
    for pi_id in ids - {None}:
        sync_order_files(session, session.get(PI, pi_id))


@event.listens_for(Session, 'after_rollback')
def clear_order_changes(session):
    session.info.pop('archive_order_changes', None)
