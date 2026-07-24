from __future__ import annotations

import fcntl
import os
import shutil
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from flask import current_app
from google.auth.exceptions import RefreshError, TransportError
from googleapiclient.errors import HttpError
from sqlalchemy.exc import OperationalError

from extensions import db
from models import AutoCertificateEvent, AutoCertificateItem, AutoCertificateRun
from services.certificate_photos import PHOTO_PLACEHOLDER, prepare_certificate_photo
from services.google_drive import DriveConfigurationError, upload_pdf_with_config
from services.google_sheets import ParsedSheet, SheetConfigurationError, fetch_form_rows
from services.pptx_generator import build_pdf_safe_template, convert_pptx_to_pdf_with_soffice, replace_placeholders
from services.storage import ensure_dir, remove_dir, remove_files, slugify_filename

_SYNC_LOCKS: dict[str, threading.Lock] = {}
RETRYABLE_SYNC_EXCEPTIONS = (TransportError,)
_DB_SYNC_LOCK_PATH = Path(__file__).resolve().parent.parent / 'instance' / 'auto_certificate_sync.lock'


class AutoCertificateError(RuntimeError):
    pass



def _normalize_certificate_name(value: str | None) -> str:
    text = ' '.join((value or '').split())
    return text.upper()


@dataclass
class EventSyncSummary:
    found_rows: int
    queued_rows: int
    processed_rows: int
    success_rows: int
    failed_rows: int
    message: str


def _event_lock(event_uuid: str) -> threading.Lock:
    if event_uuid not in _SYNC_LOCKS:
        _SYNC_LOCKS[event_uuid] = threading.Lock()
    return _SYNC_LOCKS[event_uuid]


class _GlobalSyncFileLock:
    def __init__(self, path: Path):
        self.path = path
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = open(self.path, 'a+')
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.handle.close()
            self.handle = None
            raise AutoCertificateError('Sinkronisasi global sedang berjalan. Silakan tunggu proses aktif selesai.') from exc
        self.handle.seek(0)
        self.handle.truncate()
        self.handle.write(str(os.getpid()))
        self.handle.flush()
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.handle is None:
            return
        try:
            self.handle.seek(0)
            self.handle.truncate()
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None


def _normalize_header_key(value: str) -> str:
    import re

    return re.sub(r'[^a-z0-9]+', '', (value or '').strip().lower())


HEADER_ALIASES = {
    'name': ['namalengkap', 'nama', 'peserta', 'namapeserta'],
    'email': ['email', 'alamatemail', 'surel'],
    'institution': ['asalinstansi', 'instansi', 'unitkerja', 'satker'],
    'phone': ['nomorwa', 'wa', 'nomorwa', 'nohp', 'noh p', 'telepon', 'nohpwa'],
    'timestamp': ['timestamp', 'stempelwaktu', 'waktu', 'tanggalwaktu'],
    'photo': ['foto', 'photo', 'pasfoto', 'uploadfoto', 'unggahfoto', 'filefoto', 'linkfoto', 'fotopeserta'],
}


def detect_form_columns(headers: list[str]) -> dict[str, str | None]:
    normalized_map = {_normalize_header_key(header): header for header in headers}
    result: dict[str, str | None] = {}
    for key, aliases in HEADER_ALIASES.items():
        result[key] = next((normalized_map[alias] for alias in aliases if alias in normalized_map), None)
    return result


def validate_event_configuration(parsed: ParsedSheet, template_path: str) -> dict:
    columns = detect_form_columns(parsed.headers)
    if not columns.get('name'):
        raise AutoCertificateError('Kolom Nama Lengkap tidak terdeteksi pada Google Form Response.')

    preview_root = ensure_dir(Path(template_path).parent / '_automation_validation')
    safe_template_path = preview_root / 'template-safe-check.pptx'
    build_pdf_safe_template(
        template_path,
        str(safe_template_path),
        placeholders=['{{nama}}', PHOTO_PLACEHOLDER],
        working_dir=str(preview_root / 'build'),
        soffice_path=current_app.config.get('SOFFICE_PATH', ''),
    )
    sample_row = next((row for row in parsed.rows if (row.get(columns['name'] or '') or '').strip()), None)
    return {
        'columns': columns,
        'sample_name': sample_row.get(columns['name'] or '', '') if sample_row else '',
        'total_rows': len(parsed.rows),
        'has_sample_row': sample_row is not None,
    }


