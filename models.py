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
    deleted_at = db.Column(db.DateTime, nullable=True, index=True)
    version = db.Column(db.Integer, nullable=False, default=1)
    __mapper_args__ = {'version_id_col': version}

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
            'version': self.version,
        }


class Account(db.Model):
    __tablename__ = 'accounts'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)  # Display name
    company_name = db.Column(db.String(300), default='')
    country_region = db.Column(db.String(100), default='')
    beneficiary_address = db.Column(db.Text, default='')
    bank_name = db.Column(db.String(200), default='')
    bank_address = db.Column(db.Text, default='')
    account_no = db.Column(db.String(100), default='')
    swift_code = db.Column(db.String(50), default='')
    bank_code = db.Column(db.String(50), default='')
    branch_code = db.Column(db.String(50), default='')
    brand = db.Column(db.String(20), default='klista')  # 'klista' or 'qisuo'
    currency = db.Column(db.String(3), default='USD')
    notes = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def bank_info(self):
        parts = []
        if self.company_name: parts.append(f'Beneficiary: {self.company_name}')
        if self.account_no: parts.append(f'A/C: {self.account_no}')
        if self.country_region: parts.append(f'Country/Region: {self.country_region}')
        if self.beneficiary_address: parts.append(f'Beneficiary Address: {self.beneficiary_address}')
        if self.bank_name: parts.append(f'Bank Name: {self.bank_name}')
        if self.bank_address: parts.append(f'Bank Address: {self.bank_address}')
        if self.swift_code: parts.append(f'SWIFT: {self.swift_code}')
        if self.bank_code: parts.append(f'Bank Code: {self.bank_code}')
        if self.branch_code: parts.append(f'Branch Code: {self.branch_code}')
        if self.currency: parts.append(f'Currency: {self.currency}')
        return '\n'.join(parts)

    def snapshot(self):
        """Return the complete bank group used when a PI is issued."""
        return {
            'bank_beneficiary_name': self.company_name or '',
            'bank_account_no': self.account_no or '',
            'bank_country_region': self.country_region or '',
            'bank_beneficiary_address': self.beneficiary_address or '',
            'bank_name': self.bank_name or '',
            'bank_address': self.bank_address or '',
            'bank_swift_code': self.swift_code or '',
            'bank_code': self.bank_code or '',
            'bank_branch_code': self.branch_code or '',
            'bank_currency': (self.currency or '').upper(),
        }

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'company_name': self.company_name,
            'bank_name': self.bank_name, 'account_no': self.account_no,
            'country_region': self.country_region,
            'beneficiary_address': self.beneficiary_address,
            'bank_address': self.bank_address,
            'swift_code': self.swift_code, 'bank_code': self.bank_code,
            'branch_code': self.branch_code,
            'brand': self.brand, 'currency': self.currency, 'notes': self.notes,
        }


class FieldOption(db.Model):
    """Administrator-managed choices used by business forms."""
    __tablename__ = 'field_options'
    __table_args__ = (
        db.UniqueConstraint('field_key', 'value', name='uq_field_option_key_value'),
    )

    id = db.Column(db.Integer, primary_key=True)
    field_key = db.Column(db.String(50), nullable=False, index=True)
    value = db.Column(db.String(200), nullable=False)
    english_value = db.Column(db.String(200), nullable=False, default='')
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'field_key': self.field_key,
            'value': self.value,
            'english_value': self.english_value,
            'sort_order': self.sort_order,
        }


class DocumentTemplate(db.Model):
    """Administrator-managed PI export template.

    Custom files are stored outside the public static directory.  ``filename``
    is deliberately a basename instead of an arbitrary path so a database row
    can never make the application read files outside the template directory.
    """
    __tablename__ = 'document_templates'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    code = db.Column(db.String(100), nullable=False, unique=True)
    template_type = db.Column(db.String(20), nullable=False, default='xlsx')
    filename = db.Column(db.String(255), nullable=False, default='')
    active = db.Column(db.Boolean, nullable=False, default=True)
    is_default = db.Column(db.Boolean, nullable=False, default=False)
    notes = db.Column(db.Text, default='')
    created_by = db.Column(db.String(100), default='')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow,
                           onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'code': self.code,
            'template_type': self.template_type,
            'filename': self.filename,
            'active': self.active,
            'is_default': self.is_default,
            'notes': self.notes,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if self.created_at else '',
        }


