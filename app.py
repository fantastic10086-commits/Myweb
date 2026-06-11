"""
Flask PI Management System
Foreign Trade Proforma Invoice Generator
Run with: python app.py
"""

import os
import sys
import uuid
from datetime import datetime, date, timedelta
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, send_file, jsonify, current_app, session
)
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from models import db, Customer, Product, PI, PIItem, Salesperson, User, Account, Payment
from pdf_generator import generate_pi_pdf
from excel_generator import generate_pi_excel

# ── Configuration ────────────────────────────────────────────────────
# Detect the app root directory (where this file lives)
APP_ROOT = os.path.dirname(os.path.abspath(__file__))

def _migrate_db():
    """Auto-add missing columns to existing tables without data loss."""
    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)
    expected = {
        'customers': {'salesperson': 'VARCHAR(100)', 'created_at': 'DATETIME', 'total_deal_usd': 'FLOAT'},
        'products': {'image': 'VARCHAR(500)'},
        'pis': {'salesperson': 'VARCHAR(100)', 'currency': 'VARCHAR(3)', 'company': 'VARCHAR(50)', 'excel_path': 'VARCHAR(500)', 'paid': 'BOOLEAN', 'received_amount': 'FLOAT'},
        'salespersons': {'phone': 'VARCHAR(50)', 'email': 'VARCHAR(200)'},
        'accounts': {},  # table auto-created by create_all
    }
    for table, columns in expected.items():
        if not inspector.has_table(table): continue
        existing = {c['name'] for c in inspector.get_columns(table)}
        for col_name, col_type in columns.items():
            if col_name not in existing:
                try:
                    db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type} DEFAULT ''"))
                    db.session.commit()
                except Exception:
                    db.session.rollback()


# Company info — edit these to match your business
COMPANY_CONFIG = {
    'name': 'CHANGZHOU KLISTA INTERNATIONAL TRADE CO., LTD.',
    'address': 'No. 158 Jinchuang Road, Yaoguan Town, Changzhou City, China',
    'phone': '+86 17712333882',
    'email': 'fantastic10086@gmail.com',
}


def _seed_products_from_csv():
    """Seed products from bundled CSV files on first startup."""
    import csv, re
    for fname in ['产品信息202606111_1.csv', '产品信息202606111_2.csv', '产品信息202606111_3.csv']:
        csv_path = os.path.join(APP_ROOT, fname)
        if not os.path.exists(csv_path):
            continue
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)
            for row in reader:
                try:
                    name = (row[0] or '').strip().replace('\n', ' ').replace('\r', '')[:200]
                    if not name: continue
                    code = (row[1] or '').strip()[:100]
                    spec = (row[2] or '').strip()[:200]
                    price_str = (row[5] or '').strip()
                    price = 0.0
                    if price_str:
                        nums = re.findall(r'[\d.]+', price_str.replace(',', ''))
                        if nums:
                            try: price = float(nums[0])
                            except: pass
                    db.session.add(Product(name=name, product_code=code, specification=spec, unit_price=price))
                except Exception:
                    pass
    db.session.commit()


