"""
ContratosPy — Backend Flask
Deploy: Render.com
"""

import os
import uuid
import smtplib
import bcrypt as _bcrypt
from datetime import datetime, date, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from functools import wraps

from flask import Flask, request, jsonify, send_from_directory, g
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from sqlalchemy import func, or_
import jwt
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

# ─────────────────────────────────────────────
# APP SETUP
# ─────────────────────────────────────────────

# O Flask serve o frontend a partir da pasta ../frontend
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), 'frontend')

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path='')
CORS(app, resources={r"/api/*": {"origins": "*"}})

app.config.update(
    SECRET_KEY=os.environ.get('SECRET_KEY', 'dev-secret-change-in-prod'),
    SQLALCHEMY_DATABASE_URI=os.environ.get('DATABASE_URL', '').replace(
        'postgres://', 'postgresql://', 1          # Render usa postgres://, SQLAlchemy exige postgresql://
    ),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SQLALCHEMY_ENGINE_OPTIONS={
        "pool_pre_ping": True,
        "pool_recycle": 300,
    },
    UPLOAD_FOLDER=os.path.join(os.path.dirname(__file__), 'uploads'),
    MAX_CONTENT_LENGTH=50 * 1024 * 1024,
    MAIL_SERVER=os.environ.get('MAIL_SERVER', 'smtp.gmail.com'),
    MAIL_PORT=int(os.environ.get('MAIL_PORT', 587)),
    MAIL_USERNAME=os.environ.get('MAIL_USERNAME', ''),
    MAIL_PASSWORD=os.environ.get('MAIL_PASSWORD', ''),
    MAIL_FROM=os.environ.get('MAIL_FROM', 'contratos@empresa.com'),
)

db = SQLAlchemy(app)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ─────────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────────

