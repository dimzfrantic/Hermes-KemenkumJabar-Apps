import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import Flask, redirect, render_template, request, url_for
from flask_login import current_user
from werkzeug.exceptions import HTTPException

from config import Config
from extensions import db, login_manager
from models import AdminUser


SCHEMA_COLUMNS = {
    'generation_jobs': {
        'photo_column': 'VARCHAR(255)',
        'mapping_json': 'TEXT',
    },
    'auto_certificate_events': {
        'photo_column': 'VARCHAR(255)',
        'mapping_json': 'TEXT',
    },
    'auto_certificate_items': {
        'photo_url': 'TEXT',
        'source_data_json': 'TEXT',
    },
}


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    configure_logging(app)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Silakan login terlebih dahulu.'
    login_manager.login_message_category = 'warning'

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(AdminUser, int(user_id))

    @app.context_processor
    def inject_app_name():
        google_token_status = None
        if current_user.is_authenticated:
            try:
                from services.google_oauth_manager import get_oauth_status
                google_token_status = get_oauth_status(
                    app.config['GOOGLE_TOKEN_PATH'],
                    app.config['GOOGLE_OAUTH_CLIENT_SECRET_PATH'],
                    app.config.get('GOOGLE_OAUTH_TESTING_WINDOW_DAYS', 7),
                )
            except Exception:
                app.logger.exception('Gagal membaca status token Google')
        return {
            'app_name': app.config['APP_NAME'],
            'google_token_status': google_token_status,
        }

    @app.before_request
    def redirect_root_for_authenticated_user():
        if request.endpoint == 'root' and current_user.is_authenticated:
            return redirect(url_for('certificates.dashboard'))
        return None

    from routes.auth import auth_bp
    from routes.certificates import certificates_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(certificates_bp)

    @app.route('/')
    def root():
        if current_user.is_authenticated:
            return redirect(url_for('certificates.dashboard'))
        return redirect(url_for('auth.login'))

    @app.errorhandler(Exception)
    def handle_unexpected_error(exc):
        if isinstance(exc, HTTPException):
            return exc
        app.logger.exception('Unhandled application error')
        return render_template('error_500.html'), 500

    with app.app_context():
        db.create_all()
        ensure_schema_columns()
        ensure_admin_user(app)

    return app


def configure_logging(app):
    log_dir = Path(app.instance_path)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / 'app.log'

    has_file_handler = any(
        isinstance(handler, RotatingFileHandler) and getattr(handler, 'baseFilename', '') == str(log_path)
        for handler in app.logger.handlers
    )
    if not has_file_handler:
        file_handler = RotatingFileHandler(log_path, maxBytes=1_048_576, backupCount=5)
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s [%(name)s] %(message)s'
        ))
        app.logger.addHandler(file_handler)

    app.logger.setLevel(logging.INFO)


def ensure_schema_columns():
    with db.engine.connect() as connection:
        for table_name, columns in SCHEMA_COLUMNS.items():
            existing = {row[1] for row in connection.exec_driver_sql(f'PRAGMA table_info({table_name})')}
            for column_name, column_type in columns.items():
                if column_name not in existing:
                    connection.exec_driver_sql(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}')
        connection.commit()


def ensure_admin_user(app):
    username = app.config['ADMIN_USERNAME']
    admin_user = AdminUser.query.filter_by(username=username).first()
    if admin_user is None:
        admin_user = AdminUser(
            username=username,
            display_name=app.config['ADMIN_DISPLAY_NAME'],
        )
        admin_user.set_password(app.config['ADMIN_PASSWORD'])
        db.session.add(admin_user)
        db.session.commit()


if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5062, debug=True)
