from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func
from extensions import db
from models import User

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('portal.dashboard'))

    if request.method == 'POST':
        nip = (request.form.get('nip') or '').strip()
        compact_nip = ''.join(ch for ch in nip if ch.isdigit())
        password = request.form.get('password') or ''
        user = User.query.filter_by(nip=nip).first()
        if user is None and compact_nip:
            user = User.query.filter(
                func.replace(User.nip, ' ', '') == compact_nip
            ).first()
        if user is None or not user.check_password(password) or not user.is_active_user:
            flash('NIP atau password tidak valid.', 'danger')
            return render_template('login.html')
        login_user(user)
        flash('Login berhasil.', 'success')
        if user.must_change_password:
            flash('Silakan ganti password awal Anda terlebih dahulu.', 'warning')
            return redirect(url_for('auth.change_password'))
        return redirect(url_for('portal.dashboard'))

    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Anda sudah logout.', 'info')
    return redirect(url_for('auth.login'))

@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password') or ''
        new_password = request.form.get('new_password') or ''
        confirm_password = request.form.get('confirm_password') or ''

        if not current_user.check_password(current_password):
            flash('Password saat ini tidak sesuai.', 'danger')
            return render_template('change_password.html')
        if len(new_password) < 6:
            flash('Password baru minimal 6 karakter.', 'danger')
            return render_template('change_password.html')
        if new_password != confirm_password:
            flash('Konfirmasi password baru tidak sama.', 'danger')
            return render_template('change_password.html')

        current_user.set_password(new_password)
        current_user.must_change_password = False
        db.session.commit()
        flash('Password berhasil diperbarui.', 'success')
        return redirect(url_for('portal.dashboard'))

    return render_template('change_password.html')
