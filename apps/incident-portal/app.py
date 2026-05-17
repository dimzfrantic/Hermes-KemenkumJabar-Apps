from flask import Flask, redirect, request, url_for
from flask_login import current_user

from config import Config
from extensions import csrf, db, login_manager
from models import User

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Silakan login terlebih dahulu.'
    login_manager.login_message_category = 'warning'

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @app.before_request
    def enforce_first_password_change():
        allowed_endpoints = {'auth.change_password', 'auth.logout', 'static'}
        if current_user.is_authenticated and current_user.must_change_password:
            endpoint = request.endpoint or ''
            if endpoint not in allowed_endpoints:
                return redirect(url_for('auth.change_password'))
        return None

    from routes.auth import auth_bp
    from routes.portal import portal_bp
    from routes.admin import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(portal_bp)
    app.register_blueprint(admin_bp)

    with app.app_context():
        db.create_all()
        ensure_admin_user(app)

    return app

def ensure_admin_user(app):
    admin_nip = app.config['ADMIN_NIP']
    admin_name = app.config['ADMIN_NAME']
    admin_password = app.config['ADMIN_PASSWORD']
    admin_user = User.query.filter_by(nip=admin_nip).first()
    if admin_user is None:
        admin_user = User(
            nip=admin_nip,
            full_name=admin_name,
            unit='ADMIN PORTAL',
            role='admin',
            must_change_password=True,
            is_active_user=True,
        )
        admin_user.set_password(admin_password)
        db.session.add(admin_user)
        db.session.commit()

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5050, debug=True)
