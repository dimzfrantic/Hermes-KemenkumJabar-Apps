from collections import Counter
from datetime import datetime, timedelta, timezone
from io import BytesIO
import math
import re
import tempfile
from functools import wraps
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_, func

from extensions import db
from models import PendingEvidence, PortalTicket, User
from services.employee_import import import_employees_from_excel
from services.incident_cache import parse_portal_datetime
from services.incident_gateway import (
    create_incident_from_portal,
    normalize_portal_category,
    portal_category_label,
    portal_category_prefix,
    load_incident_module,
)
from services.incident_admin_store import get_dashboard_records, sync_state_summary
from services.incident_store import get_all_incidents, get_conn, get_history, get_record, split_links, sync_portal_ticket_from_db
from services.incident_recap import build_report_dataset, default_filter_values, export_excel, export_pdf, parse_filters
from services.drive_guard import check_drive_health, create_pending_evidence, pending_count, pending_rows, retry_pending_evidence
from services.telegram_notifier import send_new_ticket_notification

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
    minutes = max(int(minutes), 0)
    days, rem = divmod(minutes, 1440)
    hours, mins = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f'{days}d')
    if hours:
        parts.append(f'{hours}h')
    if mins or not parts:
        parts.append(f'{mins}m')
    return ' '.join(parts)


def _terminal_duration_minutes(row):
    status = str(row.get('status') or '').strip().upper()
    if status not in {'RESOLVED', 'CLOSED'}:
        return None
    created_dt = _parse_dt(row.get('created_at'))
    if status == 'CLOSED':
        end_dt = _parse_dt(row.get('closed_at')) or _parse_dt(row.get('update_terakhir')) or _parse_dt(row.get('resolved_at'))
    else:
        end_dt = _parse_dt(row.get('resolved_at')) or _parse_dt(row.get('update_terakhir')) or _parse_dt(row.get('closed_at'))
    if not created_dt or not end_dt:
        return None
    return max(0, int((end_dt - created_dt).total_seconds() / 60))


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


def _category_key_from_ticket_code(ticket_code):
    prefix = str(ticket_code or '').strip().upper().split('-', 1)[0]
    prefix_map = {
        'NET': 'NETWORK',
        'APP': 'APPLICATION',
        'HW': 'HARDWARE',
        'OTH': 'OTHER',
        'INC': 'OTHER',
    }
    return prefix_map.get(prefix, 'OTHER')


def _category_label_from_ticket_code(ticket_code):
    return portal_category_label(_category_key_from_ticket_code(ticket_code))


def _ticket_category_options():
    keys = ['NETWORK', 'APPLICATION', 'HARDWARE', 'OTHER']
    return [
        {
            'key': key,
            'label': portal_category_label(key),
            'prefix': portal_category_prefix(key),
        }
        for key in keys
    ]


def _dashboard_payload():
    active, archive, history_rows = get_dashboard_records()
    sync_state = type('SyncState', (), sync_state_summary(len(active), len(archive), len(history_rows)))()
    latest_status_entry_times = _build_latest_status_entry_times(history_rows)
    now = datetime.now()

    all_rows = active + archive

    for row in all_rows:
        row['category_label'] = _category_label_from_ticket_code(row.get('ticket_code'))
        terminal_duration = _terminal_duration_minutes(row)
        if terminal_duration is not None:
            row['durasi'] = _format_minutes(terminal_duration)

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
    terminal_duration = _terminal_duration_minutes(row)
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
        'durasi': _format_minutes(terminal_duration) if terminal_duration is not None else (row.get('durasi') or '-'),
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


def _report_type_choices():
    return [
        ('daftar_tiket', 'Rekap daftar tiket'),
        ('per_petugas', 'Rekap per petugas'),
        ('per_lokasi_kategori', 'Rekap per lokasi/kategori'),
        ('eksekutif', 'Rekap eksekutif'),
    ]


def _recap_form_values(args=None):
    defaults = default_filter_values()
    source = args or request.args
    values = dict(defaults)
    for key in defaults:
        raw_value = source.get(key) if source else None
        if raw_value is not None and str(raw_value).strip() != '':
            values[key] = str(raw_value).strip()
    values['report_type'] = values.get('report_type') or 'daftar_tiket'
    values['format'] = values.get('format') or 'xlsx'
    return values


