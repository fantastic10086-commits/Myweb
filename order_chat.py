"""Order-scoped internal chat and a durable APNs outbox. No network calls on writes."""
import uuid
import re
from flask import request, jsonify, abort, session
from sqlalchemy import func, or_
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.exc import IntegrityError
from models import db, PI, User, OrderMessage, OrderReadState, PushDevice, PushDelivery


def user_can_chat(user, pi):
    return bool(user and user.active and not user.must_change_password and pi and not pi.deleted_at
        and pi.customer and not pi.customer.deleted_at and (user.role == 'admin' or
        (user.salesperson_name and user.salesperson_name == pi.salesperson == pi.customer.salesperson)))


def unread_query(user_id):
    return OrderMessage.query.outerjoin(OrderReadState, db.and_(
        OrderReadState.pi_id == OrderMessage.pi_id, OrderReadState.user_id == user_id
    )).filter(or_(OrderMessage.author_id != user_id,OrderMessage.author_id.is_(None)),
              OrderMessage.id > func.coalesce(OrderReadState.last_read_id, 0))


def register_chat(bp, *, current_user, accessible_order, orders_query, order_payload, audit):
    def payload(m):
        return {'id':m.id, 'author_id':m.author_id, 'author_name':m.author_name,
                'body':m.body, 'created_at':m.created_at.isoformat()+'Z'}

    @bp.get('/orders/<int:id>/messages')
    def messages(id):
        accessible_order(id)
        after = request.args.get('after', 0, type=int)
        before = request.args.get('before', 0, type=int)
        if after < 0 or before < 0 or (after and before): abort(400)
        q = OrderMessage.query.filter_by(pi_id=id)
        if after:
            rows = q.filter(OrderMessage.id > after).order_by(OrderMessage.id).limit(51).all()
            more = len(rows)>50; rows=rows[:50]
        else:
            if before: q=q.filter(OrderMessage.id < before)
            rows=q.order_by(OrderMessage.id.desc()).limit(51).all()
            more=len(rows)>50; rows=list(reversed(rows[:50]))
        return jsonify(messages=[payload(m) for m in rows], has_more=more)

    @bp.post('/orders/<int:id>/messages')
    def send(id):
        pi=accessible_order(id); user=current_user(); data=request.get_json(silent=True) or {}
        if not isinstance(data,dict): abort(400)
        body=data.get('body', '')
        if not isinstance(body,str) or not body.strip() or len(body)>4000:
            abort(400, description='消息需包含 1–4000 个字符。')
        body=body.strip()
        try: key=str(uuid.UUID(str(data.get('request_id',''))))
        except ValueError: abort(400, description='消息标识无效。')
        def previous():
            m=OrderMessage.query.filter_by(author_id=user.id, request_id=key).first()
            if m and (m.pi_id != id or m.body != body):
                abort(409, description='消息标识已使用，请重新编辑后发送。')
            return m
        old=previous()
        if old: return jsonify(message=payload(old)),200
        m=OrderMessage(pi_id=id, author_id=user.id, author_name=user.username, body=body, request_id=key)
        try:
            db.session.add(m); db.session.flush()
            devices=PushDevice.query.join(User,User.id==PushDevice.user_id).filter(
                PushDevice.active.is_(True), User.active.is_(True), User.id != user.id,
                or_(User.role=='admin',User.salesperson_name==pi.salesperson)).all()
            for device in devices:
                recipient=db.session.get(User,device.user_id)
                if user_can_chat(recipient, pi) and recipient.auth_version==device.auth_version:
                    db.session.add(PushDelivery(message_id=m.id, device_id=device.id,
                        user_id=recipient.id, auth_version=recipient.auth_version))
            from web_push import queue_web_push
            queue_web_push(m, pi, user)
            audit('create','order_message',m.id,'发送订单消息',after={'pi_id':id})
            db.session.commit()
        except IntegrityError:
            db.session.rollback(); old=previous()
            if old: return jsonify(message=payload(old)),200
            raise
        return jsonify(message=payload(m)),201

    @bp.post('/orders/<int:id>/read')
    def mark_read(id):
        accessible_order(id); data=request.get_json(silent=True) or {}
        if not isinstance(data,dict): abort(400)
        last=data.get('last_read_id')
        if type(last) is not int or last<1: abort(400)
        if not OrderMessage.query.filter_by(id=last,pi_id=id).first(): abort(400)
        stmt=insert(OrderReadState).values(user_id=current_user().id,pi_id=id,last_read_id=last)
        stmt=stmt.on_conflict_do_update(index_elements=['user_id','pi_id'],
            set_={'last_read_id':func.max(OrderReadState.last_read_id,last)})
        db.session.execute(stmt); db.session.commit()
        return jsonify(ok=True)

    @bp.get('/unread')
    def unread():
        accessible=orders_query().with_entities(PI.id).subquery()
        rows=unread_query(current_user().id).filter(OrderMessage.pi_id.in_(db.select(accessible.c.id))).with_entities(
            OrderMessage.pi_id,func.count(OrderMessage.id),func.max(OrderMessage.id)
        ).group_by(OrderMessage.pi_id).all()
        # Only metadata in alerts; message bodies are retrieved after order authorization.
        pis={p.id:p for p in PI.query.filter(PI.id.in_([r[0] for r in rows])).all()}
        return jsonify(orders=[{'order':order_payload(pis[id]),'count':count,'latest_id':latest}
                               for id,count,latest in rows],total=sum(row[1] for row in rows))

    @bp.post('/devices')
    def register_device():
        data=request.get_json(silent=True) or {}
        if not isinstance(data,dict): abort(400)
        token=data.get('token',''); env=data.get('environment','')
        if not isinstance(token,str) or not re.fullmatch(r'[a-fA-F0-9]{32,512}',token) or not isinstance(env,str) or env not in {'sandbox','production'}:
            abort(400,description='推送设备信息无效。')
        user=current_user();token=token.lower()
        stmt=insert(PushDevice).values(token=token,environment=env,user_id=user.id,auth_version=user.auth_version,active=True)
        stmt=stmt.on_conflict_do_update(index_elements=['token','environment'],
            set_={'user_id':user.id,'auth_version':user.auth_version,'active':True})
        db.session.execute(stmt); db.session.commit()
        session['mobile_push_token']=token; session['mobile_push_environment']=env
        return jsonify(ok=True)


def disable_session_device():
    token=session.get('mobile_push_token');env=session.get('mobile_push_environment');user_id=session.get('user_id')
    if token and user_id:
        PushDevice.query.filter_by(token=token,environment=env,user_id=user_id).update({'active':False})
        db.session.commit()
