from collections import Counter
from datetime import datetime, timedelta, timezone
import math
import re
import tempfile
from functools import wraps

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_, func

from extensions import db
from models import PortalTicket, User
from services.employee_import import import_employees_from_excel
from services.incident_cache import parse_portal_datetime
from services.incident_gateway import portal_category_label
from services.incident_admin_store import get_dashboard_records, sync_state_summary

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def admin_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if current_user.role != 'admin':
            flash('Halaman ini hanya untuk admin.', 'danger')
            return redirect(url_for('portal.dashboard'))
        return view_func(*args, **kwargs)
    return wrapped


def _employees_redirect():
    q = (request.form.get('return_q') or request.args.get('q') or '').strip()
    page = request.form.get('return_page') or request.args.get('page') or 1
    try:
        page = max(int(page), 1)
    except (TypeError, ValueError):
        page = 1
    return redirect(url_for('admin.employees', q=q, page=page))


def _parse_dt(value):
    return parse_portal_datetime(value)


def _format_minutes(minutes):
    if minutes is None:
        return '-'
    hours, mins = divmod(int(minutes), 60)
    if hours > 0:
        return f'{hours}h {mins}m'
    return f'{mins}m'


def _format_datetime_display(value):
    if not value:
        return '-'
    target_tz = timezone(timedelta(hours=7))
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(target_tz).strftime('%d-%m-%Y %H:%M:%S')
    parsed = _parse_dt(value)
    if parsed:
        return parsed.strftime('%d-%m-%Y %H:%M:%S')
    return str(value)


def _build_latest_status_entry_times(history_rows):
    latest = {}
    for row in history_rows or []:
        ticket_code = str(row.get('ticket_code', '')).strip().upper()
        status_after = str(row.get('status_after', '')).strip().upper()
        update_dt = _parse_dt(row.get('update_time'))
        if not ticket_code or status_after not in {'OPEN', 'IN_PROGRESS', 'PENDING'} or not update_dt:
            continue
        key = (ticket_code, status_after)
        prev_dt = latest.get(key)
        if prev_dt is None or update_dt > prev_dt:
            latest[key] = update_dt
    return latest


def _status_stagnation_minutes(row, now, latest_status_entry_times):
    ticket_code = str(row.get('ticket_code', '')).strip().upper()
    status = str(row.get('status', '')).strip().upper()
    start_dt = latest_status_entry_times.get((ticket_code, status))
    if not start_dt:
        start_dt = _parse_dt(row.get('update_terakhir')) or _parse_dt(row.get('created_at'))
    if not start_dt:
        return None
    return max(0, int((now - start_dt).total_seconds() / 60))


def _category_label_from_ticket_code(ticket_code):
    prefix = str(ticket_code or '').strip().upper().split('-', 1)[0]
    prefix_map = {
        'NET': 'NETWORK',
        'APP': 'APPLICATION',
        'HW': 'HARDWARE',
        'OTH': 'OTHER',
        'INC': 'OTHER',
    }
    return portal_category_label(prefix_map.get(prefix, 'OTHER'))


