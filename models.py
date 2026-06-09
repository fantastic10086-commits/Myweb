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
            'notes': self.notes,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else '',
        }


class Salesperson(db.Model):
    __tablename__ = 'salespersons'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    phone = db.Column(db.String(50), default='')
    email = db.Column(db.String(200), default='')
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
    unit_price = db.Column(db.Float, nullable=False, default=0.0)
    notes = db.Column(db.Text, default='')
    image = db.Column(db.String(500), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'product_code': self.product_code,
            'specification': self.specification,
            'unit_price': self.unit_price,
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
    pdf_path = db.Column(db.String(500), default='')
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
