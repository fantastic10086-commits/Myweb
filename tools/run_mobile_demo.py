"""Disposable localhost backend for iOS Simulator testing. Never reads live data."""
import os
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

with tempfile.TemporaryDirectory(prefix='pi-iphone-demo-') as folder:
    for name in ('instance','uploads','pdf','backups'):
        Path(folder,name).mkdir()
    os.environ.update(FLASK_ENV='production',SECRET_KEY='local-disposable-demo-only',
        INITIAL_ADMIN_PASSWORD='LocalPhotoTest123!',SESSION_COOKIE_SECURE='0',
        DATABASE_DIR=str(Path(folder,'instance')),UPLOAD_DIR=str(Path(folder,'uploads')),
        PDF_DIR=str(Path(folder,'pdf')),BACKUP_DIR=str(Path(folder,'backups')),
        SETTINGS_FILE=str(Path(folder,'settings.json')))
    # Do not inherit optional cloud database sync credentials into demo runs.
    for name in ('BLOB_READ_WRITE_TOKEN',): os.environ.pop(name,None)
    import app as application
    application.app.config['MOBILE_DEMO'] = True
    from models import db, User, Customer, PI
    from werkzeug.security import generate_password_hash
    with application.app.app_context():
        admin=User.query.filter_by(account='admin').one()
        admin.must_change_password=False
        db.session.add(User(account='demo-sales',username='测试业务员',role='salesperson',
            salesperson_name='Demo',password_hash=generate_password_hash('LocalPhotoTest123!'),must_change_password=False))
        customer=Customer(name='演示客户 · 非真实业务数据',salesperson='Demo')
        db.session.add(customer);db.session.flush()
        db.session.add_all([
            PI(pi_number='DEMO-PAID-001',customer_id=customer.id,salesperson='Demo',received_amount=100,currency='USD'),
            PI(pi_number='DEMO-UNPAID-002',customer_id=customer.id,salesperson='Demo',received_amount=0,currency='USD')])
        db.session.commit()
    print('Disposable simulator server: http://127.0.0.1:5099',flush=True)
    print('Demo accounts: admin / demo-sales; demo-only password: LocalPhotoTest123!',flush=True)
    application.app.run(host='127.0.0.1',port=5099,debug=False,use_reloader=False)
