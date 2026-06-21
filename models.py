from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date

db = SQLAlchemy()


class Customer(db.Model):
    __tablename__ = 'customers'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    country = db.Column(db.String(100), default='')
    contact_person = db.Column(db.String(100), default='')
    email = db.Column(db.String(200), default='')
    phone = db.Column(db.String(50), default='')
    address = db.Column(db.Text, default='')
    salesperson = db.Column(db.String(100), default='')
    total_deal_usd = db.Column(db.Float, default=0.0)
    image = db.Column(db.String(500), default='')
    notes = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    pis = db.relationship('PI', backref='customer', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'country': self.country,
            'contact_person': self.contact_person,
            'email': self.email,
            'phone': self.phone,
            'address': self.address,
            'salesperson': self.salesperson,
            'total_deal_usd': self.total_deal_usd,
            'image': self.image,
            'notes': self.notes,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else '',
        }


class Account(db.Model):
    __tablename__ = 'accounts'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)  # Display name
    company_name = db.Column(db.String(300), default='')
    bank_name = db.Column(db.String(200), default='')
    account_no = db.Column(db.String(100), default='')
    swift_code = db.Column(db.String(50), default='')
    brand = db.Column(db.String(20), default='klista')  # 'klista' or 'qisuo'
    currency = db.Column(db.String(3), default='USD')
    notes = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def bank_info(self):
        parts = []
        if self.bank_name: parts.append(self.bank_name)
        if self.account_no: parts.append(f'A/C: {self.account_no}')
        if self.swift_code: parts.append(f'SWIFT: {self.swift_code}')
        return '\n'.join(parts)

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'company_name': self.company_name,
            'bank_name': self.bank_name, 'account_no': self.account_no,
            'swift_code': self.swift_code, 'brand': self.brand, 'currency': self.currency, 'notes': self.notes,
        }


class Payment(db.Model):
    __tablename__ = 'payments'

    id = db.Column(db.Integer, primary_key=True)
    pi_id = db.Column(db.Integer, db.ForeignKey('pis.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False, default=0.0)
    fee = db.Column(db.Float, default=0.0)
    order_no = db.Column(db.String(200), default='')
    note = db.Column(db.String(200), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    pi = db.relationship('PI', backref=db.backref('payments', lazy=True, cascade='all, delete-orphan'))

    def to_dict(self):
        return {'id': self.id, 'pi_id': self.pi_id, 'amount': self.amount,
                'fee': self.fee, 'order_no': self.order_no,
                'note': self.note, 'created_at': self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else ''}


class Salesperson(db.Model):
    __tablename__ = 'salespersons'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    phone = db.Column(db.String(50), default='')
    email = db.Column(db.String(200), default='')
    dingtalk_user_id = db.Column(db.String(100), default='')
    notes = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'phone': self.phone,
            'email': self.email,
            'notes': self.notes,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else '',
        }


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False, unique=True)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='salesperson')  # 'admin' or 'salesperson'
    salesperson_name = db.Column(db.String(100), default='')
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'role': self.role,
            'salesperson_name': self.salesperson_name,
        }


class Product(db.Model):
    __tablename__ = 'products'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    product_code = db.Column(db.String(100), default='')
    specification = db.Column(db.String(200), default='')
    chinese_name = db.Column(db.String(200), default='')
    unit_price = db.Column(db.Float, nullable=False, default=0.0)
    unit_price_rmb = db.Column(db.Float, nullable=False, default=0.0)
    notes = db.Column(db.Text, default='')
    image = db.Column(db.String(500), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'product_code': self.product_code,
            'specification': self.specification,
            'chinese_name': self.chinese_name,
            'unit_price': self.unit_price,
            'unit_price_rmb': self.unit_price_rmb,
            'notes': self.notes,
            'image': self.image,
        }