def _dashboard_payload():
    active, archive, history_rows = get_dashboard_records()
    sync_state = type('SyncState', (), sync_state_summary(len(active), len(archive), len(history_rows)))()
    latest_status_entry_times = _build_latest_status_entry_times(history_rows)
    now = datetime.now()

    all_rows = active + archive

    for row in all_rows:
        row['category_label'] = _category_label_from_ticket_code(row.get('ticket_code'))

    for row in active:
        stagnation_minutes = _status_stagnation_minutes(row, now, latest_status_entry_times)
        row['_stagnation_minutes'] = stagnation_minutes
        row['_stagnation_label'] = _format_minutes(stagnation_minutes)

    status_counts = Counter(str(row.get('status', '') or '').upper() for row in all_rows)
    active_counts = Counter(str(row.get('status', '') or '').upper() for row in active)

    active_sorted = sorted(
        active,
        key=lambda row: _parse_dt(row.get('update_terakhir')) or _parse_dt(row.get('created_at')) or datetime.min,
    )
    latest_active = list(reversed(active_sorted[-5:]))

    pending_rows = [row for row in active if str(row.get('status', '')).upper() == 'PENDING']
    pending_rows = sorted(
        pending_rows,
        key=lambda row: (
            -(row.get('_stagnation_minutes') or -1),
            (_parse_dt(row.get('update_terakhir')) or _parse_dt(row.get('created_at')) or datetime.min),
        ),
        reverse=False,
    )
    urgent_rows = []
    for row in active:
        stagnation_minutes = row.get('_stagnation_minutes')
        status = str(row.get('status', '') or '').upper()
        if stagnation_minutes is None:
            continue
        if status == 'OPEN':
            level = 'RED' if stagnation_minutes > 120 else 'YELLOW' if stagnation_minutes > 60 else None
        elif status == 'IN_PROGRESS':
            level = 'RED' if stagnation_minutes > 240 else 'YELLOW' if stagnation_minutes > 120 else None
        elif status == 'PENDING':
            level = 'RED' if stagnation_minutes > 1440 else 'YELLOW' if stagnation_minutes > 240 else None
        else:
            level = None
        if level:
            urgent_rows.append({
                'row': row,
                'sla_level': level,
                'stagnation_minutes': stagnation_minutes,
            })
    urgent_total = len(urgent_rows)
    urgent_rows = sorted(
        urgent_rows,
        key=lambda item: (0 if item['sla_level'] == 'RED' else 1, -item['stagnation_minutes'], item['row'].get('alias') or ''),
    )

    finished = [row for row in archive if str(row.get('status', '')).upper() in {'RESOLVED', 'CLOSED'}]
    finished_rows = sorted(
        finished,
        key=lambda row: _parse_dt(row.get('update_terakhir')) or _parse_dt(row.get('closed_at')) or _parse_dt(row.get('resolved_at')) or _parse_dt(row.get('created_at')) or datetime.min,
        reverse=True,
    )[:6]

    return {
        'status_counts': status_counts,
        'active_counts': active_counts,
        'active_total': len(active),
        'archive_total': len(archive),
        'latest_active': latest_active,
        'pending_rows': pending_rows[:6],
        'urgent_rows': urgent_rows,
        'urgent_total': urgent_total,
        'finished_rows': finished_rows,
        'sync_state': sync_state,
    }


def _serialize_dashboard_row(row):
    status = str(row.get('status') or '').upper()
    ticket_code = row.get('ticket_code') or '-'
    return {
        'alias': row.get('alias') or '-',
        'ticket_code': ticket_code,
        'category_label': _category_label_from_ticket_code(ticket_code),
        'status': row.get('status') or '-',
        'status_class': {
            'OPEN': 'status-open',
            'IN_PROGRESS': 'status-progress',
            'PENDING': 'status-pending',
            'RESOLVED': 'status-resolved',
            'CLOSED': 'status-closed',
        }.get(status, 'status-open'),
        'masalah': row.get('masalah') or '-',
        'catatan': row.get('catatan_terakhir') or row.get('alasan_pending') or 'Belum ada catatan tambahan.',
        'alasan_pending': row.get('alasan_pending') or 'Belum ada alasan pending.',
        'lokasi': row.get('lokasi') or '-',
        'pelapor': row.get('pelapor') or '-',
        'petugas': '' if status == 'OPEN' else (row.get('ditangani_oleh') or '-'),
        'durasi_aktif': row.get('_stagnation_label') or '-',
        'durasi': row.get('durasi') or '-',
        'update': row.get('update_terakhir') or row.get('closed_at') or row.get('resolved_at') or row.get('created_at') or '-',
    }


