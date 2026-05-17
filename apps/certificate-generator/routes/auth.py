from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from models import AdminUser


auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('certificates.dashboard'))
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        user = AdminUser.query.filter_by(username=username).first()
        if user is None or not user.check_password(password):
            flash('Username atau password tidak valid.', 'danger')
            return render_template('login.html')
        login_user(user)
        flash('Login berhasil.', 'success')
        return redirect(url_for('certificates.dashboard'))
    return render_template('login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Anda sudah logout.', 'info')
    return redirect(url_for('auth.login'))