class PI(db.Model):
    __tablename__ = 'pis'

    id = db.Column(db.Integer, primary_key=True)
    pi_number = db.Column(db.String(50), nullable=False, unique=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    issue_date = db.Column(db.Date, default=date.today)
    payment_terms = db.Column(db.Text, default='100% TT before shipment')
    bank_info = db.Column(db.Text, default='')
    salesperson = db.Column(db.String(100), nullable=False, default='')
    currency = db.Column(db.String(3), default='USD')
    company = db.Column(db.String(50), default='klista')
    total_amount = db.Column(db.Float, default=0.0)
    shipping_cost = db.Column(db.Float, default=0.0)
    shipping_note = db.Column(db.Text, default='')
    actual_shipping_cost = db.Column(db.Float, default=0.0)
    procurement_confirmed = db.Column(db.Boolean, default=False)
    pdf_path = db.Column(db.String(500), default='')
    excel_path = db.Column(db.String(500), default='')
    paid = db.Column(db.Boolean, default=False)
    received_amount = db.Column(db.Float, default=0.0)
    shipping_address = db.Column(db.Text, default='')
    notes = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship('PIItem', backref='pi', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'pi_number': self.pi_number,
            'customer_id': self.customer_id,
            'issue_date': self.issue_date.strftime('%Y-%m-%d') if self.issue_date else '',
            'payment_terms': self.payment_terms,
            'bank_info': self.bank_info,
            'salesperson': self.salesperson,
            'currency': self.currency,
            'total_amount': self.total_amount,
            'pdf_path': self.pdf_path,
            'paid': self.paid,
            'notes': self.notes,
        }


class PIItem(db.Model):
    __tablename__ = 'pi_items'

    id = db.Column(db.Integer, primary_key=True)
    pi_id = db.Column(db.Integer, db.ForeignKey('pis.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Float, nullable=False, default=0.0)
    amount = db.Column(db.Float, nullable=False, default=0.0)

    product = db.relationship('Product', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'pi_id': self.pi_id,
            'product_id': self.product_id,
            'product_name': self.product.name if self.product else '',
            'product_code': self.product.product_code if self.product else '',
            'specification': self.product.specification if self.product else '',
            'quantity': self.quantity,
            'unit_price': self.unit_price,
            'amount': self.amount,
        }


class Expense(db.Model):
    __tablename__ = 'expenses'

    id = db.Column(db.Integer, primary_key=True)
    pi_id = db.Column(db.Integer, db.ForeignKey('pis.id'), nullable=True)
    category = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False, default=0.0)
    currency = db.Column(db.String(3), default='USD')
    note = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    pi = db.relationship('PI', backref=db.backref('expenses', lazy=True, cascade='all, delete-orphan'))

    def to_dict(self):
        return {
            'id': self.id,
            'pi_id': self.pi_id,
            'category': self.category,
            'amount': self.amount,
            'currency': self.currency,
            'note': self.note,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else '',
        }


class Supplier(db.Model):
    __tablename__ = 'suppliers'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    contact_person = db.Column(db.String(100), default='')
    phone = db.Column(db.String(50), default='')
    email = db.Column(db.String(200), default='')
    address = db.Column(db.Text, default='')
    notes = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'contact_person': self.contact_person,
            'phone': self.phone,
            'email': self.email,
            'address': self.address,
            'notes': self.notes,
        }


class Procurement(db.Model):
    __tablename__ = 'procurements'

    id = db.Column(db.Integer, primary_key=True)
    pi_id = db.Column(db.Integer, db.ForeignKey('pis.id'), nullable=False)
    pi_item_id = db.Column(db.Integer, db.ForeignKey('pi_items.id'), nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=True)
    unit_price = db.Column(db.Float, nullable=False, default=0.0)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    total = db.Column(db.Float, nullable=False, default=0.0)
    procurement_date = db.Column(db.String(20), default='')
    note = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    pi = db.relationship('PI', backref=db.backref('procurements', lazy=True, cascade='all, delete-orphan'))
    pi_item = db.relationship('PIItem', backref=db.backref('procurements', lazy=True, cascade='all, delete-orphan'))
    supplier = db.relationship('Supplier', backref=db.backref('procurements', lazy=True))

    def to_dict(self):
        return {
            'id': self.id,
            'pi_id': self.pi_id,
            'pi_item_id': self.pi_item_id,
            'supplier_id': self.supplier_id,
            'supplier_name': self.supplier.name if self.supplier else '',
            'unit_price': self.unit_price,
            'quantity': self.quantity,
            'total': self.total,
            'procurement_date': self.procurement_date,
            'note': self.note,
        }
