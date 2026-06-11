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
from models import db, Customer, Product, PI, PIItem, Salesperson, User
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
        'customers': {'salesperson': 'VARCHAR(100)', 'created_at': 'DATETIME'},
        'products': {'image': 'VARCHAR(500)'},
        'pis': {'salesperson': 'VARCHAR(100)', 'currency': 'VARCHAR(3)', 'company': 'VARCHAR(50)', 'excel_path': 'VARCHAR(500)'},
        'salespersons': {'phone': 'VARCHAR(50)', 'email': 'VARCHAR(200)'},
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

    return render_template('sales_stats.html',
                           stats=results,
                           grand_total=grand_total,
                           grand_pi_count=grand_pi_count,
                           date_from=date_from,
                           date_to=date_to,
                           preset=preset)


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
        pi = PI(
            pi_number=pi_number,
            customer_id=customer_id,
            issue_date=issue_date,
            payment_terms=payment_terms or '100% TT before shipment',
            bank_info=bank_info or '',
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
        pi.bank_info = bank_info or ''
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

    # GET request
    return render_template('pi_edit.html', pi=pi, customers=customers,
                           products=products, existing_items=existing_items)


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