class Payment(db.Model):
    __tablename__ = 'payments'

    id = db.Column(db.Integer, primary_key=True)
    pi_id = db.Column(db.Integer, db.ForeignKey('pis.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False, default=0.0)
    fee = db.Column(db.Float, default=0.0)
    order_no = db.Column(db.String(200), default='')
    order_no_normalized = db.Column(db.String(200), nullable=True)
    idempotency_key = db.Column(db.String(64), nullable=True)
    # Keep a snapshot instead of a foreign key so historical receipts remain
    # traceable even if an account is later renamed or removed.
    receiving_account_id = db.Column(db.Integer, nullable=True)
    receiving_account_name = db.Column(db.String(200), default='')
    receiving_account_currency = db.Column(db.String(3), default='')
    attachment = db.Column(db.String(500), default='')
    note = db.Column(db.String(200), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    deleted_at = db.Column(db.DateTime, nullable=True, index=True)

    pi = db.relationship('PI', backref=db.backref('payments', lazy=True, cascade='all, delete-orphan'))

    def to_dict(self):
        return {'id': self.id, 'pi_id': self.pi_id, 'amount': self.amount,
                'fee': self.fee, 'order_no': self.order_no,
                'receiving_account_id': self.receiving_account_id,
                'receiving_account_name': self.receiving_account_name,
                'receiving_account_currency': self.receiving_account_currency,
                'has_attachment': bool(self.attachment),
                'note': self.note, 'created_at': self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else '',
                'deleted_at': self.deleted_at.isoformat() if self.deleted_at else None}


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
    # ``account`` is the stable login identifier.  ``username`` remains the
    # employee/display name shown throughout the business UI.
    account = db.Column(db.String(100), nullable=False, unique=True, index=True)
    username = db.Column(db.String(100), nullable=False, unique=True)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='salesperson')  # 'admin' or 'salesperson'
    salesperson_name = db.Column(db.String(100), default='')
    active = db.Column(db.Boolean, nullable=False, default=True)
    must_change_password = db.Column(db.Boolean, nullable=False, default=True)
    # Increment whenever credentials or authorization change.  Existing
    # sessions carry the previous value and are rejected immediately.
    auth_version = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'account': self.account,
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
    # Customs master data. Existing products are backfilled with the company's
    # common welding/cutting-parts declaration profile during migration; users
    # can then adjust the smaller number of exceptions product by product.
    customs_hs_code = db.Column(db.String(20), nullable=False, default='8515900090')
    customs_name_cn = db.Column(db.String(200), nullable=False, default='焊割设备配件')
    customs_name_en = db.Column(db.String(200), nullable=False, default='Welding & Cutting Equipment Parts')
    customs_unit = db.Column(db.String(30), nullable=False, default='件')
    customs_brand_type = db.Column(db.String(100), nullable=False, default='无品牌')
    customs_brand = db.Column(db.String(100), nullable=False, default='无品牌')
    customs_preferential = db.Column(db.String(100), nullable=False, default='无')
    customs_purpose = db.Column(
        db.Text, nullable=False,
        default='用于焊接及等离子切割设备的导电、连接、夹持和气流控制等',
    )
    customs_origin_country = db.Column(db.String(100), nullable=False, default='中国')
    customs_domestic_source = db.Column(db.String(100), nullable=False, default='常州其他')
    customs_tax_exemption = db.Column(db.String(100), nullable=False, default='照章征税')
    customs_elements = db.Column(db.Text, nullable=False, default='')
    notes = db.Column(db.Text, default='')
    image = db.Column(db.String(500), default='')
    active = db.Column(db.Boolean, nullable=False, default=True)
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
            'customs_hs_code': self.customs_hs_code,
            'customs_name_cn': self.customs_name_cn,
            'customs_name_en': self.customs_name_en,
            'customs_unit': self.customs_unit,
            'customs_brand_type': self.customs_brand_type,
            'customs_brand': self.customs_brand,
            'customs_preferential': self.customs_preferential,
            'customs_purpose': self.customs_purpose,
            'customs_origin_country': self.customs_origin_country,
            'customs_domestic_source': self.customs_domestic_source,
            'customs_tax_exemption': self.customs_tax_exemption,
            'customs_elements': self.customs_elements,
            'notes': self.notes,
            'image': self.image,
            'active': self.active,
        }


class PI(db.Model):
    __tablename__ = 'pis'

    id = db.Column(db.Integer, primary_key=True)
    pi_number = db.Column(db.String(50), nullable=False, unique=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    issue_date = db.Column(db.Date, default=date.today)
    payment_terms = db.Column(db.Text, default='100% TT before shipment')
    price_terms = db.Column(db.String(200), default='')
    delivery_time = db.Column(db.String(200), default='')
    bank_info = db.Column(db.Text, default='')
    # Complete receiving-account snapshot.  Changing an account later must not
    # silently rewrite historical outward documents.
    bank_beneficiary_name = db.Column(db.String(300), default='')
    bank_account_no = db.Column(db.String(100), default='')
    bank_country_region = db.Column(db.String(100), default='')
    bank_beneficiary_address = db.Column(db.Text, default='')
    bank_name = db.Column(db.String(200), default='')
    bank_address = db.Column(db.Text, default='')
    bank_swift_code = db.Column(db.String(50), default='')
    bank_code = db.Column(db.String(50), default='')
    bank_branch_code = db.Column(db.String(50), default='')
    bank_currency = db.Column(db.String(3), default='')
    salesperson = db.Column(db.String(100), nullable=False, default='')
    currency = db.Column(db.String(3), default='USD')
    # Snapshot of the USD -> RMB business rate used by this PI.  It must not
    # follow later changes to the system default because historical quotation,
    # procurement and profit figures need to remain reproducible.
    exchange_rate = db.Column(db.Float, nullable=False, default=7.0)
    company = db.Column(db.String(50), default='klista')
    total_amount = db.Column(db.Float, default=0.0)
    shipping_cost = db.Column(db.Float, default=0.0)
    shipping_note = db.Column(db.Text, default='')
    shipping_note_en = db.Column(db.Text, default='')
    # Legacy database column retained for a no-data-loss migration.  The value
    # now means the RMB freight charged by the supplier for this purchase.
    actual_shipping_cost = db.Column(db.Float, default=0.0)
    procurement_confirmed = db.Column(db.Boolean, default=False)
    shipping_completed = db.Column(db.Boolean, default=False)
    shipping_date = db.Column(db.Date, nullable=True)
    shipping_tracking_no = db.Column(db.String(200), default='')
    shipping_record_note = db.Column(db.Text, default='')
    shipping_recorded_at = db.Column(db.DateTime, nullable=True)
    shipping_recorded_by = db.Column(db.String(100), default='')
    procurement_status = db.Column(db.String(20), nullable=False, default='未回款')
    # NULL means this business record has not been filled in yet. False is a
    # deliberate "no customs declaration required" decision.
    customs_required = db.Column(db.Boolean, nullable=True, default=None)
    customs_note = db.Column(db.Text, default='')
    customs_recorded_at = db.Column(db.DateTime, nullable=True)
    customs_recorded_by = db.Column(db.String(100), default='')
    pdf_path = db.Column(db.String(500), default='')
    excel_path = db.Column(db.String(500), default='')
    paid = db.Column(db.Boolean, default=False)
    received_amount = db.Column(db.Float, default=0.0)
    shipping_address = db.Column(db.Text, default='')
    notes = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    deleted_at = db.Column(db.DateTime, nullable=True, index=True)
    version = db.Column(db.Integer, nullable=False, default=1)
    __mapper_args__ = {'version_id_col': version}

    # PI rows are inserted in the user's chosen order.  Always load them by
    # their insertion id so previews and every export reproduce that order.
    items = db.relationship(
        'PIItem', backref='pi', lazy=True, cascade='all, delete-orphan',
        order_by='PIItem.id',
    )

    @property
    def active_payments(self):
        return [payment for payment in self.payments if payment.deleted_at is None]

    @property
    def product_subtotal(self):
        """Sum of PI items, kept in the legacy total_amount column."""
        return round(self.total_amount or 0.0, 2)

    @property
    def other_charges(self):
        """Freight/adjustment amount. A negative value represents a discount."""
        return round(self.shipping_cost or 0.0, 2)

    @property
    def supplier_freight_cost(self):
        """RMB freight cost attached to the supplier procurement order."""
        return round(self.actual_shipping_cost or 0.0, 2)

    @supplier_freight_cost.setter
    def supplier_freight_cost(self, value):
        self.actual_shipping_cost = value

    @property
    def grand_total(self):
        """Customer-facing order total: products plus charges/discounts."""
        return round(self.product_subtotal + self.other_charges, 2)

    @property
    def procurement_is_complete(self):
        """A confirmed purchase must cover the full quantity of every PI item."""
        if not self.procurement_confirmed or not self.items:
            return False
        purchased = {}
        for procurement in self.procurements:
            purchased[procurement.pi_item_id] = (
                purchased.get(procurement.pi_item_id, 0) + int(procurement.quantity or 0)
            )
        return all(
            int(item.quantity or 0) > 0
            and purchased.get(item.id, 0) >= int(item.quantity or 0)
            for item in self.items
        )

    @property
    def effective_procurement_status(self):
        """Derive order progress independently from payment records."""
        if self.shipping_completed:
            return '发货完成'
        if self.procurement_is_complete:
            return '采购完成'
        return '部分采购' if self.procurements else '待采购'

    def to_dict(self):
        return {
            'id': self.id,
            'pi_number': self.pi_number,
            'customer_id': self.customer_id,
            'issue_date': self.issue_date.strftime('%Y-%m-%d') if self.issue_date else '',
            'payment_terms': self.payment_terms,
            'price_terms': self.price_terms,
            'delivery_time': self.delivery_time,
            'bank_info': self.bank_info,
            'bank_beneficiary_name': self.bank_beneficiary_name,
            'bank_account_no': self.bank_account_no,
            'bank_country_region': self.bank_country_region,
            'bank_beneficiary_address': self.bank_beneficiary_address,
            'bank_name': self.bank_name,
            'bank_address': self.bank_address,
            'bank_swift_code': self.bank_swift_code,
            'bank_code': self.bank_code,
            'bank_branch_code': self.bank_branch_code,
            'bank_currency': self.bank_currency,
            'salesperson': self.salesperson,
            'currency': self.currency,
            'exchange_rate': self.exchange_rate,
            'total_amount': self.total_amount,
            'product_subtotal': self.product_subtotal,
            'other_charges': self.other_charges,
            'grand_total': self.grand_total,
            'supplier_freight_cost': self.supplier_freight_cost,
            'procurement_status': self.effective_procurement_status,
            'shipping_completed': bool(self.shipping_completed),
            'shipping_date': self.shipping_date.isoformat() if self.shipping_date else '',
            'shipping_tracking_no': self.shipping_tracking_no or '',
            'shipping_record_note': self.shipping_record_note or '',
            'shipping_recorded_at': (
                self.shipping_recorded_at.isoformat()
                if self.shipping_recorded_at else ''
            ),
            'shipping_recorded_by': self.shipping_recorded_by or '',
            'customs_required': self.customs_required,
            'customs_note': self.customs_note or '',
            'customs_recorded_at': (
                self.customs_recorded_at.isoformat()
                if self.customs_recorded_at else ''
            ),
            'customs_recorded_by': self.customs_recorded_by or '',
            'pdf_path': self.pdf_path,
            'paid': self.paid,
            'notes': self.notes,
            'version': self.version,
        }


class AuditLog(db.Model):
    """Append-only record of sensitive business changes."""
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    username = db.Column(db.String(100), nullable=False, default='system')
    action = db.Column(db.String(50), nullable=False)
    entity_type = db.Column(db.String(50), nullable=False)
    entity_id = db.Column(db.Integer, nullable=True)
    summary = db.Column(db.String(300), default='')
    before_json = db.Column(db.Text, default='')
    after_json = db.Column(db.Text, default='')
    ip_address = db.Column(db.String(64), default='')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)


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


class PackingList(db.Model):
    """A PI packing plan, kept separate from the customer-facing PI rows."""
    __tablename__ = 'packing_lists'

    id = db.Column(db.Integer, primary_key=True)
    pi_id = db.Column(db.Integer, db.ForeignKey('pis.id'), nullable=False,
                      unique=True, index=True)
    status = db.Column(db.String(20), nullable=False, default='draft')
    packing_date = db.Column(db.Date, nullable=True)
    created_by = db.Column(db.String(100), nullable=False, default='')
    updated_by = db.Column(db.String(100), nullable=False, default='')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow,
                           onupdate=datetime.utcnow)
    version = db.Column(db.Integer, nullable=False, default=1)
    __mapper_args__ = {'version_id_col': version}

    pi = db.relationship(
        'PI', backref=db.backref('packing_list', uselist=False, lazy=True,
                                cascade='all, delete-orphan')
    )
    boxes = db.relationship(
        'PackingBox', backref='packing_list', lazy=True,
        cascade='all, delete-orphan', order_by='PackingBox.sort_order',
    )

    @property
    def is_completed(self):
        return self.status == 'completed'