def _serialize_ticket_row(row):
    status = str(row.get('status') or '').upper()
    return {
        'alias': row.get('alias') or '-',
        'ticket_code': row.get('ticket_code') or '-',
        'category_key': _category_key_from_ticket_code(row.get('ticket_code')),
        'category_label': _category_label_from_ticket_code(row.get('ticket_code')),
        'status': status or '-',
        'status_class': {
            'OPEN': 'status-open',
            'IN_PROGRESS': 'status-progress',
            'PENDING': 'status-pending',
            'RESOLVED': 'status-resolved',
            'CLOSED': 'status-closed',
        }.get(status, 'status-open'),
        'lokasi': row.get('lokasi') or '-',
        'masalah': row.get('masalah') or '-',
        'pelapor': row.get('pelapor') or '-',
        'petugas': row.get('ditangani_oleh') or '-',
        'created_at': row.get('created_at') or '-',
        'update_terakhir': row.get('update_terakhir') or '-',
        'catatan': row.get('catatan_terakhir') or row.get('alasan_pending') or '-',
        'alasan_pending': row.get('alasan_pending') or '',
        'durasi': row.get('durasi') or '',
        'bukti_awal_links': split_links(row.get('bukti_awal') or ''),
        'bukti_resolve_links': split_links(row.get('bukti_resolve') or ''),
        'folder_bukti_links': split_links(row.get('folder_bukti') or ''),
    }


def _active_ticket_rows():
    active_rows, archive_rows = get_all_incidents(include_archive=True)
    active_list = []
    resolved_list = []
    for row in sorted(
        active_rows,
        key=lambda item: _parse_dt(item.get('update_terakhir')) or _parse_dt(item.get('created_at')) or datetime.min,
        reverse=True,
    ):
        active_list.append(_serialize_ticket_row(row))
    for row in sorted(
        [r for r in archive_rows if str(r.get('status') or '').upper() == 'RESOLVED'],
        key=lambda item: _parse_dt(item.get('update_terakhir')) or _parse_dt(item.get('resolved_at')) or _parse_dt(item.get('created_at')) or datetime.min,
        reverse=True,
    ):
        resolved_list.append(_serialize_ticket_row(row))
    return active_list, resolved_list


def _rename_ticket_code_and_category(old_ticket_code: str, new_ticket_code: str, new_summary: str) -> None:
    old_code = str(old_ticket_code or '').strip().upper()
    new_code = str(new_ticket_code or '').strip().upper()
    summary = ' '.join(str(new_summary or '').split())
    if not old_code or not new_code:
        raise ValueError('Kode tiket tidak valid.')
    if not summary:
        raise ValueError('Judul tiket wajib diisi.')

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM incidents WHERE UPPER(ticket_code)=UPPER(%s) LIMIT 1', (old_code,))
            row = cur.fetchone()
            if not row:
                raise ValueError(f'Tiket tidak ditemukan: {old_code}')

            if old_code != new_code:
                cur.execute('SELECT 1 FROM incidents WHERE UPPER(ticket_code)=UPPER(%s) LIMIT 1', (new_code,))
                if cur.fetchone():
                    raise ValueError(f'Kode tiket tujuan sudah dipakai: {new_code}')

            cur.execute(
                '''
                UPDATE incidents
                   SET ticket_code = %s,
                       masalah = %s,
                       updated_ts = NOW()
                 WHERE UPPER(ticket_code)=UPPER(%s)
                ''',
                (new_code, summary, old_code),
            )
            cur.execute(
                '''
                UPDATE incident_history
                   SET ticket_code = %s
                 WHERE UPPER(ticket_code)=UPPER(%s)
                ''',
                (new_code, old_code),
            )
            cur.execute(
                '''
                UPDATE incident_attachments
                   SET ticket_code = %s
                 WHERE UPPER(ticket_code)=UPPER(%s)
                ''',
                (new_code, old_code),
            )
        conn.commit()


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


@admin_bp.route('/tickets')
@login_required
@admin_required
def active_tickets():
    try:
        active_tickets, resolved_tickets = _active_ticket_rows()
    except Exception as exc:
        flash(f'Halaman operasional tiket belum bisa dimuat: {exc}', 'danger')
        active_tickets, resolved_tickets = [], []
    return render_template(
        'admin_active_tickets.html',
        active_tickets=active_tickets,
        resolved_tickets=resolved_tickets,
        total_tickets=len(active_tickets) + len(resolved_tickets),
        drive_health=check_drive_health(),
        pending_evidence_count=pending_count(),
        pending_evidence_rows=pending_rows(limit=8),
    )