def _dashboard_json_payload(payload):
    sync_state = payload.get('sync_state')
    last_synced_at = getattr(sync_state, 'last_synced_at', None) if sync_state else None
    last_error = getattr(sync_state, 'last_error', None) if sync_state else None
    active_total = payload.get('active_total', 0)
    archive_total = payload.get('archive_total', 0)
    status_counts = payload.get('status_counts', Counter())
    active_counts = payload.get('active_counts', Counter())
    return {
        'summary': {
            'urgent_total': payload.get('urgent_total', 0),
            'active_total': active_total,
            'finished_total': status_counts.get('RESOLVED', 0) + status_counts.get('CLOSED', 0),
            'total_tickets': active_total + archive_total,
            'active_detail': f"OPEN {active_counts.get('OPEN', 0)} · IN_PROGRESS {active_counts.get('IN_PROGRESS', 0)} · PENDING {active_counts.get('PENDING', 0)}",
            'finished_detail': f"RESOLVED {status_counts.get('RESOLVED', 0)} · CLOSED {status_counts.get('CLOSED', 0)}",
            'total_detail': f"Aktif {active_total} · Arsip {archive_total}",
            'urgent_detail': 'Tiket aktif SLA kuning atau merah.',
        },
        'sync': {
            'last_synced_at': _format_datetime_display(last_synced_at),
            'last_synced_version': last_synced_at.isoformat() if isinstance(last_synced_at, datetime) else '',
            'active_count': getattr(sync_state, 'active_count', active_total) if sync_state else active_total,
            'archive_count': getattr(sync_state, 'archive_count', archive_total) if sync_state else archive_total,
            'history_count': getattr(sync_state, 'history_count', 0) if sync_state else 0,
            'last_error': last_error or '',
        },
        'lists': {
            'urgent_rows': [
                {
                    **item,
                    'row': _serialize_dashboard_row(item.get('row', {})),
                }
                for item in payload.get('urgent_rows', [])
            ],
            'pending_rows': [_serialize_dashboard_row(row) for row in payload.get('pending_rows', [])],
            'latest_active': [_serialize_dashboard_row(row) for row in payload.get('latest_active', [])],
            'finished_rows': [_serialize_dashboard_row(row) for row in payload.get('finished_rows', [])],
        },
    }


@admin_bp.route('/')
@login_required
@admin_required
def index():
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    try:
        payload = _dashboard_payload()
    except Exception as exc:
        flash(f'Dashboard admin memakai data terakhir yang tersedia. Sinkron sumber incident gagal: {exc}', 'warning')
        payload = {
            'status_counts': Counter(),
            'active_counts': Counter(),
            'active_total': 0,
            'archive_total': 0,
            'latest_active': [],
            'pending_rows': [],
            'urgent_rows': [],
            'urgent_total': 0,
            'finished_rows': [],
            'sync_state': type('SyncState', (), sync_state_summary(0, 0, 0))(),
        }
    return render_template(
        'admin_dashboard.html',
        dashboard_payload_json=_dashboard_json_payload(payload),
        dashboard_refresh_seconds=5,
        **payload,
    )


@admin_bp.route('/dashboard/data')
@login_required
@admin_required
def dashboard_data():
    try:
        payload = _dashboard_payload()
        return jsonify({'ok': True, 'data': _dashboard_json_payload(payload)})
    except Exception as exc:
        return jsonify({
            'ok': False,
            'error': f'Sinkron sumber incident gagal: {exc}',
            'data': {
                'sync': {
                    'last_error': str(exc),
                },
            },
        }), 500