def _seed_customers_from_csv():
    """Seed customers from bundled CSV file on first startup."""
    import csv
    csv_path = os.path.join(APP_ROOT, 'CUSTOMER_EXPORT_56677547_1_1781157273.csv')
    if not os.path.exists(csv_path):
        return
    count = 0
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader)
        for row in reader:
            try:
                name = (row[0] or '').strip()
                if not name or name.startswith('NA_') or name.startswith('nocompany_'):
                    contact = (row[3] or '').strip()
                    name = contact if (contact and not contact.startswith('NA_')) else f'Customer_{row[2]}'
                contact_person = (row[3] or '').strip()[:100]
                email = (row[4] or '').strip() if len(row) > 4 else ''
                salesperson = (row[5] or '').strip() if len(row) > 5 else ''
                country = (row[6] or '').strip() if len(row) > 6 else ''
                address = (row[7] or '').strip() if len(row) > 7 else ''
                phone_raw = (row[9] or '').strip() if len(row) > 9 else ''
                phone = ''
                if phone_raw:
                    for p in phone_raw.replace("'", '').split(';'):
                        p = p.strip().strip('"+').strip()
                        if p and any(c.isdigit() for c in p):
                            phone = p[:50]; break
                deal_str = row[-1].strip() if row[-1] else '0'
                try:
                    total_deal = float(deal_str) if deal_str else 0.0
                except ValueError:
                    total_deal = 0.0
                name = name.replace('&amp;', '&')[:200]
                db.session.add(Customer(
                    name=name, country=country, contact_person=contact_person,
                    email=email, phone=phone, address=address,
                    salesperson=salesperson, total_deal_usd=total_deal,
                ))
                count += 1
                if count % 500 == 0: db.session.commit()
            except Exception:
                pass
    db.session.commit()


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'pi-manager-secret-key-change-in-production'

    # Database — stored in instance/ folder under project root
    db_path = os.path.join(APP_ROOT, 'instance', 'pi_manager.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # PDF output directory
    app.config['PDF_DIR'] = os.path.join(APP_ROOT, 'pdf')
    app.config['UPLOAD_DIR'] = os.path.join(APP_ROOT, 'static', 'uploads')
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max upload
    os.makedirs(app.config['PDF_DIR'], exist_ok=True)
    os.makedirs(app.config['UPLOAD_DIR'], exist_ok=True)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    db.init_app(app)

    with app.app_context():
        db.create_all()
        _migrate_db()

        # Seed default salespersons
        default_sp = [
            ('Shu Kei', '+86 17712333882', 'fantastic10086@gmail.com'),
            ('Limon', '+86 15301506008', 'limon@qisuowelding.com'),
            ('Kristi', '+86 18112500618', 'kristi@qisuowelding.com'),
            ('Lu Yan', '+86 18019696608', 'luyan@qisuowelding.com'),
        ]
        for name, phone, email in default_sp:
            if not Salesperson.query.filter_by(name=name).first():
                db.session.add(Salesperson(name=name, phone=phone, email=email))
        db.session.commit()

        # Seed default accounts (by name, won't overwrite existing)
        default_accounts = [
            ('克利斯达-农行', 'CHANGZHOU KLISTA INTERNATIONAL TRADE CO.LTD', 'AGRICULTURAL BANK OF CHINA H.O.BEIJING', '10618114040004700', 'ABOCCNBJ', 'klista'),
            ('QISUO-花旗', 'Changzhou Q1 Suo Welding And Cutting Equipment Co., Ltd.', 'CITIBANK N. A. HONG KONG BRANCH', '39740000004173', 'CITIHKHXXXX', 'qisuo'),
            ('姜舒棋的支付宝', 'CHANGZHOU KLISTA INTERNATIONAL TRADE CO.LTD', 'Alipay', '17712333882', '', 'klista'),
            ('姜舒棋的微信', 'CHANGZHOU KLISTA INTERNATIONAL TRADE CO.LTD', 'Wechat', '17712333882', '', 'klista'),
        ]
        for name, co_name, bank_name, acct_no, swift, brand in default_accounts:
            if not Account.query.filter_by(name=name).first():
                db.session.add(Account(name=name, company_name=co_name, bank_name=bank_name, account_no=acct_no, swift_code=swift, brand=brand))
        db.session.commit()

        # Seed default customers from CSV (only if empty)
        if Customer.query.count() == 0:
            _seed_customers_from_csv()

        # Seed default products from CSV (only if empty)
        if Product.query.count() == 0:
            _seed_products_from_csv()

        # Seed admin account if not exists
        if not User.query.filter_by(username='admin').first():
            db.session.add(User(
                username='admin',
                password_hash=generate_password_hash('admin123'),
                role='admin',
                salesperson_name='',
            ))
            db.session.commit()

    return app


app = create_app()


# ── Helper ─────────────────────────────────────────────────────────────
def _generate_pi_number():
    """Generate sequential PI number: PI-YYYYMMDD-NNN"""
    today = date.today()
    prefix = f"PI-{today.strftime('%Y%m%d')}-"
    count = PI.query.filter(PI.pi_number.like(f'{prefix}%')).count()
    return f"{prefix}{count + 1:03d}"

def _save_upload(file):
    """Save an uploaded file and return the filename."""
    if not file or file.filename == '':
        return ''
    filename = secure_filename(file.filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ('.jpg', '.jpeg', '.png', '.gif', '.webp'):
        return ''
    unique_name = f"{uuid.uuid4().hex}{ext}"
    file.save(os.path.join(current_app.config['UPLOAD_DIR'], unique_name))
    return unique_name

ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp'}


# ── Auth helpers ─────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def get_current_user():
    if 'user_id' in session:
        return User.query.get(session['user_id'])
    return None

def is_admin():
    return session.get('role') == 'admin'

def filter_by_user(query, model, salesperson_field='salesperson'):
    """Filter query by current user's salesperson if not admin."""
    if is_admin():
        return query
    sp = session.get('salesperson_name', '')
    if sp and hasattr(model, salesperson_field):
        return query.filter(getattr(model, salesperson_field) == sp)
    return query


# ═══════════════════════════════════════════════════════════════════════
#  ROUTES — Auth
# ═══════════════════════════════════════════════════════════════════════

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            session['salesperson_name'] = user.salesperson_name
            flash(f'Welcome, {user.username}!', 'success')
            return redirect(url_for('index'))
        flash('Invalid username or password.', 'danger')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out.', 'info')
    return redirect(url_for('login'))


@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user = get_current_user()
    sp = None
    if not is_admin() and user.salesperson_name:
        sp = Salesperson.query.filter_by(name=user.salesperson_name).first()
        # Auto-create salesperson record if missing
        if not sp:
            sp = Salesperson(name=user.salesperson_name)
            db.session.add(sp)
            db.session.commit()

    if request.method == 'POST' and sp:
        sp.phone = request.form.get('phone', '').strip()
        sp.email = request.form.get('email', '').strip()
        sp.notes = request.form.get('notes', '').strip()
        db.session.commit()
        flash('Profile updated.', 'success')
        return redirect(url_for('profile'))

    # Stats for salesperson
    stats = None
    pi_list = []
    if sp:
        stats = db.session.query(
            func.count(PI.id).label('pi_count'),
            func.coalesce(func.sum(PI.total_amount), 0).label('total_amount'),
        ).filter(PI.salesperson == sp.name).first()
        pi_list = PI.query.options(joinedload(PI.customer)).filter_by(salesperson=sp.name).order_by(PI.created_at.desc()).limit(10).all()

    return render_template('profile.html', sp=sp, stats=stats, pi_list=pi_list)


# ═══════════════════════════════════════════════════════════════════════
#  ROUTES — Dashboard
# ═══════════════════════════════════════════════════════════════════════

@app.route('/')
@login_required
def index():
    cust_q = filter_by_user(Customer.query, Customer, 'salesperson')
    customer_count = cust_q.count()
    product_count = Product.query.count()
    pi_q = filter_by_user(PI.query, PI, 'salesperson')
    pi_count = pi_q.count()
    recent_pis = pi_q.order_by(PI.created_at.desc()).limit(5).all()
    return render_template('index.html',
                           customer_count=customer_count,
                           product_count=product_count,
                           pi_count=pi_count,
                           recent_pis=recent_pis)


# ═══════════════════════════════════════════════════════════════════════
#  ROUTES — Customers
# ═══════════════════════════════════════════════════════════════════════

@app.route('/customers')
@login_required
def customer_list():
    search = request.args.get('search', '').strip()
    query = filter_by_user(Customer.query, Customer, 'salesperson')
    if search:
        query = query.filter(
            db.or_(
                Customer.name.ilike(f'%{search}%'),
                Customer.country.ilike(f'%{search}%'),
                Customer.contact_person.ilike(f'%{search}%'),
                Customer.email.ilike(f'%{search}%'),
            )
        )
    customers = query.order_by(Customer.created_at.desc()).all()
    return render_template('customers.html', customers=customers, search=search)


@app.route('/customers/add', methods=['GET', 'POST'])
@login_required
def customer_add():
    if request.method == 'POST':
        customer = Customer(
            name=request.form.get('name', '').strip(),
            country=request.form.get('country', '').strip(),
            contact_person=request.form.get('contact_person', '').strip(),
            email=request.form.get('email', '').strip(),
            phone=request.form.get('phone', '').strip(),
            address=request.form.get('address', '').strip(),
            salesperson=request.form.get('salesperson', '').strip(),
            notes=request.form.get('notes', '').strip(),
        )
        if not customer.name:
            flash('Customer name is required.', 'danger')
            return render_template('customer_form.html', customer=customer, editing=False)
        db.session.add(customer)
        db.session.commit()
        flash('Customer added successfully.', 'success')
        return redirect(url_for('customer_list'))
    return render_template('customer_form.html', customer=None, editing=False)


@app.route('/customers/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def customer_edit(id):
    customer = Customer.query.get_or_404(id)
    if request.method == 'POST':
        customer.name = request.form.get('name', '').strip()
        customer.country = request.form.get('country', '').strip()
        customer.contact_person = request.form.get('contact_person', '').strip()
        customer.email = request.form.get('email', '').strip()
        customer.phone = request.form.get('phone', '').strip()
        customer.address = request.form.get('address', '').strip()
        customer.salesperson = request.form.get('salesperson', '').strip()
        customer.notes = request.form.get('notes', '').strip()
        if not customer.name:
            flash('Customer name is required.', 'danger')
            return render_template('customer_form.html', customer=customer, editing=True)
        db.session.commit()
        flash('Customer updated successfully.', 'success')
        return redirect(url_for('customer_list'))
    return render_template('customer_form.html', customer=customer, editing=True)


@app.route('/api/customers/add', methods=['POST'])
def api_customer_add():
    """AJAX endpoint — add a customer and return JSON."""
    name = request.form.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'Customer name is required.'}), 400

    customer = Customer(
        name=name,
        country=request.form.get('country', '').strip(),
        contact_person=request.form.get('contact_person', '').strip(),
        email=request.form.get('email', '').strip(),
        phone=request.form.get('phone', '').strip(),
        address=request.form.get('address', '').strip(),
        salesperson=request.form.get('salesperson', '').strip(),
        notes=request.form.get('notes', '').strip(),
    )
    db.session.add(customer)
    db.session.commit()

    return jsonify({
        'success': True,
        'customer': customer.to_dict(),
    })


@app.route('/customers/<int:id>')
@login_required
def customer_detail(id):
    customer = Customer.query.get_or_404(id)
    pis = PI.query.options(
        joinedload(PI.items).joinedload(PIItem.product)
    ).filter_by(customer_id=id).order_by(PI.created_at.desc()).all()
    return render_template('customer_detail.html', customer=customer, pis=pis)


@app.route('/sales-stats')
@login_required
def sales_stats():
    """Salesperson statistics: PI count and total amount per salesperson."""
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    preset = request.args.get('preset', '').strip()

    # Apply preset date ranges
    today = date.today()
    if preset == 'this_month':
        date_from = today.replace(day=1).strftime('%Y-%m-%d')
        date_to = today.strftime('%Y-%m-%d')
    elif preset == 'last_month':
        first_of_this_month = today.replace(day=1)
        last_of_last_month = first_of_this_month - timedelta(days=1)
        date_from = last_of_last_month.replace(day=1).strftime('%Y-%m-%d')
        date_to = last_of_last_month.strftime('%Y-%m-%d')
    elif preset == 'this_year':
        date_from = today.replace(month=1, day=1).strftime('%Y-%m-%d')
        date_to = today.strftime('%Y-%m-%d')


    # Apply preset date ranges
    today = date.today()
    if preset == 'this_month':
        date_from = today.replace(day=1).strftime('%Y-%m-%d')
        date_to = today.strftime('%Y-%m-%d')
    elif preset == 'last_month':
        first_of_this_month = today.replace(day=1)
        last_of_last_month = first_of_this_month - timedelta(days=1)
        date_from = last_of_last_month.replace(day=1).strftime('%Y-%m-%d')
        date_to = last_of_last_month.strftime('%Y-%m-%d')
    elif preset == 'this_year':
        date_from = today.replace(month=1, day=1).strftime('%Y-%m-%d')
        date_to = today.strftime('%Y-%m-%d')

    base_q = db.session.query(
        func.coalesce(db.func.nullif(PI.salesperson, ''), '(Unassigned)').label('salesperson'),
        func.count(PI.id).label('pi_count'),
        func.coalesce(func.sum(PI.total_amount), 0).label('total_amount'),
        func.count(db.distinct(PI.customer_id)).label('customer_count'),
    )
    if date_from:
        try:
            base_q = base_q.filter(PI.issue_date >= datetime.strptime(date_from, '%Y-%m-%d').date())
        except ValueError:
            pass
    if date_to:
        try:
            base_q = base_q.filter(PI.issue_date <= datetime.strptime(date_to, '%Y-%m-%d').date())
        except ValueError:
            pass
    results = base_q.group_by(PI.salesperson).order_by(func.sum(PI.total_amount).desc()).all()

    grand_total = sum(r.total_amount for r in results)
    grand_pi_count = sum(r.pi_count for r in results)

    # Detailed PI list for the same filter
    pi_detail_q = PI.query.options(joinedload(PI.customer)).order_by(PI.created_at.desc())
    if date_from:
        try: pi_detail_q = pi_detail_q.filter(PI.issue_date >= datetime.strptime(date_from, '%Y-%m-%d').date())
        except: pass
    if date_to:
        try: pi_detail_q = pi_detail_q.filter(PI.issue_date <= datetime.strptime(date_to, '%Y-%m-%d').date())
        except: pass
    all_filtered_pis = pi_detail_q.all()

    return render_template('sales_stats.html',
                           stats=results,
                           grand_total=grand_total,
                           grand_pi_count=grand_pi_count,
                           date_from=date_from,
                           date_to=date_to,
                           preset=preset,
                           all_pis=all_filtered_pis)


@app.route('/customers/<int:id>/delete', methods=['POST'])
@login_required
def customer_delete(id):
    customer = Customer.query.get_or_404(id)
    db.session.delete(customer)
    db.session.commit()
    flash('Customer deleted successfully.', 'success')
    return redirect(url_for('customer_list'))


@app.route('/customers/<int:id>/reassign', methods=['POST'])
@login_required
def customer_reassign(id):
    if not is_admin():
        flash('Access denied.', 'danger')
        return redirect(url_for('customer_list'))
    customer = Customer.query.get_or_404(id)
    new_sp = request.form.get('salesperson', '').strip()
    old_sp = customer.salesperson
    if not new_sp:
        flash('Please select a salesperson.', 'danger')
        return redirect(url_for('customer_edit', id=id))
    # Update customer
    customer.salesperson = new_sp
    # Update all PIs under this customer
    count = PI.query.filter_by(customer_id=id).update({'salesperson': new_sp})
    db.session.commit()
    old_label = old_sp or 'unassigned'
    flash(f'Customer and {count} PI(s) reassigned from "{old_label}" to "{new_sp}".', 'success')
    return redirect(url_for('customer_list'))


# ═══════════════════════════════════════════════════════════════════════
#  ROUTES — Products
# ═══════════════════════════════════════════════════════════════════════

@app.route('/products')
@login_required
def product_list():
    search = request.args.get('search', '').strip()
    if search:
        query = Product.query.filter(
            db.or_(
                Product.name.ilike(f'%{search}%'),
                Product.product_code.ilike(f'%{search}%'),
                Product.specification.ilike(f'%{search}%'),
            )
        )
    else:
        query = Product.query
    products = query.order_by(Product.created_at.desc()).all()
    return render_template('products.html', products=products, search=search)


@app.route('/products/add', methods=['GET', 'POST'])
@login_required
def product_add():
    if request.method == 'POST':
        try:
            unit_price = float(request.form.get('unit_price', '0').strip() or '0')
        except ValueError:
            unit_price = 0.0
        image_file = request.files.get('image')
        image_filename = _save_upload(image_file) if image_file else ''
        product = Product(
            name=request.form.get('name', '').strip(),
            product_code=request.form.get('product_code', '').strip(),
            specification=request.form.get('specification', '').strip(),
            unit_price=unit_price,
            notes=request.form.get('notes', '').strip(),
            image=image_filename,
        )
        if not product.name:
            flash('Product name is required.', 'danger')
            return render_template('product_form.html', product=product, editing=False)
        db.session.add(product)
        db.session.commit()
        flash('Product added successfully.', 'success')
        return redirect(url_for('product_list'))
    return render_template('product_form.html', product=None, editing=False)


@app.route('/products/<int:id>/edit', methods=['GET', 'POST'])
def product_edit(id):
    product = Product.query.get_or_404(id)
    if request.method == 'POST':
        product.name = request.form.get('name', '').strip()
        product.product_code = request.form.get('product_code', '').strip()
        product.specification = request.form.get('specification', '').strip()
        try:
            product.unit_price = float(request.form.get('unit_price', '0').strip() or '0')
        except ValueError:
            product.unit_price = 0.0
        product.notes = request.form.get('notes', '').strip()
        image_file = request.files.get('image')
        if image_file and image_file.filename:
            new_img = _save_upload(image_file)
            if new_img:
                # Delete old image
                if product.image:
                    old_path = os.path.join(current_app.config['UPLOAD_DIR'], product.image)
                    if os.path.exists(old_path): os.remove(old_path)
                product.image = new_img
        if not product.name:
            flash('Product name is required.', 'danger')
            return render_template('product_form.html', product=product, editing=True)
        db.session.commit()
        flash('Product updated successfully.', 'success')
        return redirect(url_for('product_list'))
    return render_template('product_form.html', product=product, editing=True)


@app.route('/products/<int:id>/delete', methods=['POST'])
def product_delete(id):
    product = Product.query.get_or_404(id)
    db.session.delete(product)
    db.session.commit()
    flash('Product deleted successfully.', 'success')
    return redirect(url_for('product_list'))


@app.route('/api/products/add', methods=['POST'])
def api_product_add():
    """AJAX endpoint — add a product and return JSON."""
    try:
        unit_price = float(request.form.get('unit_price', '0').strip() or '0')
    except ValueError:
        unit_price = 0.0

    image_file = request.files.get('image')
    product = Product(
        name=request.form.get('name', '').strip(),
        product_code=request.form.get('product_code', '').strip(),
        specification=request.form.get('specification', '').strip(),
        unit_price=unit_price,
        notes=request.form.get('notes', '').strip(),
        image=_save_upload(image_file) if image_file else '',
    )
    if not product.name:
        return jsonify({'success': False, 'error': 'Product name is required.'}), 400

    db.session.add(product)
    db.session.commit()

    return jsonify({
        'success': True,
        'product': product.to_dict(),
    })


@app.route('/api/products/search')
@login_required
def api_product_search():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([])
    pattern = f'%{q}%'
    products = Product.query.filter(
        db.or_(Product.name.ilike(pattern), Product.product_code.ilike(pattern))
    ).limit(50).all()
    return jsonify([{
        'id': p.id, 'name': p.name, 'code': p.product_code,
        'spec': p.specification or '', 'price': p.unit_price, 'img': p.image or '',
    } for p in products])


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_file(os.path.join(current_app.config['UPLOAD_DIR'], secure_filename(filename)))


# ═══════════════════════════════════════════════════════════════════════
#  ROUTES — Salespersons
# ═══════════════════════════════════════════════════════════════════════

@app.route('/salespersons')
@login_required
def salesperson_list():
    salespersons = Salesperson.query.order_by(Salesperson.name).all()
    return render_template('salesperson_list.html', salespersons=salespersons)


@app.route('/salespersons/add', methods=['GET', 'POST'])
def salesperson_add():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('Salesperson name is required.', 'danger')
            return render_template('salesperson_form.html', sp=None, editing=False)
        if Salesperson.query.filter_by(name=name).first():
            flash('Salesperson name already exists.', 'danger')
            return render_template('salesperson_form.html', sp=None, editing=False)
        sp = Salesperson(
            name=name,
            phone=request.form.get('phone', '').strip(),
            email=request.form.get('email', '').strip(),
            notes=request.form.get('notes', '').strip(),
        )
        db.session.add(sp)
        db.session.commit()
        flash('Salesperson added successfully.', 'success')
        return redirect(url_for('salesperson_list'))
    return render_template('salesperson_form.html', sp=None, editing=False)


@app.route('/salespersons/<int:id>/edit', methods=['GET', 'POST'])
def salesperson_edit(id):
    sp = Salesperson.query.get_or_404(id)
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('Salesperson name is required.', 'danger')
            return render_template('salesperson_form.html', sp=sp, editing=True)
        existing = Salesperson.query.filter_by(name=name).first()
        if existing and existing.id != sp.id:
            flash('Salesperson name already exists.', 'danger')
            return render_template('salesperson_form.html', sp=sp, editing=True)
        sp.name = name
        sp.phone = request.form.get('phone', '').strip()
        sp.email = request.form.get('email', '').strip()
        sp.notes = request.form.get('notes', '').strip()
        db.session.commit()
        flash('Salesperson updated successfully.', 'success')
        return redirect(url_for('salesperson_list'))
    return render_template('salesperson_form.html', sp=sp, editing=True)


@app.route('/salespersons/<int:id>/delete', methods=['POST'])
def salesperson_delete(id):
    sp = Salesperson.query.get_or_404(id)
    db.session.delete(sp)
    db.session.commit()
    flash('Salesperson deleted successfully.', 'success')
    return redirect(url_for('salesperson_list'))


# ═══════════════════════════════════════════════════════════════════════
#  ROUTES — Users (Admin only)
# ═══════════════════════════════════════════════════════════════════════

@app.route('/users')
@login_required
def user_list():
    if not is_admin():
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('user_list.html', users=users)


@app.route('/users/add', methods=['GET', 'POST'])
@login_required
def user_add():
    if not is_admin():
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        role = request.form.get('role', 'salesperson').strip()
        salesperson_name = request.form.get('salesperson_name', '').strip()
        if not username or not password:
            flash('Username and password are required.', 'danger')
            return render_template('user_form.html', u=None, editing=False)
        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'danger')
            return render_template('user_form.html', u=None, editing=False)
        db.session.add(User(
            username=username,
            password_hash=generate_password_hash(password),
            role=role,
            salesperson_name=salesperson_name if role == 'salesperson' else '',
        ))
        db.session.commit()
        flash('User created.', 'success')
        return redirect(url_for('user_list'))
    return render_template('user_form.html', u=None, editing=False)