@admin_bp.route('/drive-guard/retry', methods=['POST'])
@login_required
@admin_required
def retry_drive_pending():
    health = check_drive_health()
    if not health.get('ok'):
        flash(f"Google Drive belum siap: {health.get('message')}", 'danger')
        return redirect(url_for('admin.active_tickets'))
    results = retry_pending_evidence(limit=50)
    success_count = sum(1 for item in results if item.get('ok'))
    fail_count = len(results) - success_count
    if success_count:
        flash(f'{success_count} bukti pending berhasil diupload ulang.', 'success')
    if fail_count:
        flash(f'{fail_count} bukti pending masih gagal. Cek status Drive Guard.', 'warning')
    if not results:
        flash('Tidak ada bukti pending untuk di-retry.', 'info')
    return redirect(url_for('admin.active_tickets'))


@admin_bp.route('/drive-guard/status')
@login_required
@admin_required
def drive_guard_status():
    return jsonify({
        'ok': True,
        'drive': check_drive_health(),
        'pending_count': pending_count(),
    })


@admin_bp.route('/tickets/<ticket_code>/delete', methods=['POST'])
@login_required
@admin_required
def delete_ticket(ticket_code):
    normalized_code = str(ticket_code or '').strip().upper()
    if not normalized_code:
        flash('Kode tiket tidak valid.', 'danger')
        return redirect(url_for('admin.active_tickets'))

    incident_module = load_incident_module()
    args = SimpleNamespace(ticket=normalized_code)
    response_text = str(incident_module.cmd_delete(args) or '').strip()
    if response_text.startswith('[ERROR]'):
        flash(response_text, 'danger')
        return redirect(url_for('admin.active_tickets'))

    portal_refs = PortalTicket.query.filter_by(ticket_code=normalized_code).all()
    removed_portal_rows = len(portal_refs)
    for row in portal_refs:
        db.session.delete(row)
    db.session.commit()
    flash(f'Tiket {normalized_code} berhasil dihapus. Referensi portal terhapus: {removed_portal_rows}.', 'success')
    return redirect(url_for('admin.active_tickets'))


