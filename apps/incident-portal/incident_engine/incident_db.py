#!/usr/bin/env python3
import os
import re
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

ACTIVE_STATUSES = {'OPEN', 'IN_PROGRESS', 'PENDING'}
TERMINAL_STATUSES = {'RESOLVED', 'CLOSED'}
DATETIME_FORMAT = '%d-%m-%Y %H:%M:%S'

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS incidents (
    id BIGSERIAL PRIMARY KEY,
    ticket_code VARCHAR(64) NOT NULL UNIQUE,
    alias INTEGER NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL,
    lokasi TEXT NOT NULL,
    masalah TEXT NOT NULL,
    pelapor TEXT NOT NULL,
    status VARCHAR(32) NOT NULL,
    durasi VARCHAR(64),
    bukti_awal TEXT,
    update_terakhir TIMESTAMP NOT NULL,
    ditangani_oleh TEXT,
    alasan_pending TEXT,
    catatan_terakhir TEXT,
    bukti_resolve TEXT,
    folder_bukti TEXT,
    archived_at TIMESTAMP,
    source_sheet VARCHAR(64) NOT NULL DEFAULT 'incident_log',
    resolved_at TIMESTAMP,
    closed_at TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_ts TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status);
CREATE INDEX IF NOT EXISTS idx_incidents_source_sheet ON incidents(source_sheet);
CREATE INDEX IF NOT EXISTS idx_incidents_created_at ON incidents(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_incidents_update_terakhir ON incidents(update_terakhir DESC);

CREATE TABLE IF NOT EXISTS incident_history (
    id BIGSERIAL PRIMARY KEY,
    update_id VARCHAR(128) NOT NULL UNIQUE,
    ticket_code VARCHAR(64) NOT NULL,
    alias INTEGER,
    update_time TIMESTAMP NOT NULL,
    action VARCHAR(64),
    status_before VARCHAR(32),
    status_after VARCHAR(32),
    ditangani_oleh TEXT,
    alasan_pending TEXT,
    catatan_terakhir TEXT,
    catatan TEXT,
    raw_message TEXT,
    bukti_awal TEXT,
    bukti_resolve TEXT,
    folder_bukti TEXT,
    bukti_status VARCHAR(64),
    bukti_baru TEXT,
    created_ts TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_incident_history_ticket_code ON incident_history(ticket_code);
CREATE INDEX IF NOT EXISTS idx_incident_history_update_time ON incident_history(update_time DESC);
CREATE INDEX IF NOT EXISTS idx_incident_history_status_after ON incident_history(status_after);

CREATE TABLE IF NOT EXISTS incident_attachments (
    id BIGSERIAL PRIMARY KEY,
    ticket_code VARCHAR(64) NOT NULL,
    history_update_id VARCHAR(128),
    kind VARCHAR(32) NOT NULL,
    status_label VARCHAR(32),
    file_url TEXT NOT NULL,
    source_filename TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_incident_attachments_ticket_code ON incident_attachments(ticket_code);
CREATE INDEX IF NOT EXISTS idx_incident_attachments_history_update_id ON incident_attachments(history_update_id);
"""


def _env_value_from_file(env_path: Path, key: str) -> str:
    if not env_path.exists():
        return ''
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        if k.strip() == key:
            return v.strip().strip('"').strip("'")
    return ''


def load_database_url() -> str:
    base_dir = Path(__file__).resolve().parent
    portal_dir = base_dir.parent
    env_candidates = [
        os.environ.get('INCIDENT_DATABASE_URL', '').strip(),
        os.environ.get('DATABASE_URL', '').strip(),
        _env_value_from_file(base_dir / '.env', 'DATABASE_URL'),
        _env_value_from_file(portal_dir / '.env', 'INCIDENT_DATABASE_URL'),
    ]
    for value in env_candidates:
        if value and value.startswith('postgresql'):
            return value
    return ''


def db_enabled() -> bool:
    return bool(load_database_url())


@contextmanager
def get_conn(autocommit=False):
    database_url = load_database_url()
    if not database_url:
        raise RuntimeError('DATABASE_URL PostgreSQL belum dikonfigurasi')
    conn = psycopg.connect(database_url.replace('postgresql+psycopg://', 'postgresql://'), row_factory=dict_row)
    try:
        conn.autocommit = autocommit
        yield conn
    finally:
        conn.close()


_def_headers_cache = {}


def ensure_schema() -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
        conn.commit()


def parse_dt(value):
    if isinstance(value, datetime):
        return value
    text = str(value or '').strip()
    if not text:
        return None
    for fmt in ('%d-%m-%Y %H:%M:%S', '%d-%m-%Y %H:%M', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def format_dt(value):
    dt_value = parse_dt(value)
    return dt_value.strftime(DATETIME_FORMAT) if dt_value else ''


def _incident_row_from_db(row):
    return {
        'ticket_code': row.get('ticket_code', ''),
        'created_at': format_dt(row.get('created_at')),
        'lokasi': row.get('lokasi', '') or '',
        'masalah': row.get('masalah', '') or '',
        'pelapor': row.get('pelapor', '') or '',
        'status': row.get('status', '') or '',
        'durasi': row.get('durasi', '') or '',
        'bukti_awal': row.get('bukti_awal', '') or '',
        'update_terakhir': format_dt(row.get('update_terakhir')),
        'alias': row.get('alias', ''),
        'ditangani_oleh': row.get('ditangani_oleh', '') or '',
        'alasan_pending': row.get('alasan_pending', '') or '',
        'catatan_terakhir': row.get('catatan_terakhir', '') or '',
        'bukti_resolve': row.get('bukti_resolve', '') or '',
        'folder_bukti': row.get('folder_bukti', '') or '',
        'archived_at': format_dt(row.get('archived_at')),
        'source_sheet': row.get('source_sheet', '') or '',
        'resolved_at': format_dt(row.get('resolved_at')),
        'closed_at': format_dt(row.get('closed_at')),
    }


def _history_row_from_db(row):
    return {
        'update_id': row.get('update_id', '') or '',
        'ticket_code': row.get('ticket_code', '') or '',
        'alias': row.get('alias', '') or '',
        'update_time': format_dt(row.get('update_time')),
        'action': row.get('action', '') or '',
        'status_before': row.get('status_before', '') or '',
        'status_after': row.get('status_after', '') or '',
        'ditangani_oleh': row.get('ditangani_oleh', '') or '',
        'alasan_pending': row.get('alasan_pending', '') or '',
        'catatan_terakhir': row.get('catatan_terakhir', '') or '',
        'catatan': row.get('catatan', '') or '',
        'raw_message': row.get('raw_message', '') or '',
        'bukti_awal': row.get('bukti_awal', '') or '',
        'bukti_resolve': row.get('bukti_resolve', '') or '',
        'folder_bukti': row.get('folder_bukti', '') or '',
        'bukti_status': row.get('bukti_status', '') or '',
        'bukti_baru': row.get('bukti_baru', '') or '',
    }


def fetch_incident_by_code(ticket_code: str):
    ensure_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM incidents WHERE UPPER(ticket_code)=UPPER(%s) LIMIT 1", (ticket_code,))
            row = cur.fetchone()
    return _incident_row_from_db(row) if row else None


def fetch_all_incidents():
    ensure_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM incidents ORDER BY created_at ASC, id ASC")
            rows = cur.fetchall()
    return [_incident_row_from_db(row) for row in rows]


def get_all_records(include_archive=False):
    records = fetch_all_incidents()
    active_records = [row for row in records if str(row.get('status', '')).upper() in ACTIVE_STATUSES]
    archive_records = [row for row in records if str(row.get('status', '')).upper() in TERMINAL_STATUSES] if include_archive else []
    return active_records, archive_records


def get_history_records(ticket_code=None):
    ensure_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            if ticket_code:
                cur.execute(
                    "SELECT * FROM incident_history WHERE UPPER(ticket_code)=UPPER(%s) ORDER BY update_time ASC, id ASC",
                    (ticket_code,),
                )
            else:
                cur.execute("SELECT * FROM incident_history ORDER BY update_time ASC, id ASC")
            rows = cur.fetchall()
    return [_history_row_from_db(row) for row in rows]


def generate_ticket_code(category='NET'):
    ensure_schema()
    prefix = str(category or 'INC').upper()
    today = datetime.now().strftime('%Y%m%d')
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(MAX(CAST(split_part(ticket_code, '-', 3) AS INTEGER)), 0)
                FROM incidents
                WHERE split_part(ticket_code, '-', 1) = %s
                  AND split_part(ticket_code, '-', 2) = %s
                """,
                (prefix, today),
            )
            max_daily_num = cur.fetchone()['coalesce']
            cur.execute("SELECT COALESCE(MAX(alias), 0) AS max_alias FROM incidents")
            max_alias_num = cur.fetchone()['max_alias']
    new_daily_num = int(max_daily_num or 0) + 1
    new_alias_num = int(max_alias_num or 0) + 1
    return f'{prefix}-{today}-{str(new_daily_num).zfill(3)}', new_alias_num


def upsert_incident_record(record: dict):
    ensure_schema()
    normalized = dict(record)
    status = str(normalized.get('status', 'OPEN') or 'OPEN').upper()
    source_sheet = 'incident_log' if status in ACTIVE_STATUSES else 'incident_archive'
    resolved_at = normalized.get('resolved_at') or (normalized.get('update_terakhir') if status == 'RESOLVED' else None)
    closed_at = normalized.get('closed_at') or (normalized.get('update_terakhir') if status == 'CLOSED' else None)
    archived_at = normalized.get('archived_at') or (normalized.get('update_terakhir') if status in TERMINAL_STATUSES else None)
    values = {
        'ticket_code': str(normalized.get('ticket_code', '')).strip().upper(),
        'alias': int(normalized.get('alias') or 0),
        'created_at': parse_dt(normalized.get('created_at')) or datetime.now(),
        'lokasi': str(normalized.get('lokasi', '') or '').strip(),
        'masalah': str(normalized.get('masalah', '') or '').strip(),
        'pelapor': str(normalized.get('pelapor', '') or '').strip() or 'Unknown',
        'status': status,
        'durasi': str(normalized.get('durasi', '') or '').strip() or None,
        'bukti_awal': str(normalized.get('bukti_awal', '') or '').strip() or None,
        'update_terakhir': parse_dt(normalized.get('update_terakhir')) or datetime.now(),
        'ditangani_oleh': str(normalized.get('ditangani_oleh', '') or '').strip() or None,
        'alasan_pending': str(normalized.get('alasan_pending', '') or '') or None,
        'catatan_terakhir': str(normalized.get('catatan_terakhir', '') or '') or None,
        'bukti_resolve': str(normalized.get('bukti_resolve', '') or '').strip() or None,
        'folder_bukti': str(normalized.get('folder_bukti', '') or '').strip() or None,
        'archived_at': parse_dt(archived_at),
        'source_sheet': str(normalized.get('source_sheet', '') or source_sheet).strip() or source_sheet,
        'resolved_at': parse_dt(resolved_at),
        'closed_at': parse_dt(closed_at),
    }
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO incidents (
                    ticket_code, alias, created_at, lokasi, masalah, pelapor, status, durasi,
                    bukti_awal, update_terakhir, ditangani_oleh, alasan_pending, catatan_terakhir,
                    bukti_resolve, folder_bukti, archived_at, source_sheet, resolved_at, closed_at, updated_ts
                ) VALUES (
                    %(ticket_code)s, %(alias)s, %(created_at)s, %(lokasi)s, %(masalah)s, %(pelapor)s, %(status)s, %(durasi)s,
                    %(bukti_awal)s, %(update_terakhir)s, %(ditangani_oleh)s, %(alasan_pending)s, %(catatan_terakhir)s,
                    %(bukti_resolve)s, %(folder_bukti)s, %(archived_at)s, %(source_sheet)s, %(resolved_at)s, %(closed_at)s, NOW()
                )
                ON CONFLICT (ticket_code) DO UPDATE SET
                    alias = EXCLUDED.alias,
                    created_at = EXCLUDED.created_at,
                    lokasi = EXCLUDED.lokasi,
                    masalah = EXCLUDED.masalah,
                    pelapor = EXCLUDED.pelapor,
                    status = EXCLUDED.status,
                    durasi = EXCLUDED.durasi,
                    bukti_awal = EXCLUDED.bukti_awal,
                    update_terakhir = EXCLUDED.update_terakhir,
                    ditangani_oleh = EXCLUDED.ditangani_oleh,
                    alasan_pending = EXCLUDED.alasan_pending,
                    catatan_terakhir = EXCLUDED.catatan_terakhir,
                    bukti_resolve = EXCLUDED.bukti_resolve,
                    folder_bukti = EXCLUDED.folder_bukti,
                    archived_at = EXCLUDED.archived_at,
                    source_sheet = EXCLUDED.source_sheet,
                    resolved_at = EXCLUDED.resolved_at,
                    closed_at = EXCLUDED.closed_at,
                    updated_ts = NOW()
                """,
                values,
            )
        conn.commit()


def append_history_row(row: dict):
    ensure_schema()
    payload = {
        'update_id': str(row.get('update_id', '') or '').strip(),
        'ticket_code': str(row.get('ticket_code', '') or '').strip().upper(),
        'alias': int(row.get('alias') or 0) if str(row.get('alias', '')).strip() else None,
        'update_time': parse_dt(row.get('update_time')) or datetime.now(),
        'action': str(row.get('action', '') or '').strip() or None,
        'status_before': str(row.get('status_before', '') or '').strip().upper() or None,
        'status_after': str(row.get('status_after', '') or '').strip().upper() or None,
        'ditangani_oleh': str(row.get('ditangani_oleh', '') or '').strip() or None,
        'alasan_pending': str(row.get('alasan_pending', '') or '') or None,
        'catatan_terakhir': str(row.get('catatan_terakhir', '') or '') or None,
        'catatan': str(row.get('catatan', '') or '') or None,
        'raw_message': str(row.get('raw_message', '') or '').strip() or None,
        'bukti_awal': str(row.get('bukti_awal', '') or '').strip() or None,
        'bukti_resolve': str(row.get('bukti_resolve', '') or '').strip() or None,
        'folder_bukti': str(row.get('folder_bukti', '') or '').strip() or None,
        'bukti_status': str(row.get('bukti_status', '') or '').strip() or None,
        'bukti_baru': str(row.get('bukti_baru', '') or '').strip() or None,
    }
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO incident_history (
                    update_id, ticket_code, alias, update_time, action, status_before, status_after,
                    ditangani_oleh, alasan_pending, catatan_terakhir, catatan, raw_message,
                    bukti_awal, bukti_resolve, folder_bukti, bukti_status, bukti_baru
                ) VALUES (
                    %(update_id)s, %(ticket_code)s, %(alias)s, %(update_time)s, %(action)s, %(status_before)s, %(status_after)s,
                    %(ditangani_oleh)s, %(alasan_pending)s, %(catatan_terakhir)s, %(catatan)s, %(raw_message)s,
                    %(bukti_awal)s, %(bukti_resolve)s, %(folder_bukti)s, %(bukti_status)s, %(bukti_baru)s
                )
                ON CONFLICT (update_id) DO UPDATE SET
                    ticket_code = EXCLUDED.ticket_code,
                    alias = EXCLUDED.alias,
                    update_time = EXCLUDED.update_time,
                    action = EXCLUDED.action,
                    status_before = EXCLUDED.status_before,
                    status_after = EXCLUDED.status_after,
                    ditangani_oleh = EXCLUDED.ditangani_oleh,
                    alasan_pending = EXCLUDED.alasan_pending,
                    catatan_terakhir = EXCLUDED.catatan_terakhir,
                    catatan = EXCLUDED.catatan,
                    raw_message = EXCLUDED.raw_message,
                    bukti_awal = EXCLUDED.bukti_awal,
                    bukti_resolve = EXCLUDED.bukti_resolve,
                    folder_bukti = EXCLUDED.folder_bukti,
                    bukti_status = EXCLUDED.bukti_status,
                    bukti_baru = EXCLUDED.bukti_baru
                """,
                payload,
            )
        conn.commit()


def insert_attachment(ticket_code, file_url, kind, status_label='', history_update_id=None, source_filename=None):
    clean_url = str(file_url or '').strip()
    if not clean_url:
        return
    ensure_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO incident_attachments (ticket_code, history_update_id, kind, status_label, file_url, source_filename)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    str(ticket_code or '').strip().upper(),
                    str(history_update_id or '').strip() or None,
                    str(kind or '').strip() or 'bukti',
                    str(status_label or '').strip().upper() or None,
                    clean_url,
                    str(source_filename or '').strip() or None,
                ),
            )
        conn.commit()


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