class User(db.Model):
    __tablename__ = 'users'
    id            = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name          = db.Column(db.String(200), nullable=False)
    email         = db.Column(db.String(200), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role          = db.Column(db.String(20), default='viewer')
    department    = db.Column(db.String(100))
    phone         = db.Column(db.String(20))
    is_active     = db.Column(db.Boolean, default=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()

    def check_password(self, password):
        return _bcrypt.checkpw(password.encode(), self.password_hash.encode())

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'email': self.email,
            'role': self.role, 'department': self.department,
            'phone': self.phone, 'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


contract_tags = db.Table('contract_tags',
    db.Column('contract_id', db.String(36), db.ForeignKey('contracts.id', ondelete='CASCADE')),
    db.Column('tag_id',      db.String(36), db.ForeignKey('tags.id',      ondelete='CASCADE')),
)


class Contract(db.Model):
    __tablename__ = 'contracts'
    id                  = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code                = db.Column(db.String(50), unique=True, nullable=False)
    title               = db.Column(db.String(300), nullable=False)
    contract_type       = db.Column(db.String(30), default='service')
    status              = db.Column(db.String(20), default='active')
    counterparty_name   = db.Column(db.String(200), nullable=False)
    counterparty_doc    = db.Column(db.String(30))
    counterparty_email  = db.Column(db.String(200))
    start_date          = db.Column(db.Date, nullable=False)
    end_date            = db.Column(db.Date)
    renewal_type        = db.Column(db.String(20), default='manual')
    renewal_notice_days = db.Column(db.Integer, default=30)
    alert_days_before   = db.Column(db.Integer, default=30)  # dias antes do vencimento para alertar
    auto_renewal_months = db.Column(db.Integer)
    value_total         = db.Column(db.Numeric(15, 2))
    value_monthly       = db.Column(db.Numeric(15, 2))
    currency            = db.Column(db.String(3), default='BRL')
    description         = db.Column(db.Text)
    internal_notes      = db.Column(db.Text)
    responsible_id      = db.Column(db.String(36), db.ForeignKey('users.id'))
    department          = db.Column(db.String(100))
    is_confidential     = db.Column(db.Boolean, default=False)
    created_by          = db.Column(db.String(36), db.ForeignKey('users.id'))
    created_at          = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at          = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    responsible = db.relationship('User', foreign_keys=[responsible_id], backref='managed_contracts')
    creator     = db.relationship('User', foreign_keys=[created_by])
    alerts      = db.relationship('Alert',   backref='contract', lazy='dynamic', cascade='all, delete-orphan')
    documents   = db.relationship('Document', backref='contract', lazy='dynamic', cascade='all, delete-orphan')
    tags        = db.relationship('Tag', secondary=contract_tags, backref='contracts')

    @property
    def days_until_expiry(self):
        return (self.end_date - date.today()).days if self.end_date else None

    def to_dict(self, include_alerts=False):
        days = self.days_until_expiry
        urgency = 'none'
        if days is not None:
            if days < 0:    urgency = 'expired'
            elif days <= 7:  urgency = 'critical'
            elif days <= 30: urgency = 'high'
            elif days <= 60: urgency = 'medium'
            elif days <= 90: urgency = 'low'
        d = {
            'id': self.id, 'code': self.code, 'title': self.title,
            'contract_type': self.contract_type, 'status': self.status,
            'counterparty_name': self.counterparty_name,
            'counterparty_doc': self.counterparty_doc,
            'counterparty_email': self.counterparty_email,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'renewal_type': self.renewal_type,
            'renewal_notice_days': self.renewal_notice_days,
            'alert_days_before': self.alert_days_before,
            'auto_renewal_months': self.auto_renewal_months,
            'value_total': float(self.value_total) if self.value_total else None,
            'value_monthly': float(self.value_monthly) if self.value_monthly else None,
            'currency': self.currency, 'description': self.description,
            'internal_notes': self.internal_notes,
            'responsible': self.responsible.to_dict() if self.responsible else None,
            'responsible_id': self.responsible_id,
            'department': self.department,
            'is_confidential': self.is_confidential,
            'days_until_expiry': days, 'urgency': urgency,
            'tags': [t.to_dict() for t in self.tags],
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'created_by': self.created_by,
        }
        if include_alerts:
            d['alerts'] = [a.to_dict() for a in self.alerts.order_by(Alert.trigger_date).all()]
        return d


class Alert(db.Model):
    __tablename__ = 'alerts'
    id              = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    contract_id     = db.Column(db.String(36), db.ForeignKey('contracts.id', ondelete='CASCADE'), nullable=False)
    alert_type      = db.Column(db.String(20), default='expiration')
    days_before     = db.Column(db.Integer, nullable=False)
    trigger_date    = db.Column(db.Date, nullable=False)
    event_date      = db.Column(db.Date, nullable=False)
    title           = db.Column(db.String(200))
    message         = db.Column(db.Text)
    status          = db.Column(db.String(20), default='pending')
    priority        = db.Column(db.String(10), default='medium')
    sent_at         = db.Column(db.DateTime)
    acknowledged_at = db.Column(db.DateTime)
    acknowledged_by = db.Column(db.String(36), db.ForeignKey('users.id'))
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id, 'contract_id': self.contract_id,
            'alert_type': self.alert_type, 'days_before': self.days_before,
            'trigger_date': self.trigger_date.isoformat() if self.trigger_date else None,
            'event_date': self.event_date.isoformat() if self.event_date else None,
            'title': self.title, 'message': self.message,
            'status': self.status, 'priority': self.priority,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'acknowledged_at': self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            'contract_title': self.contract.title if self.contract else None,
            'counterparty': self.contract.counterparty_name if self.contract else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Renewal(db.Model):
    __tablename__ = 'renewals'
    id                   = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    original_contract_id = db.Column(db.String(36), db.ForeignKey('contracts.id'))
    new_contract_id      = db.Column(db.String(36), db.ForeignKey('contracts.id'))
    renewal_number       = db.Column(db.Integer, default=1)
    decision             = db.Column(db.String(20), default='renew')
    decision_date        = db.Column(db.Date)
    decision_by          = db.Column(db.String(36), db.ForeignKey('users.id'))
    new_start_date       = db.Column(db.Date)
    new_end_date         = db.Column(db.Date)
    new_value            = db.Column(db.Numeric(15, 2))
    notes                = db.Column(db.Text)
    created_at           = db.Column(db.DateTime, default=datetime.utcnow)

    original      = db.relationship('Contract', foreign_keys=[original_contract_id])
    decision_user = db.relationship('User',     foreign_keys=[decision_by])

    def to_dict(self):
        return {
            'id': self.id,
            'original_contract_id': self.original_contract_id,
            'new_contract_id': self.new_contract_id,
            'renewal_number': self.renewal_number,
            'decision': self.decision,
            'decision_date': self.decision_date.isoformat() if self.decision_date else None,
            'new_start_date': self.new_start_date.isoformat() if self.new_start_date else None,
            'new_end_date': self.new_end_date.isoformat() if self.new_end_date else None,
            'new_value': float(self.new_value) if self.new_value else None,
            'notes': self.notes,
            'decision_user': self.decision_user.name if self.decision_user else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Document(db.Model):
    __tablename__ = 'documents'
    id          = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    contract_id = db.Column(db.String(36), db.ForeignKey('contracts.id', ondelete='CASCADE'))
    filename    = db.Column(db.String(300), nullable=False)
    file_path   = db.Column(db.String(500), nullable=False)
    file_size   = db.Column(db.Integer)
    mime_type   = db.Column(db.String(100))
    version     = db.Column(db.Integer, default=1)
    uploaded_by = db.Column(db.String(36), db.ForeignKey('users.id'))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    description = db.Column(db.String(500))
    uploader    = db.relationship('User', foreign_keys=[uploaded_by])

    def to_dict(self):
        return {
            'id': self.id, 'contract_id': self.contract_id,
            'filename': self.filename, 'file_size': self.file_size,
            'mime_type': self.mime_type, 'version': self.version,
            'description': self.description,
            'uploaded_by': self.uploader.name if self.uploader else None,
            'uploaded_at': self.uploaded_at.isoformat() if self.uploaded_at else None,
        }


class Tag(db.Model):
    __tablename__ = 'tags'
    id    = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name  = db.Column(db.String(50), unique=True, nullable=False)
    color = db.Column(db.String(7), default='#6366f1')

    def to_dict(self):
        return {'id': self.id, 'name': self.name, 'color': self.color}


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id          = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id     = db.Column(db.String(36), db.ForeignKey('users.id'))
    action      = db.Column(db.String(100), nullable=False)
    entity_type = db.Column(db.String(50))
    entity_id   = db.Column(db.String(36))
    old_values  = db.Column(db.JSON)
    new_values  = db.Column(db.JSON)
    ip_address  = db.Column(db.String(50))
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    user        = db.relationship('User', foreign_keys=[user_id])

    def to_dict(self):
        return {
            'id': self.id, 'action': self.action,
            'entity_type': self.entity_type, 'entity_id': self.entity_id,
            'user': self.user.name if self.user else 'Sistema',
            'ip_address': self.ip_address,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


# ─────────────────────────────────────────────
# AUTH HELPERS
# ─────────────────────────────────────────────

def generate_token(user_id, role):
    return jwt.encode({
        'sub': user_id, 'role': role,
        'iat': datetime.utcnow(),
        'exp': datetime.utcnow() + timedelta(hours=24),
    }, app.config['SECRET_KEY'], algorithm='HS256')


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'error': 'Token requerido'}), 401
        try:
            payload    = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            g.user_id  = payload['sub']
            g.user_role = payload['role']
            g.user     = User.query.get(g.user_id)
            if not g.user or not g.user.is_active:
                return jsonify({'error': 'Usuário inativo'}), 401
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expirado'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Token inválido'}), 401
        return f(*args, **kwargs)
    return decorated