@app.route('/users/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def user_edit(id):
    if not is_admin():
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))
    user = User.query.get_or_404(id)
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        role = request.form.get('role', 'salesperson').strip()
        salesperson_name = request.form.get('salesperson_name', '').strip()
        if not username:
            flash('Username is required.', 'danger')
            return render_template('user_form.html', u=user, editing=True)
        existing = User.query.filter_by(username=username).first()
        if existing and existing.id != user.id:
            flash('Username already exists.', 'danger')
            return render_template('user_form.html', u=user, editing=True)
        user.username = username
        if password:
            user.password_hash = generate_password_hash(password)
        user.role = role
        user.salesperson_name = salesperson_name if role == 'salesperson' else ''
        db.session.commit()
        flash('User updated.', 'success')
        return redirect(url_for('user_list'))
    return render_template('user_form.html', u=user, editing=True)


@app.route('/users/<int:id>/delete', methods=['POST'])
@login_required
def user_delete(id):
    if not is_admin():
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))
    user = User.query.get_or_404(id)
    if user.username == 'admin':
        flash('Cannot delete the admin account.', 'danger')
        return redirect(url_for('user_list'))
    db.session.delete(user)
    db.session.commit()
    flash('User deleted.', 'success')
    return redirect(url_for('user_list'))