class DBWorksheet:
    def __init__(self, sheet_name, headers):
        self.sheet_name = sheet_name
        self.headers = list(headers)
        self.col_count = len(headers)
        self._last_index_map = {}

    def add_cols(self, count):
        self.col_count += int(count or 0)

    def row_values(self, row_index):
        return list(self.headers) if int(row_index) == 1 else []

    def _records(self):
        if self.sheet_name == 'incident_history':
            rows = get_history_records()
        elif self.sheet_name == 'incident_archive':
            _, rows = get_all_records(include_archive=True)
        else:
            rows, _ = get_all_records(include_archive=True)
        self._last_index_map = {idx: row.get('ticket_code') for idx, row in enumerate(rows, 2)}
        return rows

    def get_all_records(self):
        return self._records()

    def append_row(self, row_values):
        payload = {header: row_values[idx] if idx < len(row_values) else '' for idx, header in enumerate(self.headers)}
        if self.sheet_name == 'incident_history':
            append_history_row(payload)
            return
        payload['source_sheet'] = self.sheet_name
        upsert_incident_record(payload)

    def update(self, rows, cell_range):
        row_values = (rows or [[]])[0]
        payload = {header: row_values[idx] if idx < len(row_values) else '' for idx, header in enumerate(self.headers)}
        if self.sheet_name == 'incident_history':
            append_history_row(payload)
            return
        payload['source_sheet'] = self.sheet_name
        upsert_incident_record(payload)

    def update_cell(self, row_idx, col_idx, value):
        if self.sheet_name == 'incident_history':
            return
        records = self._records()
        record = None
        for idx, row in enumerate(records, 2):
            if idx == int(row_idx):
                record = dict(row)
                break
        if record is None:
            return
        header = self.headers[int(col_idx) - 1]
        record[header] = value
        record['source_sheet'] = self.sheet_name
        upsert_incident_record(record)

    def delete_rows(self, row_idx):
        ticket_code = self._last_index_map.get(int(row_idx))
        if not ticket_code:
            return
        current = fetch_incident_by_code(ticket_code)
        if not current:
            return
        status = str(current.get('status', '')).upper()
        if self.sheet_name == 'incident_log' and status in TERMINAL_STATUSES:
            return
        if self.sheet_name == 'incident_archive' and status in ACTIVE_STATUSES:
            return
        ensure_schema()
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM incidents WHERE UPPER(ticket_code)=UPPER(%s)", (ticket_code,))
            conn.commit()


def get_db_sheet(sheet_name, headers):
    ensure_schema()
    return DBWorksheet(sheet_name, headers)


def purge_deleted_ticket(ticket_code):
    normalized = str(ticket_code or '').strip().upper()
    if not normalized:
        return
    ensure_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM incident_attachments WHERE UPPER(ticket_code)=UPPER(%s)", (normalized,))
            cur.execute("DELETE FROM incident_history WHERE UPPER(ticket_code)=UPPER(%s)", (normalized,))
            cur.execute("DELETE FROM incidents WHERE UPPER(ticket_code)=UPPER(%s)", (normalized,))
        conn.commit()