def require_role(*roles):
    def decorator(f):
        @wraps(f)
        @require_auth
        def decorated(*args, **kwargs):
            if g.user_role not in roles:
                return jsonify({'error': 'Permissão insuficiente'}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator


def log_action(action, entity_type=None, entity_id=None, old=None, new=None):
    try:
        db.session.add(AuditLog(
            user_id=getattr(g, 'user_id', None),
            action=action, entity_type=entity_type, entity_id=entity_id,
            old_values=old, new_values=new, ip_address=request.remote_addr,
        ))
        db.session.commit()
    except Exception:
        pass


def generate_contract_code():
    year  = date.today().year
    count = Contract.query.filter(func.extract('year', Contract.created_at) == year).count()
    return f"CTR-{year}-{str(count + 1).zfill(4)}"


# ─────────────────────────────────────────────
# ALERT ENGINE
# ─────────────────────────────────────────────

DEFAULT_ALERT_DAYS = [90, 60, 30, 15, 7, 1]


def get_priority(days):
    if days <= 7:  return 'critical'
    if days <= 15: return 'high'
    if days <= 30: return 'medium'
    return 'low'


def send_email_alert(to_email, subject, body_html):
    try:
        if not app.config['MAIL_USERNAME']:
            print(f"[EMAIL SIMULADO] Para: {to_email} | {subject}")
            return True
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From']    = app.config['MAIL_FROM']
        msg['To']      = to_email
        msg.attach(MIMEText(body_html, 'html'))
        with smtplib.SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT']) as s:
            s.starttls()
            s.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
            s.send_message(msg)
        return True
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")
        return False


def build_alert_email(contract, days_remaining):
    colors = {'critical': '#ef4444', 'high': '#f97316', 'medium': '#eab308', 'low': '#22c55e'}
    color  = colors.get(get_priority(days_remaining), '#6366f1')
    return f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;background:#0f172a;color:#e2e8f0;padding:32px;border-radius:12px">
      <div style="border-left:4px solid {color};padding-left:16px;margin-bottom:24px">
        <h1 style="margin:0;font-size:20px;color:{color}">⚠ Alerta de Contrato — ContratosPy</h1>
      </div>
      <h2 style="color:#f1f5f9">{contract.title}</h2>
      <table style="width:100%;border-collapse:collapse;margin:16px 0">
        <tr><td style="padding:8px;color:#94a3b8;width:40%">Contraparte</td><td style="padding:8px;color:#f1f5f9">{contract.counterparty_name}</td></tr>
        <tr style="background:#1e293b"><td style="padding:8px;color:#94a3b8">Código</td><td style="padding:8px;color:#f1f5f9">{contract.code}</td></tr>
        <tr><td style="padding:8px;color:#94a3b8">Vencimento</td><td style="padding:8px;color:{color};font-weight:bold">{contract.end_date.strftime('%d/%m/%Y')}</td></tr>
        <tr style="background:#1e293b"><td style="padding:8px;color:#94a3b8">Dias restantes</td><td style="padding:8px;color:{color};font-weight:bold;font-size:20px">{days_remaining} dias</td></tr>
      </table>
      <p style="color:#475569;font-size:12px;margin-top:24px">E-mail automático — ContratosPy</p>
    </div>"""


def run_alert_engine():
    """Roda a cada hora. Ativa alertas cujo trigger_date chegou hoje."""
    with app.app_context():
        today = date.today()
        updated = 0

        # Atualizar status dos contratos
        for contract in Contract.query.filter(Contract.end_date.isnot(None)).all():
            days = (contract.end_date - today).days
            if days < 0 and contract.status not in ('expired', 'cancelled'):
                contract.status = 'expired'
                db.session.commit()
            elif 0 <= days <= 30 and contract.status == 'active':
                contract.status = 'expiring'
                db.session.commit()

        # Ativar alertas pendentes cujo trigger_date chegou
        due_alerts = Alert.query.filter(
            Alert.trigger_date <= today,
            Alert.status == 'pending'
        ).all()

        for alert in due_alerts:
            contract = alert.contract
            days = (contract.end_date - today).days
            # Atualizar título com dias reais restantes
            alert.title   = f"Contrato vence em {max(days,0)} dia(s)"
            alert.message = f"'{contract.title}' vence em {max(days,0)} dias ({contract.end_date.strftime('%d/%m/%Y')})."
            alert.priority = get_priority(days)

            if contract.responsible and contract.responsible.email:
                subject = f"[{alert.priority.upper()}] Contrato vence em {days}d — {contract.code}"
                sent    = send_email_alert(contract.responsible.email, subject, build_alert_email(contract, days))
                if sent:
                    alert.status  = 'sent'
                    alert.sent_at = datetime.utcnow()

            db.session.commit()
            updated += 1

        print(f"[SCHEDULER] {updated} alertas processados — {datetime.now()}")


def _create_default_alerts(contract):
    """Cria 1 único alerta no prazo definido pelo usuário (alert_days_before).
    Se esse prazo já passou, o alerta aparece imediatamente.
    """
    today          = date.today()
    days_remaining = (contract.end_date - today).days
    alert_before   = contract.alert_days_before or 30

    # Remover alertas antigos pendentes deste contrato (limpeza)
    Alert.query.filter(
        Alert.contract_id == contract.id,
        Alert.status == 'pending'
    ).delete()

    # Calcular trigger_date: end_date - alert_before dias
    trigger = contract.end_date - timedelta(days=alert_before)

    # Se a data de alerta já passou, disparar hoje
    if trigger < today:
        trigger = today

    days_at_trigger = (contract.end_date - trigger).days

    db.session.add(Alert(
        contract_id=contract.id, alert_type='expiration',
        days_before=alert_before, trigger_date=trigger,
        event_date=contract.end_date,
        title=f"Contrato vence em {days_at_trigger} dia(s)",
        message=f"O contrato '{contract.title}' vence em {days_at_trigger} dias ({contract.end_date.strftime('%d/%m/%Y')}).",
        status='pending', priority=get_priority(days_at_trigger),
    ))
    db.session.commit()


# ─────────────────────────────────────────────
# API — AUTH
# ─────────────────────────────────────────────

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    user = User.query.filter_by(email=data.get('email', '').lower()).first()
    if not user or not user.check_password(data.get('password', '')):
        return jsonify({'error': 'Credenciais inválidas'}), 401
    if not user.is_active:
        return jsonify({'error': 'Usuário inativo'}), 401
    log_action('LOGIN', 'user', user.id)
    return jsonify({'token': generate_token(user.id, user.role), 'user': user.to_dict()})


@app.route('/api/auth/me', methods=['GET'])
@require_auth
def me():
    return jsonify(g.user.to_dict())


# ─────────────────────────────────────────────
# API — DASHBOARD
# ─────────────────────────────────────────────

@app.route('/api/dashboard', methods=['GET'])
@require_auth
def dashboard():
    today = date.today()
    total    = Contract.query.filter(Contract.status != 'cancelled').count()
    active   = Contract.query.filter_by(status='active').count()
    expiring = Contract.query.filter_by(status='expiring').count()
    expired  = Contract.query.filter_by(status='expired').count()
    critical = Contract.query.filter(
        Contract.status.in_(['active', 'expiring']),
        Contract.end_date.isnot(None),
        Contract.end_date <= today + timedelta(days=30),
        Contract.end_date >= today,
    ).count()
    total_value   = db.session.query(func.sum(Contract.value_total)).filter(Contract.status.in_(['active', 'expiring'])).scalar() or 0
    monthly_value = db.session.query(func.sum(Contract.value_monthly)).filter(Contract.status.in_(['active', 'expiring'])).scalar() or 0
    pending_alerts = Alert.query.filter(
        Alert.status.in_(['pending', 'sent']),
        Alert.acknowledged_at.is_(None),
        Alert.trigger_date <= date.today()
    ).count()

    by_type = db.session.query(Contract.contract_type, func.count(Contract.id))\
        .filter(Contract.status != 'cancelled').group_by(Contract.contract_type).all()

    monthly_expirations = []
    for i in range(12):
        ms = (today.replace(day=1) + timedelta(days=32 * i)).replace(day=1)
        me = (ms + timedelta(days=32)).replace(day=1)
        count = Contract.query.filter(Contract.end_date >= ms, Contract.end_date < me, Contract.status != 'cancelled').count()
        monthly_expirations.append({'month': ms.strftime('%b/%Y'), 'count': count})

    critical_contracts = Contract.query.filter(
        Contract.status.in_(['active', 'expiring']),
        Contract.end_date.isnot(None),
        Contract.end_date >= today,
        Contract.end_date <= today + timedelta(days=90),
    ).order_by(Contract.end_date).limit(10).all()

    return jsonify({
        'stats': {
            'total': total, 'active': active, 'expiring': expiring,
            'expired': expired, 'critical': critical,
            'total_value': float(total_value),
            'monthly_value': float(monthly_value),
            'pending_alerts': pending_alerts,
        },
        'by_type': [{'type': t, 'count': c} for t, c in by_type],
        'monthly_expirations': monthly_expirations,
        'critical_contracts': [c.to_dict() for c in critical_contracts],
    })


# ─────────────────────────────────────────────
# API — CONTRACTS
# ─────────────────────────────────────────────

@app.route('/api/contracts', methods=['GET'])
@require_auth
def list_contracts():
    q = Contract.query
    status  = request.args.get('status')
    ctype   = request.args.get('type')
    search  = request.args.get('search')
    resp    = request.args.get('responsible_id')
    if status: q = q.filter(Contract.status == status)
    if ctype:  q = q.filter(Contract.contract_type == ctype)
    if resp:   q = q.filter(Contract.responsible_id == resp)
    if search:
        q = q.filter(or_(
            Contract.title.ilike(f'%{search}%'),
            Contract.counterparty_name.ilike(f'%{search}%'),
            Contract.code.ilike(f'%{search}%'),
        ))
    if g.user_role not in ('admin', 'legal'):
        q = q.filter(or_(Contract.is_confidential == False, Contract.responsible_id == g.user_id))

    sort = request.args.get('sort', 'end_date')
    if sort == 'end_date':     q = q.order_by(Contract.end_date.asc().nullslast())
    elif sort == 'created_at': q = q.order_by(Contract.created_at.desc())
    elif sort == 'value':      q = q.order_by(Contract.value_total.desc().nullslast())
    else:                      q = q.order_by(Contract.title)

    page     = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    pag      = q.paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({'contracts': [c.to_dict() for c in pag.items], 'total': pag.total, 'pages': pag.pages, 'page': page})


@app.route('/api/contracts', methods=['POST'])
@require_auth
def create_contract():
    data = request.json
    try:
        contract = Contract(
            code=generate_contract_code(),
            title=data['title'], contract_type=data.get('contract_type', 'service'),
            status='active',
            counterparty_name=data['counterparty_name'],
            counterparty_doc=data.get('counterparty_doc'),
            counterparty_email=data.get('counterparty_email'),
            start_date=date.fromisoformat(data['start_date']),
            end_date=date.fromisoformat(data['end_date']) if data.get('end_date') else None,
            renewal_type=data.get('renewal_type', 'manual'),
            renewal_notice_days=int(data.get('renewal_notice_days', 30)),
            alert_days_before=int(data.get('alert_days_before', 30)),
            auto_renewal_months=data.get('auto_renewal_months'),
            value_total=data.get('value_total'), value_monthly=data.get('value_monthly'),
            currency=data.get('currency', 'BRL'), description=data.get('description'),
            internal_notes=data.get('internal_notes'),
            responsible_id=data.get('responsible_id') or g.user_id,
            department=data.get('department'),
            is_confidential=data.get('is_confidential', False),
            created_by=g.user_id,
        )
        for tag_name in (data.get('tags') or []):
            tag = Tag.query.filter_by(name=tag_name).first() or Tag(name=tag_name)
            db.session.add(tag)
            db.session.flush()
            contract.tags.append(tag)
        db.session.add(contract)
        db.session.commit()
        if contract.end_date:
            _create_default_alerts(contract)
        log_action('CREATE_CONTRACT', 'contract', contract.id, new=data)
        return jsonify(contract.to_dict(include_alerts=True)), 201
    except KeyError as e:
        return jsonify({'error': f'Campo obrigatório: {e}'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/contracts/<cid>', methods=['GET'])
@require_auth
def get_contract(cid):
    return jsonify(Contract.query.get_or_404(cid).to_dict(include_alerts=True))


@app.route('/api/contracts/<cid>', methods=['PUT'])
@require_auth
def update_contract(cid):
    contract = Contract.query.get_or_404(cid)
    old  = contract.to_dict()
    data = request.json
    for f in ['title','contract_type','status','counterparty_name','counterparty_doc',
              'counterparty_email','renewal_type','renewal_notice_days','auto_renewal_months','alert_days_before',
              'value_total','value_monthly','currency','description','internal_notes',
              'responsible_id','department','is_confidential']:
        if f in data:
            setattr(contract, f, data[f])
    if 'start_date' in data and data['start_date']:
        contract.start_date = date.fromisoformat(data['start_date'])
    if 'end_date' in data:
        contract.end_date = date.fromisoformat(data['end_date']) if data['end_date'] else None
    contract.updated_at = datetime.utcnow()
    db.session.commit()
    log_action('UPDATE_CONTRACT', 'contract', contract.id, old=old, new=data)
    return jsonify(contract.to_dict(include_alerts=True))


@app.route('/api/contracts/<cid>', methods=['DELETE'])
@require_role('admin')
def delete_contract(cid):
    contract = Contract.query.get_or_404(cid)
    db.session.delete(contract)
    db.session.commit()
    log_action('DELETE_CONTRACT', 'contract', cid)
    return jsonify({'message': 'Contrato excluído'})


# ─────────────────────────────────────────────
# API — ALERTS
# ─────────────────────────────────────────────

@app.route('/api/alerts', methods=['GET'])
@require_auth
def list_alerts():
    q = Alert.query.join(Contract)
    # Só exibir alertas cuja data de disparo já chegou
    q = q.filter(Alert.trigger_date <= date.today())
    if request.args.get('status'):   q = q.filter(Alert.status == request.args['status'])
    if request.args.get('priority'): q = q.filter(Alert.priority == request.args['priority'])
    if g.user_role not in ('admin', 'legal'):
        q = q.filter(Contract.responsible_id == g.user_id)
    return jsonify([a.to_dict() for a in q.order_by(Alert.trigger_date.desc()).limit(100).all()])


@app.route('/api/alerts/<aid>/acknowledge', methods=['POST'])
@require_auth
def acknowledge_alert(aid):
    alert = Alert.query.get_or_404(aid)
    alert.status          = 'acknowledged'
    alert.acknowledged_at = datetime.utcnow()
    alert.acknowledged_by = g.user_id
    db.session.commit()
    return jsonify(alert.to_dict())


@app.route('/api/alerts/run-engine', methods=['POST'])
@require_role('admin')
def trigger_engine():
    run_alert_engine()
    return jsonify({'message': 'Engine executado'})


# ─────────────────────────────────────────────
# API — RENEWALS
# ─────────────────────────────────────────────

@app.route('/api/contracts/<cid>/renewals', methods=['GET'])
@require_auth
def list_renewals(cid):
    return jsonify([r.to_dict() for r in Renewal.query.filter_by(original_contract_id=cid).all()])


@app.route('/api/contracts/<cid>/renewals', methods=['POST'])
@require_auth
def create_renewal(cid):
    contract = Contract.query.get_or_404(cid)
    data     = request.json
    count    = Renewal.query.filter_by(original_contract_id=cid).count()
    renewal  = Renewal(
        original_contract_id=cid, renewal_number=count + 1,
        decision=data.get('decision', 'renew'), decision_date=date.today(),
        decision_by=g.user_id,
        new_start_date=date.fromisoformat(data['new_start_date']) if data.get('new_start_date') else None,
        new_end_date=date.fromisoformat(data['new_end_date'])     if data.get('new_end_date')   else None,
        new_value=data.get('new_value'), notes=data.get('notes'),
    )
    if data.get('decision') == 'renew' and data.get('new_end_date'):
        contract.end_date   = date.fromisoformat(data['new_end_date'])
        contract.status     = 'active'
        contract.updated_at = datetime.utcnow()
        Alert.query.filter_by(contract_id=cid, status='pending').delete()
        db.session.flush()
        _create_default_alerts(contract)
    elif data.get('decision') == 'terminate':
        contract.status = 'cancelled'
    db.session.add(renewal)
    db.session.commit()
    log_action('CREATE_RENEWAL', 'contract', cid, new=data)
    return jsonify(renewal.to_dict()), 201


# ─────────────────────────────────────────────
# API — USERS
# ─────────────────────────────────────────────

@app.route('/api/users', methods=['GET'])
@require_auth
def list_users():
    return jsonify([u.to_dict() for u in User.query.filter_by(is_active=True).all()])


@app.route('/api/users', methods=['POST'])
@require_role('admin')
def create_user():
    data = request.json
    if User.query.filter_by(email=data['email'].lower()).first():
        return jsonify({'error': 'E-mail já cadastrado'}), 409
    user = User(name=data['name'], email=data['email'].lower(),
                role=data.get('role', 'viewer'), department=data.get('department'), phone=data.get('phone'))
    user.set_password(data['password'])
    db.session.add(user)
    db.session.commit()
    return jsonify(user.to_dict()), 201


@app.route('/api/users/<uid>', methods=['PUT'])
@require_role('admin')
def update_user(uid):
    user = User.query.get_or_404(uid)
    data = request.json
    for f in ['name', 'role', 'department', 'phone', 'is_active']:
        if f in data:
            setattr(user, f, data[f])
    if data.get('password'):
        user.set_password(data['password'])
    db.session.commit()
    return jsonify(user.to_dict())


# ─────────────────────────────────────────────
# API — TAGS / AUDIT
# ─────────────────────────────────────────────

@app.route('/api/tags', methods=['GET'])
@require_auth
def list_tags():
    return jsonify([t.to_dict() for t in Tag.query.all()])


@app.route('/api/audit', methods=['GET'])
@require_role('admin', 'legal')
def audit_logs():
    return jsonify([l.to_dict() for l in AuditLog.query.order_by(AuditLog.created_at.desc()).limit(200).all()])


# ─────────────────────────────────────────────
# FRONTEND — serve tudo a partir de /frontend
# ─────────────────────────────────────────────

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    full = os.path.join(app.static_folder, path)
    if path and os.path.exists(full):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')


# ─────────────────────────────────────────────
# SEED
# ─────────────────────────────────────────────

def seed_database():
    if User.query.count() > 0:
        return
    print("[SEED] Criando dados demo...")

    admin  = User(name='Admin Sistema',    email='admin@empresa.com',  role='admin',   department='TI')
    legal  = User(name='Dra. Marina Costa', email='marina@empresa.com', role='legal',   department='Jurídico')
    manager = User(name='Carlos Mendes',   email='carlos@empresa.com', role='manager', department='Operações')
    for u, pw in [(admin, 'admin123'), (legal, 'legal123'), (manager, 'manager123')]:
        u.set_password(pw)
    db.session.add_all([admin, legal, manager])
    db.session.flush()

    tags_data = [('Crítico','#ef4444'),('Renovar','#f97316'),('NDA','#8b5cf6'),('TI','#3b82f6'),('Facilities','#10b981'),('Fornecedor','#6366f1')]
    tags = {}
    for name, color in tags_data:
        t = Tag(name=name, color=color)
        db.session.add(t)
        db.session.flush()
        tags[name] = t

    today = date.today()
    contracts_data = [
        {'title': 'Licença Microsoft 365 Enterprise',    'type': 'service', 'party': 'Microsoft Brasil Ltda.',    'doc': '60.316.817/0001-44', 'email': 'licencas@microsoft.com',       'start': today-timedelta(330), 'end': today+timedelta(35),  'renewal': 'manual',    'vt': 180000, 'vm': 15000,  'dept': 'TI',            'resp': legal,   'tags': ['TI','Crítico']},
        {'title': 'Locação — Sede Administrativa',       'type': 'lease',   'party': 'Imóveis Paulista S.A.',     'doc': '12.345.678/0001-90', 'email': 'contratos@imoveis.com.br',    'start': today-timedelta(180), 'end': today+timedelta(185), 'renewal': 'automatic', 'vt': 720000, 'vm': 60000,  'dept': 'Facilities',    'resp': manager, 'tags': ['Facilities']},
        {'title': 'NDA — Projeto Alpha',                 'type': 'nda',     'party': 'Startup XYZ Tecnologia',   'doc': '98.765.432/0001-10', 'email': 'legal@startupxyz.com',        'start': today-timedelta(60),  'end': today+timedelta(305), 'renewal': 'none',      'vt': None,   'vm': None,   'dept': 'Jurídico',      'resp': legal,   'tags': ['NDA']},
        {'title': 'Fornecimento de Material de Escritório','type':'supply',  'party': 'Distribuidora OfficeMax',  'doc': '55.123.456/0001-77', 'email': 'vendas@officemax.com.br',     'start': today-timedelta(200), 'end': today+timedelta(8),   'renewal': 'manual',    'vt': 36000,  'vm': 3000,   'dept': 'Administrativo','resp': manager, 'tags': ['Fornecedor','Crítico']},
        {'title': 'SLA — Suporte e Manutenção ERP',      'type': 'sla',     'party': 'TechSupport Solutions',    'doc': '33.987.654/0001-22', 'email': 'sla@techsupport.com',         'start': today-timedelta(90),  'end': today+timedelta(275), 'renewal': 'automatic', 'vt': 120000, 'vm': 10000,  'dept': 'TI',            'resp': legal,   'tags': ['TI']},
        {'title': 'Contrato de Publicidade Digital',     'type': 'service', 'party': 'Agência Criativa Digital', 'doc': '77.321.654/0001-55', 'email': 'comercial@agencia.com',       'start': today-timedelta(400), 'end': today-timedelta(35),  'renewal': 'manual',    'vt': 240000, 'vm': 20000,  'dept': 'Marketing',     'resp': manager, 'tags': ['Renovar']},
    ]

    for cd in contracts_data:
        c = Contract(
            code=generate_contract_code(), title=cd['title'], contract_type=cd['type'],
            counterparty_name=cd['party'], counterparty_doc=cd['doc'], counterparty_email=cd['email'],
            start_date=cd['start'], end_date=cd['end'], renewal_type=cd['renewal'],
            value_total=cd['vt'], value_monthly=cd['vm'], currency='BRL',
            department=cd['dept'], responsible=cd['resp'], created_by=admin.id,
        )
        days_left = (cd['end'] - today).days
        c.status = 'expired' if days_left < 0 else ('expiring' if days_left <= 30 else 'active')
        for tag_name in cd['tags']:
            if tag_name in tags:
                c.tags.append(tags[tag_name])
        db.session.add(c)
        db.session.flush()
        if c.end_date:
            _create_default_alerts(c)

    db.session.commit()
    print("[SEED] Dados demo criados. Login: admin@empresa.com / admin123")


# ─────────────────────────────────────────────
# SCHEDULER
# ─────────────────────────────────────────────

scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(run_alert_engine, IntervalTrigger(hours=1), id='alert_engine', replace_existing=True)

# Inicialização ao subir (funciona tanto com gunicorn quanto direto)
with app.app_context():
    db.create_all()
    try:
        with db.engine.connect() as conn:
            conn.execute(db.text(
                "ALTER TABLE contracts ADD COLUMN IF NOT EXISTS alert_days_before INTEGER DEFAULT 30"
            ))
            conn.commit()
            print("[INIT] Migration alert_days_before: ok")
    except Exception as e:
        print(f"[INIT] Migration aviso: {e}")
    seed_database()

scheduler.start()


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

def run_migrations():
    """Adiciona colunas novas sem derrubar dados existentes."""
    try:
        with db.engine.connect() as conn:
            # alert_days_before — adicionado na v2.1
            conn.execute(db.text(
                "ALTER TABLE contracts ADD COLUMN IF NOT EXISTS alert_days_before INTEGER DEFAULT 30"
            ))
            conn.commit()
            print("[MIGRATION] Colunas verificadas/atualizadas.")
    except Exception as e:
        print(f"[MIGRATION] Aviso: {e}")


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        run_migrations()
        seed_database()
        run_alert_engine()
    scheduler.start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