def _participant_key(event: AutoCertificateEvent, row: dict) -> str:
    ts_value = (row.get(event.timestamp_column or '') or '').strip()
    email_value = (row.get(event.email_column or '') or '').strip().lower()
    if ts_value and email_value:
        return f'{ts_value}|{email_value}'
    if ts_value:
        return f'{ts_value}|row-{row.get("_row_number", 0)}'
    if email_value:
        return f'{email_value}|row-{row.get("_row_number", 0)}'
    return f'row-{row.get("_row_number", 0)}|{(row.get(event.name_column or "") or "").strip().lower()}'


def _recalculate_event_counters(event: AutoCertificateEvent):
    items = AutoCertificateItem.query.filter_by(event_id=event.id).all()
    event.total_responses = len(items)
    event.pending_responses = sum(1 for item in items if item.status == 'pending')
    event.processing_responses = sum(1 for item in items if item.status == 'processing')
    event.success_responses = sum(1 for item in items if item.status == 'success')
    event.failed_responses = sum(1 for item in items if item.status == 'failed')


def _processing_timeout_minutes(event: AutoCertificateEvent) -> int:
    interval = max(int(event.polling_interval_minutes or 5), 1)
    return max(interval * 2, 10)


def _recover_stuck_processing_items(event: AutoCertificateEvent) -> int:
    cutoff = datetime.utcnow() - timedelta(minutes=_processing_timeout_minutes(event))
    stuck_items = (
        AutoCertificateItem.query
        .filter_by(event_id=event.id, status='processing')
        .filter(AutoCertificateItem.processed_at.is_(None))
        .filter(AutoCertificateItem.drive_file_id.is_(None))
        .filter(AutoCertificateItem.updated_at <= cutoff)
        .all()
    )
    recovered = 0
    for item in stuck_items:
        item.status = 'pending'
        item.error_message = 'Antrean dipulihkan otomatis setelah proses sebelumnya terputus.'
        item.processed_at = None
        recovered += 1
    if recovered:
        _recalculate_event_counters(event)
        db.session.commit()
    return recovered


def _mark_item_for_retry(item: AutoCertificateItem, message: str | None = None):
    item.status = 'pending'
    item.error_message = message or 'Akan dicoba ulang otomatis pada sinkronisasi berikutnya.'
    item.processed_at = None
    item.output_filename = None
    item.drive_file_id = None
    item.drive_link = None


def _retryable_http_error(exc: HttpError) -> bool:
    status_code = getattr(getattr(exc, 'resp', None), 'status', None)
    return status_code in {408, 409, 425, 429, 500, 502, 503, 504}


def _is_retryable_generation_error(exc: Exception) -> bool:
    if isinstance(exc, RETRYABLE_SYNC_EXCEPTIONS):
        return True
    if isinstance(exc, HttpError):
        return _retryable_http_error(exc)
    return False


def _prepare_event_template(event: AutoCertificateEvent) -> Path:
    event_root = ensure_dir(Path(current_app.config['AUTO_EVENT_DIR']) / event.event_uuid)
    template_original = event_root / 'template-original.pptx'
    template_safe = event_root / 'template-safe.pptx'
    if not template_original.exists():
        raise AutoCertificateError('Template kegiatan tidak ditemukan pada server.')
    if not template_safe.exists():
        build_pdf_safe_template(
            str(template_original),
            str(template_safe),
            placeholders=['{{nama}}', PHOTO_PLACEHOLDER],
            working_dir=str(event_root / '_safe_build'),
            soffice_path=current_app.config.get('SOFFICE_PATH', ''),
            cleanup_working_dir=True,
        )
    return template_safe


def _generate_item_certificate(event: AutoCertificateEvent, item: AutoCertificateItem, template_safe_path: str) -> dict:
    runtime_root = ensure_dir(Path(current_app.config['RUNTIME_DIR']) / 'auto-events' / event.event_uuid)
    normalized_name = _normalize_certificate_name(item.participant_name)
    base_name = slugify_filename(f'Sertifikat - {normalized_name}', default=f'sertifikat-{item.source_row_number}')
    if item.submitted_at:
        safe_stamp = ''.join(ch for ch in item.submitted_at if ch.isdigit())[:14]
        if safe_stamp:
            base_name = slugify_filename(f'{base_name} - {safe_stamp}', default=base_name)
    pptx_path = runtime_root / f'{uuid4().hex}-{base_name}.pptx'
    pdf_path = runtime_root / f'{pptx_path.stem}.pdf'
    photo_path = None
    try:
        image_replacements = {}
        photo_path = prepare_certificate_photo(
            item.photo_url,
            runtime_root,
            google_token_path=current_app.config['GOOGLE_TOKEN_PATH'],
            drive_scopes=list(current_app.config['DRIVE_SCOPES']),
            row_number=item.source_row_number,
            use_cached_service=True,
        ) if item.photo_url else None
        if photo_path:
            image_replacements[PHOTO_PLACEHOLDER] = photo_path
        replace_placeholders(
            template_safe_path,
            str(pptx_path),
            {'{{nama}}': normalized_name},
            image_replacements=image_replacements,
        )
        actual_pdf = convert_pptx_to_pdf_with_soffice(str(pptx_path), str(runtime_root), current_app.config.get('SOFFICE_PATH', ''))
        filename = f'{base_name}.pdf'
        upload_result = upload_pdf_with_config(
            actual_pdf,
            event.drive_folder_id,
            filename,
            current_app.config['GOOGLE_TOKEN_PATH'],
            list(current_app.config['DRIVE_SCOPES']),
            use_cached_service=True,
        )
        return {
            'ok': True,
            'filename': filename,
            'drive_file_id': upload_result.get('id'),
            'drive_link': upload_result.get('webViewLink'),
            'message': 'Upload berhasil.',
        }
    finally:
        remove_files([pptx_path, pdf_path, photo_path])
        remove_dir(runtime_root / '_soffice_profiles')


