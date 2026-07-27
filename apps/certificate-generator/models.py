from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db


class AdminUser(UserMixin, db.Model):
    __tablename__ = 'admin_users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(255), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class GenerationJob(db.Model):
    __tablename__ = 'generation_jobs'

    id = db.Column(db.Integer, primary_key=True)
    job_uuid = db.Column(db.String(36), unique=True, nullable=False, index=True)
    original_template_name = db.Column(db.String(255), nullable=False)
    original_excel_name = db.Column(db.String(255), nullable=False)
    drive_folder_id = db.Column(db.String(128), nullable=False)
    selected_sheet = db.Column(db.String(255), nullable=True)
    name_column = db.Column(db.String(255), nullable=False)
    institution_column = db.Column(db.String(255), nullable=False)
    photo_column = db.Column(db.String(255), nullable=True)
    total_rows = db.Column(db.Integer, default=0, nullable=False)
    processed_rows = db.Column(db.Integer, default=0, nullable=False)
    success_rows = db.Column(db.Integer, default=0, nullable=False)
    failed_rows = db.Column(db.Integer, default=0, nullable=False)
    status = db.Column(db.String(32), default='draft', nullable=False)
    preview_ready = db.Column(db.Boolean, default=False, nullable=False)
    cancel_requested = db.Column(db.Boolean, default=False, nullable=False)
    requested_action = db.Column(db.String(16), nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    error_summary = db.Column(db.Text, nullable=True)
    summary_json = db.Column(db.Text, nullable=True)

    preview_files = db.relationship('PreviewArtifact', back_populates='job', cascade='all, delete-orphan', lazy=True)
    job_rows = db.relationship('JobRowResult', back_populates='job', cascade='all, delete-orphan', lazy=True)


class PreviewArtifact(db.Model):
    __tablename__ = 'preview_artifacts'

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('generation_jobs.id'), nullable=False, index=True)
    row_number = db.Column(db.Integer, nullable=False)
    participant_name = db.Column(db.String(255), nullable=False)
    institution_name = db.Column(db.String(255), nullable=False)
    preview_pdf_path = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    job = db.relationship('GenerationJob', back_populates='preview_files')


class JobRowResult(db.Model):
    __tablename__ = 'job_row_results'

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('generation_jobs.id'), nullable=False, index=True)
    row_number = db.Column(db.Integer, nullable=False)
    participant_name = db.Column(db.String(255), nullable=True)
    institution_name = db.Column(db.String(255), nullable=True)
    output_filename = db.Column(db.String(255), nullable=True)
    drive_file_id = db.Column(db.String(128), nullable=True)
    drive_link = db.Column(db.String(500), nullable=True)
    status = db.Column(db.String(32), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    job = db.relationship('GenerationJob', back_populates='job_rows')


class AutoCertificateEvent(db.Model):
    __tablename__ = 'auto_certificate_events'

    id = db.Column(db.Integer, primary_key=True)
    event_uuid = db.Column(db.String(36), unique=True, nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    spreadsheet_id = db.Column(db.String(255), nullable=False)
    spreadsheet_title = db.Column(db.String(255), nullable=True)
    worksheet_name = db.Column(db.String(255), nullable=True)
    drive_folder_id = db.Column(db.String(128), nullable=False)
    drive_folder_name = db.Column(db.String(255), nullable=True)
    template_filename = db.Column(db.String(255), nullable=False)
    name_column = db.Column(db.String(255), nullable=False, default='Nama Lengkap')
    email_column = db.Column(db.String(255), nullable=True)
    institution_column = db.Column(db.String(255), nullable=True)
    phone_column = db.Column(db.String(255), nullable=True)
    photo_column = db.Column(db.String(255), nullable=True)
    timestamp_column = db.Column(db.String(255), nullable=True)
    polling_interval_minutes = db.Column(db.Integer, default=5, nullable=False)
    status = db.Column(db.String(32), default='draft', nullable=False, index=True)
    enabled = db.Column(db.Boolean, default=False, nullable=False)
    total_responses = db.Column(db.Integer, default=0, nullable=False)
    pending_responses = db.Column(db.Integer, default=0, nullable=False)
    processing_responses = db.Column(db.Integer, default=0, nullable=False)
    success_responses = db.Column(db.Integer, default=0, nullable=False)
    failed_responses = db.Column(db.Integer, default=0, nullable=False)
    last_synced_at = db.Column(db.DateTime, nullable=True)
    last_run_started_at = db.Column(db.DateTime, nullable=True)
    last_run_finished_at = db.Column(db.DateTime, nullable=True)
    next_run_at = db.Column(db.DateTime, nullable=True)
    last_error = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    items = db.relationship('AutoCertificateItem', back_populates='event', cascade='all, delete-orphan', lazy=True)
    runs = db.relationship('AutoCertificateRun', back_populates='event', cascade='all, delete-orphan', lazy=True)


class AutoCertificateItem(db.Model):
    __tablename__ = 'auto_certificate_items'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('auto_certificate_events.id'), nullable=False, index=True)
    participant_key = db.Column(db.String(255), nullable=False)
    source_row_number = db.Column(db.Integer, nullable=False)
    submitted_at = db.Column(db.String(255), nullable=True)
    participant_name = db.Column(db.String(255), nullable=True)
    institution_name = db.Column(db.String(255), nullable=True)
    email = db.Column(db.String(255), nullable=True)
    phone = db.Column(db.String(255), nullable=True)
    photo_url = db.Column(db.Text, nullable=True)
    source_data_json = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(32), nullable=False, default='pending', index=True)
    output_filename = db.Column(db.String(255), nullable=True)
    drive_file_id = db.Column(db.String(128), nullable=True)
    drive_link = db.Column(db.String(500), nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    processed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    event = db.relationship('AutoCertificateEvent', back_populates='items')

    __table_args__ = (
        db.UniqueConstraint('event_id', 'participant_key', name='uq_auto_event_participant_key'),
    )


class AutoCertificateRun(db.Model):
    __tablename__ = 'auto_certificate_runs'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('auto_certificate_events.id'), nullable=False, index=True)
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    finished_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(32), default='running', nullable=False)
    found_rows = db.Column(db.Integer, default=0, nullable=False)
    queued_rows = db.Column(db.Integer, default=0, nullable=False)
    processed_rows = db.Column(db.Integer, default=0, nullable=False)
    success_rows = db.Column(db.Integer, default=0, nullable=False)
    failed_rows = db.Column(db.Integer, default=0, nullable=False)
    message = db.Column(db.Text, nullable=True)

    event = db.relationship('AutoCertificateEvent', back_populates='runs')
