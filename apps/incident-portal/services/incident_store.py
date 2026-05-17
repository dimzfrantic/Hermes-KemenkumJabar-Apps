from datetime import datetime
import re

import psycopg
from psycopg.rows import dict_row
from flask import current_app

ACTIVE_STATUSES = {'OPEN', 'IN_PROGRESS', 'PENDING'}
TERMINAL_STATUSES = {'RESOLVED', 'CLOSED'}
DATETIME_FORMATS = ('%d-%m-%Y %H:%M:%S', '%d-%m-%Y %H:%M', '%Y-%m-%d %H:%M:%S')
OUTPUT_DATETIME_FORMAT = '%d-%m-%Y %H:%M:%S'


def db_enabled():
    return bool(str(current_app.config.get('INCIDENT_DATABASE_URL', '') or '').strip())


def get_conn():
    database_url = str(current_app.config.get('INCIDENT_DATABASE_URL', '') or '').strip()
    if not database_url:
        raise RuntimeError('INCIDENT_DATABASE_URL belum dikonfigurasi')
    return psycopg.connect(database_url.replace('postgresql+psycopg://', 'postgresql://'), row_factory=dict_row)


def parse_dt(value):
    if isinstance(value, datetime):
        return value
    text = str(value or '').strip()
    if not text:
        return None
    for fmt in DATETIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def format_dt(value):
    dt_value = parse_dt(value)
    return dt_value.strftime(OUTPUT_DATETIME_FORMAT) if dt_value else None


def split_links(value):
    parts = []
    seen = set()
    for chunk in re.split(r'\s*\|\s*|\s*;\s*|\s*\n\s*', str(value or '').strip()):
        item = chunk.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        parts.append(item)
    return parts


def incident_row_to_dict(row):
    if not row:
        return None
    return {
        'ticket_code': row.get('ticket_code'),
        'created_at': format_dt(row.get('created_at')),
        'lokasi': row.get('lokasi') or '',
        'masalah': row.get('masalah') or '',
        'pelapor': row.get('pelapor') or '',
        'status': row.get('status') or 'OPEN',
        'durasi': row.get('durasi') or '',
        'bukti_awal': row.get('bukti_awal') or '',
        'update_terakhir': format_dt(row.get('update_terakhir')),
        'alias': row.get('alias'),
        'ditangani_oleh': row.get('ditangani_oleh') or '',
        'alasan_pending': row.get('alasan_pending') or '',
        'catatan_terakhir': row.get('catatan_terakhir') or '',
        'bukti_resolve': row.get('bukti_resolve') or '',
        'folder_bukti': row.get('folder_bukti') or '',
        'archived_at': format_dt(row.get('archived_at')),
        'source_sheet': row.get('source_sheet') or ('incident_log' if str(row.get('status', '')).upper() in ACTIVE_STATUSES else 'incident_archive'),
        'resolved_at': format_dt(row.get('resolved_at')),
        'closed_at': format_dt(row.get('closed_at')),
    }


def history_row_to_dict(row):
    if not row:
        return None
    return {
        'update_id': row.get('update_id') or '',
        'ticket_code': row.get('ticket_code') or '',
        'alias': row.get('alias'),
        'update_time': format_dt(row.get('update_time')),
        'action': row.get('action') or '',
        'status_before': row.get('status_before') or '',
        'status_after': row.get('status_after') or '',
        'ditangani_oleh': row.get('ditangani_oleh') or '',
        'alasan_pending': row.get('alasan_pending') or '',
        'catatan_terakhir': row.get('catatan_terakhir') or '',
        'catatan': row.get('catatan') or '',
        'raw_message': row.get('raw_message') or '',
        'bukti_awal': row.get('bukti_awal') or '',
        'bukti_resolve': row.get('bukti_resolve') or '',
        'folder_bukti': row.get('folder_bukti') or '',
        'bukti_status': row.get('bukti_status') or '',
        'bukti_baru': row.get('bukti_baru') or '',
    }


def get_all_incidents(include_archive=True):
    with get_conn() as conn:
        with conn.cursor() as cur:
            if include_archive:
                cur.execute('SELECT * FROM incidents ORDER BY created_at ASC, id ASC')
            else:
                cur.execute("SELECT * FROM incidents WHERE status = ANY(%s) ORDER BY created_at ASC, id ASC", (list(ACTIVE_STATUSES),))
            rows = cur.fetchall()
    records = [incident_row_to_dict(row) for row in rows]
    if include_archive:
        active_records = [row for row in records if str(row.get('status', '')).upper() in ACTIVE_STATUSES]
        archive_records = [row for row in records if str(row.get('status', '')).upper() in TERMINAL_STATUSES]
        return active_records, archive_records
    return records, []


def get_record(ticket_code):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM incidents WHERE UPPER(ticket_code)=UPPER(%s) LIMIT 1', (ticket_code,))
            row = cur.fetchone()
    return incident_row_to_dict(row) if row else None


def get_history(ticket_code=None, limit=None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            if ticket_code:
                cur.execute(
                    'SELECT * FROM incident_history WHERE UPPER(ticket_code)=UPPER(%s) ORDER BY update_time ASC, id ASC',
                    (ticket_code,),
                )
            else:
                cur.execute('SELECT * FROM incident_history ORDER BY update_time ASC, id ASC')
            rows = cur.fetchall()
    records = [history_row_to_dict(row) for row in rows]
    if limit:
        return records[-limit:]
    return records


def sync_portal_ticket_from_db(portal_ticket):
    record = get_record(portal_ticket.ticket_code)
    if not record:
        return False
    portal_ticket.status_cache = record.get('status') or portal_ticket.status_cache or 'OPEN'
    portal_ticket.last_note_cache = record.get('catatan_terakhir') or None
    portal_ticket.handled_by_cache = record.get('ditangani_oleh') or None
    portal_ticket.last_update_cache = record.get('update_terakhir') or None
    return True