def sync_event(event_id: int) -> EventSyncSummary:
    event = db.session.get(AutoCertificateEvent, event_id)
    if event is None:
        raise AutoCertificateError('Kegiatan automation tidak ditemukan.')
    lock = _event_lock(event.event_uuid)
    if not lock.acquire(blocking=False):
        raise AutoCertificateError('Sinkronisasi kegiatan sedang berjalan. Silakan tunggu proses yang aktif selesai.')
    run = None
    try:
        with _GlobalSyncFileLock(_DB_SYNC_LOCK_PATH):
            event = db.session.get(AutoCertificateEvent, event_id)
            if event is None:
                raise AutoCertificateError('Kegiatan automation tidak ditemukan.')

            stale_runs = AutoCertificateRun.query.filter_by(event_id=event.id, status='running').all()
            for stale_run in stale_runs:
                stale_run.finished_at = datetime.utcnow()
                stale_run.status = 'aborted'
                stale_run.message = 'Run sebelumnya ditutup otomatis karena ada proses sinkronisasi baru yang mengambil alih.'
            if stale_runs:
                db.session.commit()

            event.last_run_started_at = datetime.utcnow()
            event.status = 'active' if event.enabled else event.status
            run = AutoCertificateRun(event_id=event.id, status='running')
            db.session.add(run)
            db.session.commit()

            recovered_rows = _recover_stuck_processing_items(event)

            parsed = fetch_form_rows(event.spreadsheet_id, worksheet_name=event.worksheet_name)
            event.spreadsheet_title = parsed.spreadsheet_title
            event.worksheet_name = parsed.selected_sheet
            if not event.photo_column:
                event.photo_column = detect_form_columns(parsed.headers).get('photo')
            run.found_rows = len(parsed.rows)

            existing = {item.participant_key: item for item in AutoCertificateItem.query.filter_by(event_id=event.id).all()}
            queued_rows = 0
            for row in parsed.rows:
                key = _participant_key(event, row)
                if key in existing:
                    item = existing[key]
                    if event.photo_column and not item.photo_url:
                        item.photo_url = (row.get(event.photo_column or '') or '').strip() or None
                    continue
                item = AutoCertificateItem(
                    event_id=event.id,
                    participant_key=key,
                    source_row_number=row.get('_row_number', 0),
                    submitted_at=(row.get(event.timestamp_column or '') or '').strip() or None,
                    participant_name=(row.get(event.name_column or '') or '').strip() or None,
                    institution_name=(row.get(event.institution_column or '') or '').strip() or None,
                    email=(row.get(event.email_column or '') or '').strip() or None,
                    phone=(row.get(event.phone_column or '') or '').strip() or None,
                    photo_url=(row.get(event.photo_column or '') or '').strip() or None,
                    status='pending',
                )
                db.session.add(item)
                queued_rows += 1
            db.session.commit()
            run.queued_rows = queued_rows

            event_root = ensure_dir(Path(current_app.config['AUTO_EVENT_DIR']) / event.event_uuid)
            template_safe_path = _prepare_event_template(event)

            pending_items = AutoCertificateItem.query.filter_by(event_id=event.id, status='pending').order_by(AutoCertificateItem.id.asc()).all()

            success_rows = 0
            failed_rows = 0
            for item in pending_items:
                try:
                    item.status = 'processing'
                    item.error_message = None
                    item.processed_at = None
                    db.session.commit()

                    result = _generate_item_certificate(event, item, str(template_safe_path))
                    item.status = 'success'
                    item.output_filename = result.get('filename')
                    item.drive_file_id = result.get('drive_file_id')
                    item.drive_link = result.get('drive_link')
                    item.error_message = None
                    item.processed_at = datetime.utcnow()
                    success_rows += 1
                except Exception as exc:
                    if _is_retryable_generation_error(exc):
                        _mark_item_for_retry(item, 'Koneksi internet/Google sempat terputus. Peserta dikembalikan ke antrean untuk dicoba ulang otomatis.')
                        db.session.commit()
                        raise AutoCertificateError('Koneksi internet/Google terputus di tengah proses. Sisa antrean akan dicoba ulang otomatis pada sinkronisasi berikutnya.') from exc
                    item.status = 'failed'
                    item.error_message = str(exc)
                    item.processed_at = datetime.utcnow()
                    failed_rows += 1
                db.session.commit()

            _recalculate_event_counters(event)
            event.last_synced_at = datetime.utcnow()
            event.last_run_finished_at = datetime.utcnow()
            event.next_run_at = datetime.utcnow() + timedelta(minutes=event.polling_interval_minutes or 5)
            event.last_error = None
            event.status = 'active' if event.enabled else 'inactive'

            run.finished_at = datetime.utcnow()
            run.status = 'completed' if failed_rows == 0 else 'completed_with_errors'
            run.processed_rows = len(pending_items)
            run.success_rows = success_rows
            run.failed_rows = failed_rows
            recovery_note = f', dipulihkan: {recovered_rows}' if recovered_rows else ''
            run.message = f'Sinkron selesai. Baru: {queued_rows}, sukses: {success_rows}, gagal: {failed_rows}{recovery_note}.'
            db.session.commit()
            return EventSyncSummary(
                found_rows=len(parsed.rows),
                queued_rows=queued_rows,
                processed_rows=len(pending_items),
                success_rows=success_rows,
                failed_rows=failed_rows,
                message=run.message,
            )
    except OperationalError as exc:
        db.session.rollback()
        if 'database is locked' in str(exc).lower():
            raise AutoCertificateError('Database sedang dipakai proses sinkronisasi lain. Silakan tunggu sebentar lalu coba lagi.') from exc
        raise AutoCertificateError(str(exc)) from exc
    except (SheetConfigurationError, DriveConfigurationError, RefreshError, HttpError, AutoCertificateError, RuntimeError, TransportError) as exc:
        db.session.rollback()
        event = db.session.get(AutoCertificateEvent, event_id)
        if event is not None:
            event.status = 'error'
            if isinstance(exc, TransportError):
                event.last_error = 'Server tidak dapat terhubung ke layanan Google saat proses sinkronisasi.'
            else:
                event.last_error = str(exc)
            event.last_run_finished_at = datetime.utcnow()
            event.next_run_at = datetime.utcnow() + timedelta(minutes=event.polling_interval_minutes or 5)
            _recalculate_event_counters(event)
        if run is None:
            run = AutoCertificateRun.query.filter_by(event_id=event_id).order_by(AutoCertificateRun.id.desc()).first()
        if run and run.status == 'running':
            run.finished_at = datetime.utcnow()
            run.status = 'failed'
            run.message = str(exc)
        db.session.commit()
        raise AutoCertificateError(str(exc)) from exc
    finally:
        lock.release()