class PackingBox(db.Model):
    __tablename__ = 'packing_boxes'
    __table_args__ = (
        db.UniqueConstraint('packing_list_id', 'box_no',
                            name='uq_packing_list_box_no'),
    )

    id = db.Column(db.Integer, primary_key=True)
    packing_list_id = db.Column(db.Integer, db.ForeignKey('packing_lists.id'),
                                nullable=False, index=True)
    box_no = db.Column(db.String(50), nullable=False)
    net_weight = db.Column(db.Float, nullable=False, default=0.0)
    gross_weight = db.Column(db.Float, nullable=False, default=0.0)
    length_cm = db.Column(db.Float, nullable=False, default=0.0)
    width_cm = db.Column(db.Float, nullable=False, default=0.0)
    height_cm = db.Column(db.Float, nullable=False, default=0.0)
    volume_cbm = db.Column(db.Float, nullable=False, default=0.0)
    shipping_mark = db.Column(db.String(300), default='')
    note = db.Column(db.String(500), default='')
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    items = db.relationship(
        'PackingItem', backref='box', lazy=True, cascade='all, delete-orphan',
        order_by='PackingItem.sort_order',
    )


class PackingItem(db.Model):
    __tablename__ = 'packing_items'

    id = db.Column(db.Integer, primary_key=True)
    packing_box_id = db.Column(db.Integer, db.ForeignKey('packing_boxes.id'),
                               nullable=False, index=True)
    pi_item_id = db.Column(db.Integer, db.ForeignKey('pi_items.id'),
                           nullable=False, index=True)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    product_name = db.Column(db.String(200), nullable=False, default='')
    product_code = db.Column(db.String(100), default='')
    specification = db.Column(db.String(200), default='')
    note = db.Column(db.String(500), default='')
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    pi_item = db.relationship('PIItem', lazy=True)


class Expense(db.Model):
    __tablename__ = 'expenses'

    id = db.Column(db.Integer, primary_key=True)
    pi_id = db.Column(db.Integer, db.ForeignKey('pis.id'), nullable=True)
    category = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False, default=0.0)
    currency = db.Column(db.String(3), default='USD')
    note = db.Column(db.Text, default='')
    attachment = db.Column(db.String(500), default='')
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
            'has_attachment': bool(self.attachment),
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
