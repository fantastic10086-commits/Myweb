"""Session-authenticated iPhone API; files share the existing customer/PI library."""
import hashlib
import os
import uuid
from datetime import datetime
from flask import Blueprint, abort, jsonify, request, session, current_app, send_file
from flask_wtf.csrf import generate_csrf
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import HTTPException
from werkzeug.utils import secure_filename
from models import db, Customer, CustomerFile, PI, OrderPhotoUpload


def register_mobile_photos(app, *, current_user, is_admin, login, customer_access,
                           pi_access, validate_file, save_file, remove_file, audit, thumbnail):
    bp = Blueprint('mobile_photos', __name__, url_prefix='/api/mobile')

    # Run before existing HTML login/maintenance redirects and before CSRF parsing.
    def guard():
        if not request.path.startswith('/api/mobile/'):
            return None
        user = current_user()
        if user and (not user.active or session.get('auth_version') != user.auth_version):
            session.clear()
            user = None
        if request.path in {'/api/mobile/session', '/api/mobile/login'}:
            return None
        if not user:
            return jsonify(error='登录已过期，请重新登录。'), 401
        if user.must_change_password:
            return jsonify(error='请先在网页系统修改临时密码，再登录 App。'), 403
    app.before_request_funcs.setdefault(None, []).insert(0, guard)

    @app.after_request
    def mobile_response(response):
        if request.path.startswith('/api/mobile/'):
            # Existing global guards can return HTML; always provide a useful API error.
            if response.status_code in {301, 302, 303, 307, 308}:
                response = jsonify(error='请在网页系统完成密码修改后重新登录。')
                response.status_code = 403
            elif response.status_code >= 400 and not response.is_json:
                code = response.status_code
                messages = {400: '请求无效或登录凭据过期，请重新登录。', 413: '照片超过上传大小限制。', 503: '系统维护中，请稍后重试。'}
                response = jsonify(error=messages.get(code, '操作失败，请稍后重试。'))
                response.status_code = code
            response.headers['Cache-Control'] = 'no-store'
        return response

    @bp.errorhandler(HTTPException)
    def api_error(exc):
        return jsonify(error=exc.description), exc.code

    def user_payload(user):
        return {'id': user.id, 'name': user.username, 'is_admin': is_admin()}

    @bp.get('/session')
    def bootstrap():
        user = current_user()
        return jsonify(csrf_token=generate_csrf(), user=user_payload(user) if user else None)

    @bp.post('/login')
    def sign_in():
        result = login()  # Reuse password checking, throttling and session rotation.
        response = app.make_response(result)
        if response.status_code == 429:
            return jsonify(error='登录失败次数过多，请稍后再试。'), 429
        # get_current_user caches the pre-login lookup in g.
        from flask import g
        g.pop('current_user', None)
        user = current_user()
        if response.status_code != 302 or not user:
            return jsonify(error='账号或密码错误。'), 401
        if user.must_change_password:
            return jsonify(error='请先在网页系统修改临时密码，再登录 App。'), 403
        return jsonify(user=user_payload(user), csrf_token=generate_csrf())

    @bp.post('/logout')
    def sign_out():
        from order_chat import disable_session_device
        disable_session_device()
        from web_push import disable_session_web_push
        disable_session_web_push()
        session.clear()
        return jsonify(ok=True)

    def orders_query():
        query = PI.query.join(Customer).filter(
            PI.deleted_at.is_(None), Customer.deleted_at.is_(None), PI.received_amount > 0)
        if not is_admin():
            sp = current_user().salesperson_name
            if not sp:
                return query.filter(db.false())
            query = query.filter(PI.salesperson == sp, Customer.salesperson == sp)
        return query

    def accessible_order(id, paid=False):
        pi = db.session.get(PI, id)
        if not pi or pi.deleted_at or not pi.customer or pi.customer.deleted_at:
            abort(404, description='订单不存在或已删除。')
        customer_access(pi.customer)
        pi_access(pi)
        if paid and not (pi.received_amount or 0) > 0:
            abort(409, description='该订单目前没有回款，无法上传照片。')
        return pi

    def order_payload(pi):
        return {'id': pi.id, 'number': pi.pi_number, 'customer_name': pi.customer.name,
                'received_amount': pi.received_amount or 0, 'currency': pi.currency or 'USD'}

    def photo_payload(record):
        return {'id': record.id, 'name': record.original_name, 'note': record.note,
                'created_by': record.created_by, 'created_at': record.created_at.isoformat() + 'Z'}

    @bp.get('/orders')
    def orders():
        page = max(1, request.args.get('page', 1, type=int))
        q = request.args.get('q', '').strip()[:100]
        query = orders_query()
        if q:
            query = query.filter(db.or_(PI.pi_number.contains(q, autoescape=True), Customer.name.contains(q, autoescape=True)))
        result = query.order_by(PI.id.desc()).paginate(page=page, per_page=30, error_out=False)
        return jsonify(orders=[order_payload(pi) for pi in result.items], has_more=result.has_next)

    @bp.get('/orders/<int:id>')
    def order_detail(id):
        return jsonify(order=order_payload(accessible_order(id)))

    @bp.get('/orders/<int:id>/photos')
    def photos(id):
        pi = accessible_order(id)
        page = max(1, request.args.get('page', 1, type=int))
        result = CustomerFile.query.filter_by(pi_id=id, customer_id=pi.customer_id).filter(
            CustomerFile.deleted_at.is_(None), CustomerFile.mime_type.startswith('image/')
        ).order_by(CustomerFile.id.desc()).paginate(page=page, per_page=30, error_out=False)
        return jsonify(order=order_payload(pi), photos=[photo_payload(p) for p in result.items], has_more=result.has_next)

    @bp.post('/orders/<int:id>/photos')
    def upload(id):
        pi = accessible_order(id, paid=True)
        try:
            key = str(uuid.UUID(request.form.get('request_id', '')))
        except ValueError:
            abort(400, description='上传标识无效，请重新选择照片。')
        note = request.form.get('note', '').strip()
        if len(note) > 300:
            abort(400, description='备注不能超过 300 个字符。')
        file = request.files.get('photo')
        if not file or len(request.files.getlist('photo')) != 1:
            abort(400, description='每个请求必须包含一张照片。')
        try:
            name, ext, size, mime = validate_file(file)
        except ValueError as exc:
            abort(400, description=str(exc))
        if not mime.startswith('image/'):
            abort(400, description='这里只接受照片。')
        digest = hashlib.sha256(file.read()).hexdigest()
        file.seek(0)
        user_id = current_user().id

        def previous():
            item = OrderPhotoUpload.query.filter_by(user_id=user_id, request_id=key).first()
            if item:
                record = db.session.get(CustomerFile, item.file_id)
                if item.digest != digest or not record or record.pi_id != id or record.note != note or record.deleted_at:
                    abort(409, description='该上传标识已使用或照片已移除，请重新选择照片。')
                return record
            return None

        existing = previous()
        if existing:
            return jsonify(photo=photo_payload(existing)), 200
        stored = None
        try:
            stored = save_file(file, ext)
            record = CustomerFile(customer_id=pi.customer_id, pi_id=id, stored_name=stored,
                original_name=name, mime_type=mime, size_bytes=size, note=note,
                created_by=current_user().username)
            db.session.add(record)
            db.session.flush()
            db.session.add(OrderPhotoUpload(user_id=user_id, request_id=key, file_id=record.id, digest=digest))
            audit('create', 'customer_file', record.id, 'iPhone 上传订单照片', after={'pi_id': id, 'customer_id': pi.customer_id})
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            if stored:
                remove_file(stored)
            existing = previous()
            if existing:
                return jsonify(photo=photo_payload(existing)), 200
            raise
        except Exception:
            db.session.rollback()
            if stored:
                remove_file(stored)
            raise
        return jsonify(photo=photo_payload(record)), 201

    def accessible_photo(id):
        record = db.session.get(CustomerFile, id)
        if not record or record.deleted_at or not record.pi_id or not record.mime_type.startswith('image/'):
            abort(404, description='照片不存在或已移除。')
        pi = accessible_order(record.pi_id)
        if record.customer_id != pi.customer_id:
            abort(404)
        return record

    @bp.get('/photos/<int:id>/file')
    def photo_file(id):
        record = accessible_photo(id)
        name = secure_filename(record.stored_name)
        if name != record.stored_name:
            abort(404)
        path = os.path.join(current_app.config['UPLOAD_DIR'], name)
        if not os.path.isfile(path):
            abort(404)
        if request.args.get('thumbnail') == '1':
            return send_file(thumbnail(name, path), conditional=True)
        return send_file(path, mimetype=record.mime_type, as_attachment=request.args.get('download') == '1',
                         download_name=record.original_name, conditional=True)

    @bp.post('/photos/<int:id>/delete')
    def delete(id):
        if not is_admin():
            abort(403, description='只有管理员可以删除照片。')
        record = accessible_photo(id)
        record.deleted_at = datetime.utcnow()
        audit('soft_delete', 'customer_file', id, '删除订单照片', before={'pi_id': record.pi_id})
        db.session.commit()
        return jsonify(ok=True)

    from order_chat import register_chat
    register_chat(bp, current_user=current_user, accessible_order=accessible_order,
                  orders_query=orders_query, order_payload=order_payload, audit=audit)
    from web_push import register_web_push
    register_web_push(bp, current_user)
    app.register_blueprint(bp)
