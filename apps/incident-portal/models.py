from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash
from extensions import db


def _clean_upper(value):
    return str(value or '').strip().upper()

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    nip = db.Column(db.String(64), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(255), nullable=False)
    unit = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(64), nullable=True)
    role = db.Column(db.String(32), nullable=False, default='employee')
    password_hash = db.Column(db.String(255), nullable=False)
    must_change_password = db.Column(db.Boolean, default=True, nullable=False)
    is_active_user = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tickets = db.relationship('PortalTicket', back_populates='user', lazy=True)

    @property
    def is_active(self):
        return self.is_active_user

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

class PortalTicket(db.Model):
    __tablename__ = 'portal_tickets'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    ticket_code = db.Column(db.String(64), unique=True, nullable=False, index=True)
    ticket_alias = db.Column(db.String(32), nullable=True)
    category = db.Column(db.String(32), nullable=False)
    location = db.Column(db.String(255), nullable=False)
    problem_summary = db.Column(db.String(500), nullable=False)
    detail_description = db.Column(db.Text, nullable=True)
    contact_phone = db.Column(db.String(64), nullable=True)
    attachment_path = db.Column(db.String(500), nullable=True)
    status_cache = db.Column(db.String(32), default='OPEN', nullable=False)
    last_note_cache = db.Column(db.Text, nullable=True)
    handled_by_cache = db.Column(db.String(255), nullable=True)
    last_update_cache = db.Column(db.String(64), nullable=True)
    raw_create_response = db.Column(db.Text, nullable=True)
    signal_notification_ok = db.Column(db.Boolean, default=False, nullable=False)
    signal_notification_detail = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = db.relationship('User', back_populates='tickets')