def retry_failed_items(event_id: int) -> int:
    event = db.session.get(AutoCertificateEvent, event_id)
    if event is None:
        raise AutoCertificateError('Kegiatan automation tidak ditemukan.')
    items = AutoCertificateItem.query.filter_by(event_id=event.id, status='failed').all()
    count = 0
    for item in items:
        item.status = 'pending'
        item.error_message = None
        item.processed_at = None
        count += 1
    _recalculate_event_counters(event)
    db.session.commit()
    return count


def reset_processing_items(event_id: int, *, only_stale: bool = False) -> int:
    event = db.session.get(AutoCertificateEvent, event_id)
    if event is None:
        raise AutoCertificateError('Kegiatan automation tidak ditemukan.')
    query = AutoCertificateItem.query.filter_by(event_id=event.id, status='processing')
    if only_stale:
        cutoff = datetime.utcnow() - timedelta(minutes=_processing_timeout_minutes(event))
        query = (
            query
            .filter(AutoCertificateItem.processed_at.is_(None))
            .filter(AutoCertificateItem.drive_file_id.is_(None))
            .filter(AutoCertificateItem.updated_at <= cutoff)
        )
    items = query.all()
    count = 0
    for item in items:
        _mark_item_for_retry(item, 'Antrean direset manual untuk diproses ulang.')
        count += 1
    _recalculate_event_counters(event)
    db.session.commit()
    return count