@admin_bp.route('/employees')
@login_required
@admin_required
def employees():
    search_query = (request.args.get('q') or '').strip()
    page = max(request.args.get('page', default=1, type=int), 1)
    per_page = 20

    query = User.query
    if search_query:
        compact_q = ''.join(ch for ch in search_query if ch.isdigit())
        filters = [
            User.full_name.ilike(f'%{search_query}%'),
            User.unit.ilike(f'%{search_query}%'),
            User.phone.ilike(f'%{search_query}%'),
            User.role.ilike(f'%{search_query}%'),
            User.nip.ilike(f'%{search_query}%'),
        ]
        if compact_q:
            filters.append(func.replace(User.nip, ' ', '').ilike(f'%{compact_q}%'))
        query = query.filter(or_(*filters))

    total_users = User.query.count()
    filtered_count = query.count()
    total_pages = max(1, math.ceil(filtered_count / per_page)) if filtered_count else 1
    if page > total_pages:
        page = total_pages

    users = (
        query.order_by(User.role.desc(), User.full_name.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    ticket_count = PortalTicket.query.count()
    default_password = current_app.config['DEFAULT_EMPLOYEE_PASSWORD']
    return render_template(
        'admin_employees.html',
        users=users,
        ticket_count=ticket_count,
        default_password=default_password,
        total_users=total_users,
        filtered_count=filtered_count,
        search_query=search_query,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )


@admin_bp.route('/import', methods=['GET', 'POST'])
@login_required
@admin_required
def import_employees():
    if request.method == 'POST':
        upload = request.files.get('excel_file')
        default_password = (request.form.get('default_password') or current_app.config['DEFAULT_EMPLOYEE_PASSWORD']).strip()
        if not upload or not upload.filename:
            flash('Silakan pilih file Excel terlebih dahulu.', 'danger')
            return render_template('admin_import.html', default_password=default_password)
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp:
            upload.save(tmp.name)
            temp_path = tmp.name
        try:
            result = import_employees_from_excel(db, temp_path, default_password)
        except Exception as exc:
            flash(f'Import pegawai gagal: {exc}', 'danger')
            return render_template('admin_import.html', default_password=default_password)
        flash(
            f"Import selesai. Baru: {result['created']}, update: {result['updated']}, skip: {result['skipped']}",
            'success'
        )
        return redirect(url_for('admin.employees'))
    return render_template('admin_import.html', default_password=current_app.config['DEFAULT_EMPLOYEE_PASSWORD'])


@admin_bp.route('/employees/<int:user_id>/reset-password', methods=['POST'])
@login_required
@admin_required
def reset_password(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        flash('Pegawai tidak ditemukan.', 'danger')
        return _employees_redirect()

    new_password = (request.form.get('new_password') or current_app.config['DEFAULT_EMPLOYEE_PASSWORD']).strip()
    if len(new_password) < 6:
        flash('Password reset minimal 6 karakter.', 'danger')
        return _employees_redirect()

    user.set_password(new_password)
    user.must_change_password = True
    db.session.commit()
    flash(f'Password akun {user.full_name} berhasil direset.', 'success')
    return _employees_redirect()


@admin_bp.route('/employees/<int:user_id>/toggle-active', methods=['POST'])
@login_required
@admin_required
def toggle_active(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        flash('Pegawai tidak ditemukan.', 'danger')
        return _employees_redirect()
    if user.role == 'admin' and user.id == current_user.id:
        flash('Akun admin aktif yang sedang dipakai tidak boleh dinonaktifkan.', 'danger')
        return _employees_redirect()

    user.is_active_user = not bool(user.is_active_user)
    db.session.commit()
    status_label = 'diaktifkan' if user.is_active_user else 'dinonaktifkan'
    flash(f'Akun {user.full_name} berhasil {status_label}.', 'success')
    return _employees_redirect()


@admin_bp.route('/employees/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_employee(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        flash('Pegawai tidak ditemukan.', 'danger')
        return _employees_redirect()
    if user.role == 'admin':
        flash('Akun admin tidak boleh dihapus dari portal.', 'danger')
        return _employees_redirect()

    ticket_refs = PortalTicket.query.filter_by(user_id=user.id).count()
    if ticket_refs > 0:
        flash(
            f'Akun {user.full_name} tidak dihapus karena masih memiliki {ticket_refs} tiket portal. Gunakan nonaktifkan akun bila perlu.',
            'warning'
        )
        return _employees_redirect()

    db.session.delete(user)
    db.session.commit()
    flash(f'Akun {user.full_name} berhasil dihapus.', 'success')
    return _employees_redirect()