@admin_bp.route('/tickets/<ticket_code>/edit', methods=['POST'])
@login_required
@admin_required
def edit_ticket(ticket_code):
    old_code = str(ticket_code or '').strip().upper()
    summary = ' '.join(str(request.form.get('summary') or '').split())
    category_key = normalize_portal_category(str(request.form.get('category') or '').strip().upper())
    status = str(request.form.get('status') or '').strip().upper()
    note = ' '.join(str(request.form.get('note') or '').split())
    current_record = get_record(old_code) if old_code else None
    if not old_code:
        flash('Kode tiket tidak valid.', 'danger')
        return redirect(url_for('admin.active_tickets'))
    if not current_record:
        flash(f'Tiket tidak ditemukan: {old_code}', 'danger')
        return redirect(url_for('admin.active_tickets'))
    if not summary:
        flash('Judul tiket wajib diisi.', 'danger')
        return redirect(url_for('admin.active_tickets'))
    if status not in {'OPEN', 'IN_PROGRESS', 'PENDING', 'RESOLVED', 'CLOSED'}:
        flash('Status tiket tidak dikenali.', 'danger')
        return redirect(url_for('admin.active_tickets'))
    if status == 'PENDING' and not note:
        note = str(current_record.get('alasan_pending') or current_record.get('catatan_terakhir') or '').strip()
        if not note:
            flash('Alasan pending wajib diisi.', 'danger')
            return redirect(url_for('admin.active_tickets'))

    attachment = request.files.get('attachment')
    bukti_files = []
    if attachment and attachment.filename:
        allowed_ext = {'.png', '.jpg', '.jpeg', '.webp', '.pdf'}
        ext = Path(attachment.filename).suffix.lower()
        if ext not in allowed_ext:
            flash('Lampiran harus berupa png, jpg, jpeg, webp, atau pdf.', 'danger')
            return redirect(url_for('admin.active_tickets'))
        upload_dir = Path(current_app.config.get('UPLOAD_FOLDER', 'uploads'))
        upload_dir.mkdir(parents=True, exist_ok=True)
        safe_name = f"{old_code}_{uuid4().hex[:8]}{ext}"
        save_path = upload_dir / safe_name
        attachment.save(str(save_path))
        if save_path.exists() and save_path.stat().st_size > 0:
            bukti_files = [str(save_path)]
        else:
            flash('Gagal menyimpan file upload.', 'danger')
            return redirect(url_for('admin.active_tickets'))

    try:
        upload_pending = False
        prefix = portal_category_prefix(category_key)
        parts = old_code.split('-')
        if len(parts) != 3:
            raise ValueError(f'Format kode tiket tidak dikenali: {old_code}')
        new_code = f'{prefix}-{parts[1]}-{parts[2]}'
        _rename_ticket_code_and_category(old_code, new_code, summary)

        is_terminal = status in ('RESOLVED', 'CLOSED')
        incident_module = load_incident_module()
        args = SimpleNamespace(
            ticket=new_code,
            status=status,
            note=note or f"Status diubah ke {status} oleh {current_user.full_name or 'Admin Portal'}",
            handled_by='',
            sender_name=current_user.full_name or 'Admin Portal',
            message='',
            bukti_awal='',
            bukti_resolve='',
            bukti_awal_files=bukti_files if not is_terminal else [],
            bukti_resolve_files=bukti_files if is_terminal else [],
        )
        response_text = str(incident_module.cmd_update(args) or '').strip()
        if response_text.startswith('[ERROR]'):
            upload_failed = bool(bukti_files) and ('Upload bukti' in response_text or 'Google Drive' in response_text or 'Token/akses' in response_text)
            if upload_failed:
                evidence_kind = 'bukti_resolve' if is_terminal else 'bukti_awal'
                create_pending_evidence(
                    ticket_code=new_code,
                    status_label=status,
                    evidence_kind=evidence_kind,
                    file_paths=bukti_files,
                    note=note or f"Status diubah ke {status} oleh {current_user.full_name or 'Admin Portal'}",
                    error_message=response_text,
                    created_by=current_user.full_name or 'Admin Portal',
                )
                args.bukti_awal_files = []
                args.bukti_resolve_files = []
                response_text = str(incident_module.cmd_update(args) or '').strip()
                if response_text.startswith('[ERROR]'):
                    raise ValueError(response_text)
                upload_pending = True
                flash('Bukti belum terkirim ke Google Drive dan disimpan sebagai pending upload. Silakan retry setelah token Drive valid.', 'warning')
            else:
                raise ValueError(response_text)

        if bukti_files and not upload_pending:
            import re as _re
            bukti_field = 'bukti_resolve' if is_terminal else 'bukti_awal'
            bukti_match = _re.search(rf'{("Bukti selesai" if is_terminal else "Bukti awal")}:\s*(https?://\S+)', response_text)
            if bukti_match:
                flash(f'Bukti berhasil diupload: {bukti_match.group(1)}', 'success')
            else:
                flash(f'Bukti berhasil diupload untuk tiket {new_code}.', 'success')

        portal_refs = PortalTicket.query.filter_by(ticket_code=old_code).all()
        for row in portal_refs:
            row.ticket_code = new_code
            row.problem_summary = summary
            row.category = category_key
            sync_portal_ticket_from_db(row)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        flash(f'Edit tiket gagal: {exc}', 'danger')
        return redirect(url_for('admin.active_tickets'))

    flash('Berhasil Disimpan.', 'success')
    return redirect(url_for('admin.active_tickets'))