# ═══════════════════════════════════════════════════════════════════════
#  ROUTES — Accounts (Admin only)
# ═══════════════════════════════════════════════════════════════════════

@app.route('/accounts')
@login_required
def account_list():
    if not is_admin(): return redirect(url_for('index'))
    accounts = Account.query.order_by(Account.name).all()
    return render_template('account_list.html', accounts=accounts)

@app.route('/accounts/add', methods=['GET', 'POST'])
@login_required
def account_add():
    if not is_admin(): return redirect(url_for('index'))
    if request.method == 'POST':
        db.session.add(Account(
            name=request.form.get('name','').strip(),
            company_name=request.form.get('company_name','').strip(),
            bank_name=request.form.get('bank_name','').strip(),
            account_no=request.form.get('account_no','').strip(),
            swift_code=request.form.get('swift_code','').strip(),
            brand=request.form.get('brand','klista').strip(),
            notes=request.form.get('notes','').strip(),
        ))
        db.session.commit()
        flash('Account added.', 'success')
        return redirect(url_for('account_list'))
    return render_template('account_form.html', a=None, editing=False)

@app.route('/accounts/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def account_edit(id):
    if not is_admin(): return redirect(url_for('index'))
    a = Account.query.get_or_404(id)
    if request.method == 'POST':
        a.name = request.form.get('name','').strip()
        a.company_name = request.form.get('company_name','').strip()
        a.bank_name = request.form.get('bank_name','').strip()
        a.account_no = request.form.get('account_no','').strip()
        a.swift_code = request.form.get('swift_code','').strip()
        a.brand = request.form.get('brand','klista').strip()
        a.notes = request.form.get('notes','').strip()
        db.session.commit()
        flash('Account updated.', 'success')
        return redirect(url_for('account_list'))
    return render_template('account_form.html', a=a, editing=True)

@app.route('/accounts/<int:id>/delete', methods=['POST'])
@login_required
def account_delete(id):
    if not is_admin(): return redirect(url_for('index'))
    db.session.delete(Account.query.get_or_404(id))
    db.session.commit()
    flash('Account deleted.', 'success')
    return redirect(url_for('account_list'))


# ═══════════════════════════════════════════════════════════════════════
#  ROUTES — PI (Proforma Invoice)
# ═══════════════════════════════════════════════════════════════════════

@app.route('/pi/create', methods=['GET', 'POST'])
@login_required
def pi_create():
    customers = filter_by_user(Customer.query, Customer, 'salesperson').order_by(Customer.name).all()
    products = Product.query.order_by(Product.name).all()

    if request.method == 'POST':
        customer_id = request.form.get('customer_id', type=int)
        salesperson = request.form.get('salesperson', '').strip()
        payment_terms = request.form.get('payment_terms', '').strip()
        bank_info = request.form.get('bank_info', '').strip()
        notes = request.form.get('notes', '').strip()
        issue_date_str = request.form.get('issue_date', '').strip()
        currency = request.form.get('currency', 'USD').strip()
        company = request.form.get('company', 'klista').strip()
        account_id = request.form.get('account_id', type=int)

        if not customer_id:
            flash('Please select a customer.', 'danger')
            return render_template('create_pi.html', customers=customers,
                                   products=products, pi=None,
                                   today=date.today().strftime('%Y-%m-%d'),
                                   selected_customer_id=None)

        if not salesperson:
            flash('Please select a salesperson.', 'danger')
            return render_template('create_pi.html', customers=customers,
                                   products=products, pi=None,
                                   today=date.today().strftime('%Y-%m-%d'),
                                   selected_customer_id=customer_id)

        # Parse issue date
        try:
            issue_date = datetime.strptime(issue_date_str, '%Y-%m-%d').date() if issue_date_str else date.today()
        except ValueError:
            issue_date = date.today()

        # Collect selected products with quantities
        selected_items = []
        total_amount = 0.0
        for product in products:
            qty_key = f'qty_{product.id}'
            selected_key = f'selected_{product.id}'
            if request.form.get(selected_key) == 'on':
                try:
                    qty = int(request.form.get(qty_key, '1').strip() or '1')
                except ValueError:
                    qty = 1
                unit_price_str = request.form.get(f'unit_price_{product.id}', '').strip()
                try:
                    unit_price = float(unit_price_str) if unit_price_str else product.unit_price
                except ValueError:
                    unit_price = product.unit_price
                if qty > 0:
                    amount = round(unit_price * qty, 2)
                    selected_items.append({
                        'product': product,
                        'quantity': qty,
                        'unit_price': unit_price,
                        'amount': amount,
                    })
                    total_amount += amount

        if not selected_items:
            flash('Please select at least one product.', 'danger')
            return render_template('create_pi.html', customers=customers,
                                   products=products, pi=None,
                                   today=issue_date.strftime('%Y-%m-%d'),
                                   selected_customer_id=customer_id)

        total_amount = round(total_amount, 2)

        # Create PI record
        pi_number = _generate_pi_number()
        bank_info_from_account = ''
        if account_id:
            acct = Account.query.get(account_id)
            if acct: bank_info_from_account = acct.bank_info()
        pi = PI(
            pi_number=pi_number,
            customer_id=customer_id,
            issue_date=issue_date,
            payment_terms=payment_terms or '100% TT before shipment',
            bank_info=bank_info or bank_info_from_account,
            salesperson=salesperson,
            currency=currency,
            company=company,
            total_amount=total_amount,
            notes=notes,
        )
        db.session.add(pi)
        db.session.flush()  # Get pi.id

        # Create PI items
        for item in selected_items:
            pi_item = PIItem(
                pi_id=pi.id,
                product_id=item['product'].id,
                quantity=item['quantity'],
                unit_price=item['unit_price'],
                amount=item['amount'],
            )
            db.session.add(pi_item)

        db.session.flush()

        # Generate PDF
        try:
            # Reload PI with relationships for PDF generation
            pi_full = PI.query.options(
                joinedload(PI.items).joinedload(PIItem.product)
            ).get(pi.id)
            sp = Salesperson.query.filter_by(name=pi.salesperson).first()
            sp_info = {'phone': sp.phone, 'email': sp.email} if sp else {}
            pdf_filename = generate_pi_pdf(pi_full, app.config['PDF_DIR'], sp_info)
            excel_filename = generate_pi_excel(pi_full, app.config['PDF_DIR'])
            pi.pdf_path = pdf_filename
            pi.excel_path = excel_filename
        except Exception as e:
            db.session.rollback()
            flash(f'Error generating PDF: {str(e)}', 'danger')
            return render_template('create_pi.html', customers=customers,
                                   products=products, pi=None,
                                   today=issue_date.strftime('%Y-%m-%d'),
                                   selected_customer_id=customer_id)

        db.session.commit()
        flash(f'PI {pi_number} created and PDF generated.', 'success')
        return redirect(url_for('pi_list'))

    # GET request
    selected_customer_id = request.args.get('customer_id', type=int)
    preselected_salesperson = ''
    if selected_customer_id:
        cust = Customer.query.get(selected_customer_id)
        if cust:
            preselected_salesperson = cust.salesperson
    return render_template('create_pi.html', customers=customers,
                           products=products, pi=None,
                           today=date.today().strftime('%Y-%m-%d'),
                           selected_customer_id=selected_customer_id,
                           preselected_salesperson=preselected_salesperson)


@app.route('/pi/list')
@login_required
def pi_list():
    salesperson_filter = request.args.get('salesperson', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()

    query = filter_by_user(PI.query.options(joinedload(PI.customer)), PI, 'salesperson')

    if salesperson_filter:
        query = query.filter(PI.salesperson == salesperson_filter)
    if date_from:
        try:
            d_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            query = query.filter(PI.issue_date >= d_from)
        except ValueError:
            pass
    if date_to:
        try:
            d_to = datetime.strptime(date_to, '%Y-%m-%d').date()
            query = query.filter(PI.issue_date <= d_to)
        except ValueError:
            pass

    pis = query.order_by(PI.created_at.desc()).all()

    # Total for this filtered set
    filtered_total = sum(pi.total_amount for pi in pis)

    return render_template('pi_list.html', pis=pis,
                           salesperson_filter=salesperson_filter,
                           date_from=date_from, date_to=date_to,
                           filtered_total=filtered_total)


@app.route('/pi/<int:id>')
@login_required
def pi_detail(id):
    pi = PI.query.options(
        joinedload(PI.customer),
        joinedload(PI.items).joinedload(PIItem.product),
    ).get_or_404(id)
    return render_template('pi_detail.html', pi=pi)


@app.route('/pi/<int:id>/preview')
@login_required
def pi_preview(id):
    pi = PI.query.options(
        joinedload(PI.customer),
        joinedload(PI.items).joinedload(PIItem.product),
    ).get_or_404(id)
    return render_template('pi_preview.html', pi=pi)


@app.route('/pi/<int:id>/download')
def pi_download(id):
    pi = PI.query.get_or_404(id)
    if not pi.pdf_path:
        flash('PDF file not found.', 'danger')
        return redirect(url_for('pi_detail', id=id))
    filepath = os.path.join(app.config['PDF_DIR'], pi.pdf_path)
    if not os.path.exists(filepath):
        flash('PDF file does not exist on disk.', 'danger')
        return redirect(url_for('pi_detail', id=id))
    return send_file(filepath, as_attachment=True, download_name=pi.pdf_path)


@app.route('/pi/<int:id>/excel')
@login_required
def pi_excel_download(id):
    pi = PI.query.options(
        joinedload(PI.customer),
        joinedload(PI.items).joinedload(PIItem.product),
    ).get_or_404(id)
    # Auto-generate if missing
    if not pi.excel_path or not os.path.exists(os.path.join(app.config['PDF_DIR'], pi.excel_path)):
        try:
            fn = generate_pi_excel(pi, app.config['PDF_DIR'])
            pi.excel_path = fn
            db.session.commit()
        except Exception as e:
            flash(f'Error generating Excel: {e}', 'danger')
            return redirect(url_for('pi_detail', id=id))
    filepath = os.path.join(app.config['PDF_DIR'], pi.excel_path)
    return send_file(filepath, as_attachment=True, download_name=pi.excel_path)


@app.route('/pi/<int:id>/toggle-paid', methods=['POST'])
@login_required
def pi_toggle_paid(id):
    pi = PI.query.get_or_404(id)
    received_str = request.form.get('received_amount', '').strip()
    try:
        amount = float(received_str) if received_str else pi.total_amount
    except ValueError:
        amount = pi.total_amount
    if amount <= 0:
        flash('Amount must be greater than 0.', 'danger')
        return redirect(request.referrer or url_for('pi_list'))

    # Add payment record
    db.session.add(Payment(pi_id=pi.id, amount=amount))

    # Update PI aggregates
    total_paid = sum(p.amount for p in pi.payments)
    pi.received_amount = total_paid
    pi.paid = total_paid >= pi.total_amount

    # Update customer's total_deal_usd
    customer = Customer.query.get(pi.customer_id)
    if customer:
        paid_pis = PI.query.filter_by(customer_id=customer.id, paid=True).all()
        total = 0.0
        for p in paid_pis:
            deal_amount = p.received_amount if p.received_amount > 0 else p.total_amount
            if p.currency == 'RMB':
                deal_amount = round(deal_amount / 7.0, 2)
            total += deal_amount
        customer.total_deal_usd = round(total, 2)

    db.session.commit()
    remaining = max(0, pi.total_amount - total_paid)
    flash(f'Payment ${amount:,.2f} recorded. Total received: ${total_paid:,.2f}. Remaining: ${remaining:,.2f}.', 'success')
    return redirect(request.referrer or url_for('pi_list'))

@app.route('/pi/<int:id>/payment/<int:pid>/delete', methods=['POST'])
@login_required
def payment_delete(id, pid):
    payment = Payment.query.get_or_404(pid)
    pi = PI.query.get_or_404(id)
    db.session.delete(payment)
    # Recalculate
    total_paid = sum(p.amount for p in pi.payments)
    pi.received_amount = total_paid
    pi.paid = total_paid >= pi.total_amount
    # Update customer
    customer = Customer.query.get(pi.customer_id)
    if customer:
        paid_pis = PI.query.filter_by(customer_id=customer.id, paid=True).all()
        total = 0.0
        for p in paid_pis:
            deal_amount = p.received_amount if p.received_amount > 0 else p.total_amount
            if p.currency == 'RMB': deal_amount = round(deal_amount / 7.0, 2)
            total += deal_amount
        customer.total_deal_usd = round(total, 2)
    db.session.commit()
    flash('Payment record deleted.', 'info')
    return redirect(request.referrer or url_for('pi_list'))


@app.route('/api/pi/<int:id>/payments')
@login_required
def api_pi_payments(id):
    pi = PI.query.get_or_404(id)
    return jsonify({
        'currency': pi.currency or 'USD',
        'total_amount': pi.total_amount,
        'received': pi.received_amount or 0,
        'paid': pi.paid,
        'payments': [{'id': p.id, 'amount': p.amount, 'created_at': p.created_at.strftime('%Y-%m-%d %H:%M') if p.created_at else ''} for p in pi.payments]
    })


@app.route('/pi/<int:id>/delete', methods=['POST'])
def pi_delete(id):
    pi = PI.query.get_or_404(id)
    # Delete PDF file if exists
    if pi.pdf_path:
        filepath = os.path.join(app.config['PDF_DIR'], pi.pdf_path)
        if os.path.exists(filepath):
            os.remove(filepath)
    db.session.delete(pi)
    db.session.commit()
    flash('PI deleted successfully.', 'success')
    return redirect(url_for('pi_list'))


@app.route('/pi/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def pi_edit(id):
    pi = PI.query.options(
        joinedload(PI.customer),
        joinedload(PI.items).joinedload(PIItem.product),
    ).get_or_404(id)
    customers = Customer.query.order_by(Customer.name).all()
    products = Product.query.order_by(Product.name).all()
    # Map existing items: product_id -> {quantity, selected}
    existing_items = {item.product_id: item.quantity for item in pi.items}

    if request.method == 'POST':
        customer_id = request.form.get('customer_id', type=int)
        salesperson = request.form.get('salesperson', '').strip()
        payment_terms = request.form.get('payment_terms', '').strip()
        bank_info = request.form.get('bank_info', '').strip()
        notes = request.form.get('notes', '').strip()
        issue_date_str = request.form.get('issue_date', '').strip()
        currency = request.form.get('currency', 'USD').strip()
        company = request.form.get('company', 'klista').strip()
        account_id = request.form.get('account_id', type=int)

        if not customer_id:
            flash('Please select a customer.', 'danger')
            return render_template('pi_edit.html', pi=pi, customers=customers,
                                   products=products, existing_items=existing_items)

        if not salesperson:
            flash('Please select a salesperson.', 'danger')
            return render_template('pi_edit.html', pi=pi, customers=customers,
                                   products=products, existing_items=existing_items)

        try:
            issue_date = datetime.strptime(issue_date_str, '%Y-%m-%d').date() if issue_date_str else pi.issue_date
        except ValueError:
            issue_date = pi.issue_date

        # Collect selected products
        selected_items = []
        total_amount = 0.0
        for product in products:
            qty_key = f'qty_{product.id}'
            selected_key = f'selected_{product.id}'
            if request.form.get(selected_key) == 'on':
                try:
                    qty = int(request.form.get(qty_key, '1').strip() or '1')
                except ValueError:
                    qty = 1
                unit_price_str = request.form.get(f'unit_price_{product.id}', '').strip()
                try:
                    unit_price = float(unit_price_str) if unit_price_str else product.unit_price
                except ValueError:
                    unit_price = product.unit_price
                if qty > 0:
                    amount = round(unit_price * qty, 2)
                    selected_items.append({
                        'product': product,
                        'quantity': qty,
                        'unit_price': unit_price,
                        'amount': amount,
                    })
                    total_amount += amount

        if not selected_items:
            flash('Please select at least one product.', 'danger')
            return render_template('pi_edit.html', pi=pi, customers=customers,
                                   products=products, existing_items=existing_items)

        total_amount = round(total_amount, 2)

        # Update PI record
        pi.customer_id = customer_id
        pi.salesperson = salesperson
        pi.currency = currency
        pi.company = company
        pi.issue_date = issue_date
        pi.payment_terms = payment_terms or '100% TT before shipment'
        bank_info_from_account = ''
        if account_id:
            acct = Account.query.get(account_id)
            if acct: bank_info_from_account = acct.bank_info()
        pi.bank_info = bank_info or bank_info_from_account
        pi.total_amount = total_amount
        pi.notes = notes

        # Replace items
        PIItem.query.filter_by(pi_id=pi.id).delete()
        for item in selected_items:
            pi_item = PIItem(
                pi_id=pi.id,
                product_id=item['product'].id,
                quantity=item['quantity'],
                unit_price=item['unit_price'],
                amount=item['amount'],
            )
            db.session.add(pi_item)

        db.session.flush()

        # Regenerate PDF
        try:
            pi_full = PI.query.options(
                joinedload(PI.items).joinedload(PIItem.product)
            ).get(pi.id)
            sp = Salesperson.query.filter_by(name=pi.salesperson).first()
            sp_info = {'phone': sp.phone, 'email': sp.email} if sp else {}
            pdf_filename = generate_pi_pdf(pi_full, app.config['PDF_DIR'], sp_info)
            excel_filename = generate_pi_excel(pi_full, app.config['PDF_DIR'])
            pi.pdf_path = pdf_filename
            pi.excel_path = excel_filename
        except Exception as e:
            db.session.rollback()
            flash(f'Error generating PDF: {str(e)}', 'danger')
            return render_template('pi_edit.html', pi=pi, customers=customers,
                                   products=products, existing_items=existing_items)

        db.session.commit()
        flash(f'PI {pi.pi_number} updated and PDF regenerated.', 'success')
        return redirect(url_for('pi_list'))

    # GET request — preload only the products that are in existing items
    preload = {}
    for pid, qty in existing_items.items():
        prod = Product.query.get(int(pid))
        if prod:
            preload[pid] = {'id': prod.id, 'name': prod.name, 'code': prod.product_code,
                            'spec': prod.specification or '', 'price': prod.unit_price, 'img': prod.image or '', 'qty': qty}
    return render_template('pi_edit.html', pi=pi, customers=customers,
                           products=products, existing_items=existing_items,
                           preload_products=preload)


# ═══════════════════════════════════════════════════════════════════════
#  Context processors — inject globals into templates
# ═══════════════════════════════════════════════════════════════════════

@app.context_processor
def inject_globals():
    user = get_current_user()
    return {
        'company': COMPANY_CONFIG,
        'app_root': APP_ROOT,
        'all_salespersons': Salesperson.query.order_by(Salesperson.name).all(),
        'all_accounts': Account.query.order_by(Account.name).all(),
        'current_user': user,
        'is_admin': is_admin(),
    }


# ═══════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print(f"App root: {APP_ROOT}")
    print(f"Database: {os.path.join(APP_ROOT, 'instance', 'pi_manager.db')}")
    print(f"PDF directory: {app.config['PDF_DIR']}")
    print("Starting Flask dev server on http://0.0.0.0:5000 ...")
    app.run(host='0.0.0.0', port=5000, debug=True)
