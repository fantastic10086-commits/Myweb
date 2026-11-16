"""Backfill existing persisted order files; run after a deployment backup."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app
from models import db, PI
from order_archive import sync_order_files

if __name__ == '__main__':
    with app.app_context():
        count = 0
        for pi in PI.query.filter(PI.deleted_at.is_(None)).order_by(PI.id).all():
            count += sync_order_files(db.session, pi)
            db.session.commit()
        print(f'Archived {count} files')