@admin_bp.route('/tickets/create', methods=['POST'])
@login_required
@admin_required
def create_ticket():
    category = normalize_portal_category((request.form.get('category') or '').strip().upper())
    location = ' '.join((request.form.get('location') or '').split())
    summary = ' '.join((request.form.get('summary') or '').split())
    reporter = ' '.join((request.form.get('reporter') or '').split())
    attachment = request.files.get('attachment')

    if not location:
        flash('Lokasi wajib diisi.', 'danger')
        return redirect(url_for('admin.active_tickets'))
    if not summary:
        flash('Masalah wajib diisi.', 'danger')
        return redirect(url_for('admin.active_tickets'))
    if not reporter:
        flash('Pelapor wajib diisi.', 'danger')
        return redirect(url_for('admin.active_tickets'))

    categories = current_app.config.get('TICKET_CATEGORIES', {})
    prefix_to_category = {v: k for k, v in {
        'NETWORK': 'NET', 'APPLICATION': 'APP', 'HARDWARE': 'HW', 'OTHER': 'OTH'
    }.items()}
    category = prefix_to_category.get(category, category)
    if category not in categories:
        category = 'NETWORK'

    attachment_path = None
    if attachment and attachment.filename:
        allowed_ext = {'.png', '.jpg', '.jpeg', '.webp', '.pdf'}
        ext = Path(attachment.filename).suffix.lower()
        if ext in allowed_ext:
            folder = Path(current_app.config.get('UPLOAD_FOLDER', 'uploads')) / datetime.now().strftime('%Y%m%d')
            folder.mkdir(parents=True, exist_ok=True)
            safe_name = f"ADMIN_{uuid4().hex[:8]}{ext}"
            attachment_path = str(folder / safe_name)
            attachment.save(attachment_path)

    try:
        admin_user = User.query.filter_by(role='admin').first()
        if not admin_user:
            admin_user = User.query.first()
        if not admin_user:
            flash('Tidak ada user admin yang tersedia.', 'danger')
            return redirect(url_for('admin.active_tickets'))

        original_name = admin_user.full_name
        admin_user.full_name = reporter
        db.session.flush()
        create_result = create_incident_from_portal(
            admin_user, category, summary, location, attachment_path
        )
        admin_user.full_name = original_name
        db.session.flush()
    except Exception as exc:
        flash(f'Gagal membuat tiket: {exc}', 'danger')
        return redirect(url_for('admin.active_tickets'))

    ticket = PortalTicket(
        user_id=admin_user.id,
        user=admin_user,
        ticket_code=create_result['ticket_code'],
        ticket_alias=create_result['ticket_alias'],
        category=category,
        location=location,
        problem_summary=summary,
        status_cache='OPEN',
        raw_create_response=create_result['raw_response'],
    )
    db.session.add(ticket)
    db.session.flush()

    try:
        incident_record = get_record(ticket.ticket_code)
        ok, detail_text = send_new_ticket_notification(ticket, incident_record=incident_record)
        ticket.notification_ok = ok
        ticket.notification_detail = detail_text
        if ok:
            flash(f'Tiket berhasil dibuat: {ticket.ticket_alias} / {ticket.ticket_code}', 'success')
        else:
            flash(f'Tiket berhasil dibuat: {ticket.ticket_alias} / {ticket.ticket_code}', 'success')
            flash(f'Notifikasi Telegram: {detail_text}', 'warning')
    except Exception as exc:
        ticket.notification_ok = False
        ticket.notification_detail = str(exc)
        flash(f'Tiket berhasil dibuat: {ticket.ticket_alias} / {ticket.ticket_code}', 'success')
        flash(f'Notifikasi Telegram gagal: {exc}', 'warning')

    db.session.commit()
    return redirect(url_for('admin.active_tickets'))


