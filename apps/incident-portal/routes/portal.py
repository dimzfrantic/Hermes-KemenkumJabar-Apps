from datetime import datetime
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from models import PortalTicket
from services.incident_gateway import (
    create_incident_from_portal,
    get_ticket_history,
    normalize_portal_category,
    portal_category_label,
    portal_category_prefix,
    sync_portal_ticket,
    sync_portal_tickets,
)
from services.telegram_notifier import send_new_ticket_notification

portal_bp = Blueprint('portal', __name__)


def _ticket_view_meta(ticket):
    category_key = normalize_portal_category(getattr(ticket, 'category', None))
    ticket_code = str(getattr(ticket, 'ticket_code', '') or '').strip().upper()
    prefix = ticket_code.split('-', 1)[0] if '-' in ticket_code else portal_category_prefix(category_key)
    return {
        'category_key': category_key,
        'category_label': portal_category_label(category_key),
        'prefix': prefix,
    }


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

@portal_bp.route('/')
@login_required
def dashboard():
    tickets = PortalTicket.query.filter_by(user_id=current_user.id).order_by(PortalTicket.created_at.desc()).all()
    try:
        synced = sync_portal_tickets(tickets, active_only=True)
        if synced:
            db.session.commit()
    except Exception as exc:
        db.session.rollback()
        flash(f'Sinkron data tiket menggunakan cache terakhir karena sumber incident sedang bermasalah: {exc}', 'warning')
    ticket_meta = {ticket.id: _ticket_view_meta(ticket) for ticket in tickets}
    return render_template('dashboard.html', tickets=tickets, ticket_meta=ticket_meta)

@portal_bp.route('/tickets/new', methods=['GET', 'POST'])
@login_required
def new_ticket():
    categories = current_app.config['TICKET_CATEGORIES']
    if request.method == 'POST':
        category = normalize_portal_category((request.form.get('category') or '').strip().upper())
        location = ' '.join((request.form.get('location') or '').split())
        summary = ' '.join((request.form.get('problem_summary') or '').split())
        detail = (request.form.get('detail_description') or '').strip()
        contact_phone = (request.form.get('contact_phone') or current_user.phone or '').strip()
        attachment = request.files.get('attachment')

        if category not in categories:
            flash('Kategori tiket belum dipilih.', 'danger')
            return render_template('new_ticket.html', categories=categories)
        if not location or not summary:
            flash('Lokasi dan ringkasan masalah wajib diisi.', 'danger')
            return render_template('new_ticket.html', categories=categories)

        attachment_path = None
        if attachment and attachment.filename:
            if not allowed_file(attachment.filename):
                flash('Lampiran harus berupa png, jpg, jpeg, webp, atau pdf.', 'danger')
                return render_template('new_ticket.html', categories=categories)
            folder = Path(current_app.config['UPLOAD_FOLDER']) / datetime.now().strftime('%Y%m%d')
            folder.mkdir(parents=True, exist_ok=True)
            extension = attachment.filename.rsplit('.', 1)[1].lower()
            safe_name = f"{current_user.nip}_{uuid4().hex}.{extension}"
            attachment_path = str(folder / safe_name)
            attachment.save(attachment_path)

        try:
            create_result = create_incident_from_portal(current_user, category, summary, location, attachment_path)
        except Exception as exc:
            flash(f'Gagal membuat tiket pada incident engine: {exc}', 'danger')
            return render_template('new_ticket.html', categories=categories)

        ticket = PortalTicket(
            user_id=current_user.id,
            user=current_user,
            ticket_code=create_result['ticket_code'],
            ticket_alias=create_result['ticket_alias'],
            category=category,
            location=location,
            problem_summary=summary,
            detail_description=detail,
            contact_phone=contact_phone or None,
            attachment_path=attachment_path,
            status_cache='OPEN',
            raw_create_response=create_result['raw_response'],
        )
        db.session.add(ticket)
        db.session.flush()
        ok, detail_text = send_new_ticket_notification(ticket)
        ticket.notification_ok = ok
        ticket.notification_detail = detail_text
        db.session.commit()
        flash(f"Tiket berhasil dibuat: {ticket.ticket_alias} / {ticket.ticket_code}", 'success')
        if not ok:
            flash(f'Notifikasi Telegram belum terkirim: {detail_text}', 'warning')
        return redirect(url_for('portal.ticket_detail', ticket_id=ticket.id, skip_sync=1))

    return render_template('new_ticket.html', categories=categories)

@portal_bp.route('/tickets/<int:ticket_id>')
@login_required
def ticket_detail(ticket_id):
    ticket = PortalTicket.query.filter_by(id=ticket_id, user_id=current_user.id).first_or_404()
    skip_sync = request.args.get('skip_sync') == '1'
    if not skip_sync:
        try:
            sync_portal_ticket(ticket)
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            flash(f'Detail tiket memakai cache terakhir karena sumber incident sedang bermasalah: {exc}', 'warning')
    history_rows = get_ticket_history(ticket.ticket_code, limit=20)
    ticket_meta = _ticket_view_meta(ticket)
    return render_template('ticket_detail.html', ticket=ticket, history_rows=history_rows, ticket_meta=ticket_meta)

@portal_bp.route('/tickets/<int:ticket_id>/sync', methods=['POST'])
@login_required
def sync_ticket(ticket_id):
    ticket = PortalTicket.query.filter_by(id=ticket_id, user_id=current_user.id).first_or_404()
    try:
        if sync_portal_ticket(ticket, force_refresh_source=True):
            db.session.commit()
            flash('Status tiket berhasil disinkronkan.', 'success')
        else:
            flash('Tiket belum ditemukan di sumber incident.', 'warning')
    except Exception as exc:
        db.session.rollback()
        flash(f'Sinkron ulang gagal karena sumber incident belum bisa dibaca: {exc}', 'danger')
    return redirect(url_for('portal.ticket_detail', ticket_id=ticket.id, skip_sync=1))