@admin_bp.route('/history')
@login_required
@admin_required
def ticket_history():
    query_text = ' '.join(str(request.args.get('q') or '').split())
    status_filter = str(request.args.get('status') or '').strip().upper()
    ticket_filter = str(request.args.get('ticket') or '').strip().upper()
    try:
        active_rows, archive_rows = get_all_incidents(include_archive=True)
        incident_map = {str(row.get('ticket_code') or '').upper(): row for row in active_rows + archive_rows}
        history_rows = get_history(ticket_filter or None)
    except Exception as exc:
        flash(f'Riwayat tiket belum bisa dimuat: {exc}', 'danger')
        incident_map = {}
        history_rows = []

    normalized_q = query_text.lower()
    filtered_rows = []
    for row in history_rows:
        ticket_code_value = str(row.get('ticket_code') or '').upper()
        incident = incident_map.get(ticket_code_value, {})
        if status_filter and str(row.get('status_after') or '').upper() != status_filter:
            continue
        if normalized_q:
            alias_value = str(row.get('alias') or '').strip()
            ticket_alias_label = f'tiket {alias_value}' if alias_value else ''
            ticket_alias_compact = f'tiket{alias_value}' if alias_value else ''
            haystack = ' '.join(str(value or '') for value in [
                ticket_code_value,
                alias_value,
                ticket_alias_label,
                ticket_alias_compact,
                row.get('action'),
                row.get('status_before'),
                row.get('status_after'),
                row.get('ditangani_oleh'),
                row.get('catatan_terakhir'),
                row.get('catatan'),
                incident.get('lokasi'),
                incident.get('masalah'),
                incident.get('pelapor'),
            ]).lower()
            normalized_q_compact = normalized_q.replace(' ', '')
            if normalized_q not in haystack and normalized_q_compact not in haystack.replace(' ', ''):
                continue
        filtered_rows.append({
            **row,
            'incident': incident,
            'bukti_baru_links': split_links(row.get('bukti_baru') or ''),
            'bukti_awal_links': split_links(row.get('bukti_awal') or ''),
            'bukti_resolve_links': split_links(row.get('bukti_resolve') or ''),
            'folder_bukti_links': split_links(row.get('folder_bukti') or ''),
        })

    filtered_rows = list(reversed(filtered_rows))
    total_rows = len(filtered_rows)
    limit = min(max(request.args.get('limit', default=100, type=int), 25), 500)
    shown_rows = filtered_rows[:limit]
    return render_template(
        'admin_ticket_history.html',
        history_rows=shown_rows,
        total_rows=total_rows,
        limit=limit,
        query_text=query_text,
        status_filter=status_filter,
        ticket_filter=ticket_filter,
        status_options=['OPEN', 'IN_PROGRESS', 'PENDING', 'RESOLVED', 'CLOSED'],
    )


@admin_bp.route('/recap')
@login_required
@admin_required
def recap():
    recap_form_values = _recap_form_values()
    try:
        filters = parse_filters(recap_form_values)
        recap_dataset = build_report_dataset(recap_form_values.get('report_type') or 'daftar_tiket', filters)
    except ValueError as exc:
        flash(str(exc), 'danger')
        recap_form_values = default_filter_values()
        filters = parse_filters(recap_form_values)
        recap_dataset = build_report_dataset(recap_form_values.get('report_type') or 'daftar_tiket', filters)
    except Exception as exc:
        flash(f'Rekap insiden tidak dapat dimuat: {exc}', 'danger')
        recap_form_values = default_filter_values()
        filters = parse_filters(recap_form_values)
        recap_dataset = build_report_dataset(recap_form_values.get('report_type') or 'daftar_tiket', filters)

    return render_template(
        'admin_recap.html',
        recap_form_values=recap_form_values,
        recap_report_types=_report_type_choices(),
        recap_dataset=recap_dataset,
    )


@admin_bp.route('/recap/export')
@login_required
@admin_required
def export_recap():
    report_type = str(request.args.get('report_type') or 'daftar_tiket').strip() or 'daftar_tiket'
    output_format = str(request.args.get('format') or 'xlsx').strip().lower() or 'xlsx'
    if output_format not in {'xlsx', 'pdf'}:
        flash('Format rekap tidak dikenali.', 'danger')
        return redirect(url_for('admin.recap'))
    try:
        filters = parse_filters(request.args)
        dataset = build_report_dataset(report_type, filters)
    except ValueError as exc:
        flash(str(exc), 'danger')
        return redirect(url_for('admin.recap', **_recap_form_values(request.args)))
    except Exception as exc:
        flash(f'Gagal membuat rekap: {exc}', 'danger')
        return redirect(url_for('admin.recap', **_recap_form_values(request.args)))

    safe_period = f"{filters['start_date'].strftime('%Y%m%d')}-{filters['end_date'].strftime('%Y%m%d')}"
    filename_base = f"rekap-{report_type.replace('_', '-')}-{safe_period}"
    file_bytes: BytesIO
    if output_format == 'xlsx':
        file_bytes = export_excel(dataset)
        mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        download_name = f'{filename_base}.xlsx'
    else:
        file_bytes = export_pdf(dataset)
        mimetype = 'application/pdf'
        download_name = f'{filename_base}.pdf'

    return send_file(
        file_bytes,
        mimetype=mimetype,
        as_attachment=True,
        download_name=download_name,
        max_age=0,
    )


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
