from __future__ import annotations

import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import login_required
from google.auth.exceptions import RefreshError, TransportError
from googleapiclient.errors import HttpError

from extensions import db
from models import AutoCertificateEvent, AutoCertificateItem, AutoCertificateRun, GenerationJob, JobRowResult
from services.certificate_photos import PHOTO_PLACEHOLDER, detect_photo_column, prepare_certificate_photo
from services.auto_certificate import AutoCertificateError, reset_processing_items, retry_failed_items, sync_event, validate_event_configuration
from services.excel_parser import WorkbookValidationError, load_participants
from services.google_drive import DriveConfigurationError, get_folder_metadata, probe_folder_upload_with_config
from services.google_sheets import SheetConfigurationError, fetch_form_rows, normalize_spreadsheet_input
from services.job_runner import start_generation
from services.pptx_generator import build_pdf_safe_template, build_text_replacements_from_row, convert_document_with_soffice, expand_placeholder_tokens, placeholder_tokens_from_headers, replace_placeholders
from services.storage import ensure_dir, remove_files, slugify_filename

certificates_bp = Blueprint('certificates', __name__, url_prefix='/certificates')


SAMPLE_FILES = {
    'template-pptx': {
        'filename': 'template-sertifikat-contoh.pptx',
        'download_name': 'template-sertifikat-contoh.pptx',
    },
    'peserta-xlsx': {
        'filename': 'peserta-contoh.xlsx',
        'download_name': 'peserta-contoh.xlsx',
    },
}

EXPECTED_SAMPLE_HEADERS = ('Nama', 'Instansi')


STATUS_LABELS = {
    'draft': 'Draft',
    'validated': 'Siap Generate',
    'running': 'Sedang Berjalan',
    'paused': 'Pause',
    'completed': 'Selesai',
    'completed_with_errors': 'Selesai Dengan Error',
    'failed': 'Gagal',
    'cancelled': 'Stop',
}


START_INFO_MESSAGES = {
    'running': ('Proses generate sedang berjalan. Status akan diperbarui otomatis pada halaman ini.', 'info'),
    'pause_requested': ('Permintaan pause sudah dicatat. Sistem akan menjeda proses setelah pekerjaan aktif selesai.', 'warning'),
    'stop_requested': ('Permintaan stop sudah dicatat. Sistem akan menghentikan proses setelah pekerjaan aktif selesai.', 'danger'),
    'paused': ('Proses sedang dijeda. Silakan lanjutkan proses untuk meneruskan batch dari progres terakhir.', 'warning'),
    'cancelled': ('Proses generate dihentikan oleh operator.', 'danger'),
    'completed': ('Proses generate telah selesai. Hasil siap ditinjau pada folder Google Drive.', 'success'),
    'completed_with_errors': ('Proses generate telah selesai dengan beberapa error. Silakan tinjau ringkasan error yang tersedia.', 'warning'),
    'failed': ('Proses generate gagal diselesaikan. Silakan tinjau detail error yang tersedia.', 'danger'),
}


def _allowed(filename: str, allowed: set[str]) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed


def _save_upload(file_storage, subdir: str, suffix: str) -> str:
    folder = ensure_dir(Path(current_app.config['JOB_DIR']) / subdir)
    filename = slugify_filename(Path(file_storage.filename or f'upload.{suffix}').stem, default='upload')
    path = folder / f'{uuid4().hex}-{filename}.{suffix}'
    file_storage.save(path)
    return str(path)


def _display_status(status: str) -> str:
    return STATUS_LABELS.get(status, status.replace('_', ' ').title())


def _normalize_drive_folder_input(raw_value: str) -> str:
    value = (raw_value or '').strip()
    if not value:
        raise DriveConfigurationError('Folder Google Drive wajib diisi.')
    if 'drive.google.com' not in value:
        return value

    folder_match = re.search(r'/folders/([a-zA-Z0-9_-]+)', value)
    if folder_match:
        return folder_match.group(1)

    id_match = re.search(r'[?&]id=([a-zA-Z0-9_-]+)', value)
    if id_match:
        return id_match.group(1)

    raise DriveConfigurationError('Link Google Drive tidak dikenali. Gunakan link folder atau Folder ID yang valid.')


def _friendly_google_configuration_message(message: str) -> str:
    text = (message or '').strip()
    if 'spreadsheets.readonly' in text or 'Token Google Sheets' in text:
        return (
            'Token Google di server belum memiliki izin Google Sheets yang dibutuhkan '
            '(spreadsheets.readonly). Saat ini token perlu diperbarui agar memuat '
            'akses Google Drive dan Google Sheets sebelum validasi atau generate dijalankan.'
        )
    if 'Token Google tidak ditemukan' in text:
        return (
            'Token Google pada server belum tersedia. Silakan pasang atau perbarui token '
            'Google OAuth terlebih dahulu sebelum validasi atau generate dijalankan.'
        )
    if 'Autentikasi Google Drive pada server sudah tidak berlaku' in text or 'Token Google Drive' in text:
        return (
            'Token Google di server bermasalah untuk akses Google Drive. Silakan perbarui '
            'token Google OAuth terlebih dahulu sebelum validasi atau generate dijalankan.'
        )
    return text


def _google_validation_status(message: str) -> tuple[str, str]:
    text = (message or '').strip()
    if any(keyword in text for keyword in ['Token Google', 'Autentikasi Google Drive', 'spreadsheets.readonly']):
        return 'pending', 'Token Google perlu diperbarui'
    return 'invalid', 'Link/ID tidak valid'


def _invalid_drive_validation(input_value: str, folder_id: str, message: str) -> dict:
    status, label = _google_validation_status(message)
    return {
        'status': status,
        'label': label,
        'message': _friendly_google_configuration_message(message),
        'input_value': input_value,
        'folder_id': folder_id,
        'folder_name': '',
    }


def _build_drive_validation(input_value: str, folder_id: str) -> dict:
    folder_name = folder_id
    metadata_warning = ''

    try:
        folder_meta = get_folder_metadata(folder_id)
        folder_name = folder_meta.get('name') or folder_id
        return {
            'status': 'valid',
            'label': 'Link/ID valid',
            'message': 'Folder Google Drive ditemukan dan siap digunakan.',
            'input_value': input_value,
            'folder_id': folder_id,
            'folder_name': folder_name,
        }
    except RefreshError as exc:
        raise DriveConfigurationError(
            'Token Google di server bermasalah untuk akses Google Drive. '
            'Silakan perbarui token Google OAuth terlebih dahulu sebelum validasi atau generate dijalankan.'
        ) from exc
    except HttpError as exc:
        status = getattr(getattr(exc, 'resp', None), 'status', None)
        if status not in {403, 404}:
            raise DriveConfigurationError(f'Validasi Google Drive gagal: {exc}') from exc
        metadata_warning = 'Metadata folder tidak dapat dibaca langsung, tetapi akan diuji dengan upload probe.'

    try:
        probe_folder_upload_with_config(
            folder_id,
            current_app.config['GOOGLE_TOKEN_PATH'],
            list(current_app.config['DRIVE_SCOPES']),
        )
    except RefreshError as exc:
        raise DriveConfigurationError(
            'Token Google di server bermasalah untuk akses Google Drive. '
            'Silakan perbarui token Google OAuth terlebih dahulu sebelum validasi atau generate dijalankan.'
        ) from exc
    except HttpError as exc:
        status = getattr(getattr(exc, 'resp', None), 'status', None)
        if status in {400, 403, 404}:
            raise DriveConfigurationError('Folder ID / link Google Drive tidak valid atau tidak bisa dipakai untuk upload. Periksa kembali folder tujuan sebelum melanjutkan.') from exc
        raise DriveConfigurationError(f'Validasi Google Drive gagal: {exc}') from exc

    message = 'Folder Google Drive lolos uji upload dan siap digunakan.'
    if metadata_warning:
        message = f'{message} {metadata_warning}'

    return {
        'status': 'valid',
        'label': 'Link/ID valid',
        'message': message,
        'input_value': input_value,
        'folder_id': folder_id,
        'folder_name': folder_name,
    }


def _format_interval_label(minutes: int | None) -> str:
    value = max(1, int(minutes or 5))
    if value == 60:
        return 'Setiap 1 jam'
    if value % 60 == 0:
        hours = value // 60
        return f'Setiap {hours} jam'
    return f'Setiap {value} menit'


def _format_age_label(started_at: datetime | None) -> str:
    if not started_at:
        return '-'
    now = datetime.utcnow()
    delta = now - started_at.replace(tzinfo=None) if started_at.tzinfo else now - started_at
    total_minutes = max(0, int(delta.total_seconds() // 60))
    days, rem_minutes = divmod(total_minutes, 1440)
    hours, minutes = divmod(rem_minutes, 60)
    parts = []
    if days:
        parts.append(f'{days} hari')
    if hours:
        parts.append(f'{hours} jam')
    if minutes or not parts:
        parts.append(f'{minutes} menit')
    return ' '.join(parts)


def _display_run_duration(started_at: datetime | None, finished_at: datetime | None) -> str:
    if not started_at:
        return '-'
    end_time = finished_at or datetime.utcnow()
    started_value = started_at.replace(tzinfo=None) if started_at.tzinfo else started_at
    end_value = end_time.replace(tzinfo=None) if getattr(end_time, 'tzinfo', None) else end_time
    total_seconds = max(0, int((end_value - started_value).total_seconds()))
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f'{hours} jam {minutes} menit {seconds} detik'
    if minutes:
        return f'{minutes} menit {seconds} detik'
    return f'{seconds} detik'


def _display_run_status(status: str) -> str:
    return {
        'running': 'Sedang berjalan',
        'completed': 'Selesai',
        'completed_with_errors': 'Selesai dengan error',
        'failed': 'Gagal',
    }.get(status, status.replace('_', ' ').title())


def _run_status_badge_class(status: str) -> str:
    return {
        'running': 'primary',
        'completed': 'success',
        'completed_with_errors': 'warning',
        'failed': 'danger',
    }.get(status, 'secondary')


def _build_recent_run_cards(runs: list[AutoCertificateRun]) -> list[dict]:
    return [
        {
            'started_at': _display_datetime(run.started_at),
            'finished_at': _display_datetime(run.finished_at),
            'status': _display_run_status(run.status),
            'status_badge': _run_status_badge_class(run.status),
            'duration': _display_run_duration(run.started_at, run.finished_at),
            'message': run.message or '-',
        }
        for run in runs
    ]


def _build_event_runtime_summary(event: AutoCertificateEvent) -> dict:
    recent_runs = AutoCertificateRun.query.filter_by(event_id=event.id).order_by(AutoCertificateRun.id.desc()).limit(5).all()
    return {
        'interval_label': _format_interval_label(event.polling_interval_minutes),
        'active_since': _display_datetime(event.created_at),
        'age_label': _format_age_label(event.created_at),
        'recent_runs': _build_recent_run_cards(recent_runs),
    }


def _sample_files_dir() -> Path:
    return Path(current_app.root_path) / 'sample-files'


def _build_excel_format_hint(headers: list[str]) -> dict:
    normalized = {str(header).strip().lower() for header in headers if str(header).strip()}
    missing = [header for header in EXPECTED_SAMPLE_HEADERS if header.lower() not in normalized]
    if not missing:
        return {
            'status': 'match',
            'title': 'Format Excel sesuai contoh',
            'message': 'Header standar contoh berhasil terdeteksi: Nama dan Instansi.',
        }
    return {
        'status': 'custom',
        'title': 'Format Excel berbeda dari contoh',
        'message': 'Header standar contoh belum lengkap. Sistem tetap bisa dipakai, tetapi pastikan Bapak memetakan kolom yang benar pada langkah berikutnya.',
        'missing_headers': missing,
    }


def _normalize_header_key(value: str) -> str:
    return re.sub(r'[^a-z0-9]+', '', (value or '').strip().lower())


def _detect_preview_columns(headers: list[str]) -> tuple[str, str] | tuple[None, None]:
    normalized_map = {_normalize_header_key(header): header for header in headers}
    name_aliases = ['nama', 'namapeserta', 'peserta', 'namalengkap']
    institution_aliases = ['instansi', 'asalinstansi', 'unitkerja', 'satker', 'instansipeserta']

    name_column = next((normalized_map[key] for key in name_aliases if key in normalized_map), None)
    institution_column = next((normalized_map[key] for key in institution_aliases if key in normalized_map), None)
    return name_column, institution_column


def _template_placeholders(headers: list[str] | None = None) -> list[str]:
    placeholders = expand_placeholder_tokens(list(current_app.config.get('PPT_PLACEHOLDERS', [])))
    for token in placeholder_tokens_from_headers(headers):
        if token not in placeholders:
            placeholders.append(token)
    if PHOTO_PLACEHOLDER not in placeholders:
        placeholders.append(PHOTO_PLACEHOLDER)
    return placeholders


def _build_sample_conversion_preview(template_path: str, parsed) -> dict | None:
    name_column, institution_column = _detect_preview_columns(parsed.headers)
    sample_row = next((row for row in parsed.rows if any((str(value).strip() for key, value in row.items() if not str(key).startswith('_')))), None)
    if sample_row is None:
        return {
            'available': False,
            'message': 'Preview contoh belum bisa ditampilkan karena belum ada baris peserta yang terisi.',
        }

    preview_root = ensure_dir(Path(template_path).parent / '_validation_preview')
    safe_template_path = preview_root / 'template-safe-preview.pptx'
    working_dir = preview_root / 'build'
    filled_pptx_path = preview_root / 'sample-preview.pptx'

    build_pdf_safe_template(
        template_path,
        str(safe_template_path),
        placeholders=_template_placeholders(parsed.headers),
        working_dir=str(working_dir),
        soffice_path=current_app.config.get('SOFFICE_PATH', ''),
        cleanup_working_dir=True,
    )
    photo_column = detect_photo_column(parsed.headers)
    image_replacements = {}
    if photo_column and sample_row.get(photo_column):
        try:
            photo_path = prepare_certificate_photo(
                sample_row.get(photo_column),
                preview_root,
                google_token_path=current_app.config['GOOGLE_TOKEN_PATH'],
                drive_scopes=list(current_app.config['DRIVE_SCOPES']),
                row_number=sample_row.get('_row_number'),
                use_cached_service=True,
            )
            if photo_path:
                image_replacements[PHOTO_PLACEHOLDER] = photo_path
        except Exception:
            image_replacements = {}

    replace_placeholders(
        str(safe_template_path),
        str(filled_pptx_path),
        build_text_replacements_from_row(sample_row),
        image_replacements=image_replacements,
    )
    preview_pdf_path = Path(convert_document_with_soffice(
        str(filled_pptx_path),
        str(preview_root),
        'pdf',
        current_app.config.get('SOFFICE_PATH', ''),
    ))
    preview_png_path = Path(convert_document_with_soffice(
        str(preview_pdf_path),
        str(preview_root),
        'png',
        current_app.config.get('SOFFICE_PATH', ''),
    ))

    return {
        'available': True,
        'job_uuid': Path(template_path).parent.name,
        'image_name': preview_png_path.name,
        'pdf_name': preview_pdf_path.name,
        'participant_name': sample_row.get(name_column, '') if name_column else '',
        'institution_name': sample_row.get(institution_column, '') if institution_column else '',
        'name_column': name_column,
        'institution_column': institution_column,
        'message': 'Preview contoh berikut dibuat otomatis dari 1 peserta pertama yang terdeteksi pada file Excel.',
    }


def _render_new_job_template(**context):
    return render_template('certificate_new.html', **context)


def _display_datetime(value: datetime | None) -> str:
    if not value:
        return '-'
    tz_name = current_app.config.get('APP_TIMEZONE', 'Asia/Jakarta')
    local_tz = ZoneInfo(tz_name)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(local_tz).strftime('%d-%m-%Y %H:%M')


def _requested_action(job: GenerationJob) -> str | None:
    if job.requested_action:
        return job.requested_action
    if job.cancel_requested:
        return 'stop'
    return None


def _build_start_info(job: GenerationJob, started_flag: bool) -> dict | None:
    if not started_flag:
        return None
    action = _requested_action(job)
    if job.status == 'running' and action == 'pause':
        message, tone = START_INFO_MESSAGES['pause_requested']
        return {'message': message, 'tone': tone}
    if job.status == 'running' and action == 'stop':
        message, tone = START_INFO_MESSAGES['stop_requested']
        return {'message': message, 'tone': tone}
    if job.status in START_INFO_MESSAGES:
        message, tone = START_INFO_MESSAGES[job.status]
        return {'message': message, 'tone': tone}
    return None


def _render_mapping_step(
    *,
    parsed,
    drive_folder_id: str,
    staged_template_path: str,
    staged_workbook_path: str,
    original_template_name: str,
    original_excel_name: str,
    selected_name_column: str = '',
    selected_institution_column: str = '',
    selected_photo_column: str = '',
    drive_validation: dict | None = None,
    excel_format_hint: dict | None = None,
    sample_conversion_preview: dict | None = None,
):
    return _render_new_job_template(
        current_step='mapping',
        workbook_headers=parsed.headers,
        sheet_names=parsed.sheet_names,
        selected_sheet=parsed.selected_sheet,
        detected_total=len(parsed.rows),
        uploaded_template_name=original_template_name,
        uploaded_excel_name=original_excel_name,
        staged_template_path=staged_template_path,
        staged_workbook_path=staged_workbook_path,
        original_template_name=original_template_name,
        original_excel_name=original_excel_name,
        drive_folder_id=drive_folder_id,
        selected_name_column=selected_name_column,
        selected_institution_column=selected_institution_column,
        selected_photo_column=selected_photo_column or detect_photo_column(parsed.headers) or '',
        drive_validation=drive_validation,
        excel_format_hint=excel_format_hint,
        sample_conversion_preview=sample_conversion_preview,
    )


def _latest_row_results(job_id: int) -> dict[int, JobRowResult]:
    latest: dict[int, JobRowResult] = {}
    rows = JobRowResult.query.filter_by(job_id=job_id).order_by(JobRowResult.id.desc()).all()
    for row in rows:
        if row.row_number not in latest:
            latest[row.row_number] = row
    return latest


def _job_summary(job: GenerationJob) -> dict:
    progress = 0
    if job.total_rows > 0:
        progress = round((job.processed_rows / job.total_rows) * 100, 2)

    latest_results = _latest_row_results(job.id)
    latest_errors = [
        {
            'row_number': row.row_number,
            'participant_name': row.participant_name or '-',
            'message': row.message,
        }
        for row in sorted(
            (item for item in latest_results.values() if item.status == 'failed'),
            key=lambda item: item.row_number,
        )[:10]
    ]
    folder_link = f"https://drive.google.com/drive/folders/{job.drive_folder_id}" if job.drive_folder_id else ''
    final_states = {'completed', 'completed_with_errors', 'failed', 'cancelled'}
    action = _requested_action(job)
    return {
        'job_uuid': job.job_uuid,
        'status': job.status,
        'status_label': _display_status(job.status),
        'total_rows': job.total_rows,
        'processed_rows': job.processed_rows,
        'success_rows': job.success_rows,
        'failed_rows': job.failed_rows,
        'progress_percent': progress,
        'completed': job.status in final_states,
        'pausable': job.status == 'running' and action is None,
        'stoppable': job.status in {'running', 'paused'},
        'resumable': job.status == 'paused',
        'action_requested': action or '',
        'pause_requested': job.status == 'running' and action == 'pause',
        'stop_requested': job.status == 'running' and action == 'stop',
        'error_summary': job.error_summary or '',
        'latest_errors': latest_errors,
        'folder_link': folder_link,
        'folder_id': job.drive_folder_id,
    }


def _event_status_label(status: str) -> str:
    labels = {
        'draft': 'Draft',
        'ready': 'Siap',
        'active': 'Aktif',
        'inactive': 'Nonaktif',
        'error': 'Bermasalah',
        'completed': 'Selesai',
    }
    return labels.get(status, status.replace('_', ' ').title())


def _event_summary(event: AutoCertificateEvent) -> dict:
    progress = 0
    if event.total_responses:
        progress = round(((event.success_responses + event.failed_responses) / event.total_responses) * 100, 2)
    latest_items = AutoCertificateItem.query.filter_by(event_id=event.id).order_by(AutoCertificateItem.id.desc()).limit(10).all()
    latest_errors = [
        {
            'participant_name': item.participant_name or '-',
            'row_number': item.source_row_number,
            'message': item.error_message or '-',
        }
        for item in latest_items if item.status == 'failed'
    ]
    runtime = _build_event_runtime_summary(event)
    return {
        'event_uuid': event.event_uuid,
        'status': event.status,
        'status_label': _event_status_label(event.status),
        'enabled': event.enabled,
        'progress_percent': progress,
        'total_responses': event.total_responses,
        'pending_responses': event.pending_responses,
        'processing_responses': event.processing_responses,
        'success_responses': event.success_responses,
        'failed_responses': event.failed_responses,
        'last_synced_at': _display_datetime(event.last_synced_at),
        'next_run_at': _display_datetime(event.next_run_at),
        'folder_link': f"https://drive.google.com/drive/folders/{event.drive_folder_id}" if event.drive_folder_id else '',
        'latest_errors': latest_errors,
        'last_error': event.last_error or '',
        'spreadsheet_link': f"https://docs.google.com/spreadsheets/d/{event.spreadsheet_id}" if event.spreadsheet_id else '',
        'interval_label': runtime['interval_label'],
        'active_since': runtime['active_since'],
        'age_label': runtime['age_label'],
        'recent_runs': runtime['recent_runs'],
    }


def _save_auto_event_template(file_storage, event_uuid: str, headers: list[str]) -> tuple[str, str]:
    event_root = ensure_dir(Path(current_app.config['AUTO_EVENT_DIR']) / event_uuid)
    filename = slugify_filename(Path(file_storage.filename or 'template.pptx').stem, default='template')
    original_path = event_root / 'template-original.pptx'
    safe_path = event_root / 'template-safe.pptx'
    file_storage.save(original_path)
    build_pdf_safe_template(
        str(original_path),
        str(safe_path),
        placeholders=placeholder_tokens_from_headers(headers) + [PHOTO_PLACEHOLDER],
        working_dir=str(event_root / '_safe_build'),
        soffice_path=current_app.config.get('SOFFICE_PATH', ''),
        cleanup_working_dir=True,
    )
    return str(original_path), f'{filename}.pptx'


def _cleanup_auto_event_artifacts(event_uuid: str):
    event_root = Path(current_app.config['AUTO_EVENT_DIR']) / event_uuid
    runtime_root = Path(current_app.config['AUTO_EVENT_RUNTIME_DIR']) / event_uuid
    shutil.rmtree(event_root, ignore_errors=True)
    shutil.rmtree(runtime_root, ignore_errors=True)


def _purge_stale_instance_artifacts() -> dict:
    jobs_root = Path(current_app.config['JOB_DIR'])
    auto_root = Path(current_app.config['AUTO_EVENT_DIR'])
    runtime_root = Path(current_app.config['RUNTIME_DIR'])
    preview_root = Path(current_app.config['PREVIEW_DIR'])

    active_job_uuids = {job.job_uuid for job in GenerationJob.query.all()}
    active_event_uuids = {event.event_uuid for event in AutoCertificateEvent.query.all()}

    removed = {
        'job_dirs': 0,
        'preview_dirs': 0,
        'auto_event_dirs': 0,
        'runtime_soffice_profiles': 0,
        'safe_build_dirs': 0,
        'validation_dirs': 0,
    }

    for child in jobs_root.iterdir() if jobs_root.exists() else []:
        if not child.is_dir():
            continue
        if child.name not in active_job_uuids:
            shutil.rmtree(child, ignore_errors=True)
            removed['job_dirs'] += 1
            continue
        for nested_name in ('_pdf_safe_build', '_validation_preview'):
            nested = child / nested_name
            if nested.exists():
                shutil.rmtree(nested, ignore_errors=True)
                removed['safe_build_dirs' if nested_name == '_pdf_safe_build' else 'validation_dirs'] += 1

    for child in preview_root.iterdir() if preview_root.exists() else []:
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
            removed['preview_dirs'] += 1

    for child in auto_root.iterdir() if auto_root.exists() else []:
        if not child.is_dir():
            continue
        if child.name not in active_event_uuids:
            shutil.rmtree(child, ignore_errors=True)
            removed['auto_event_dirs'] += 1
            continue
        for nested_name in ('_safe_build', '_automation_validation'):
            nested = child / nested_name
            if nested.exists():
                shutil.rmtree(nested, ignore_errors=True)
                removed['safe_build_dirs' if nested_name == '_safe_build' else 'validation_dirs'] += 1

    for profiles_dir in runtime_root.rglob('_soffice_profiles') if runtime_root.exists() else []:
        if profiles_dir.is_dir():
            shutil.rmtree(profiles_dir, ignore_errors=True)
            removed['runtime_soffice_profiles'] += 1

    return removed


def _validate_auto_event_form(form, files) -> dict:
    name = (form.get('name') or '').strip()
    spreadsheet_input = (form.get('spreadsheet_id') or '').strip()
    worksheet_name = (form.get('worksheet_name') or '').strip() or None
    drive_input = (form.get('drive_folder_id') or '').strip()
    interval = int((form.get('polling_interval_minutes') or current_app.config.get('AUTO_EVENT_DEFAULT_INTERVAL_MINUTES', 5)))
    template_file = files.get('template_file')
    if not name:
        raise AutoCertificateError('Nama kegiatan wajib diisi.')
    spreadsheet_id = normalize_spreadsheet_input(spreadsheet_input)
    drive_folder_id = _normalize_drive_folder_input(drive_input)
    if not template_file or not template_file.filename or not _allowed(template_file.filename, current_app.config['ALLOWED_TEMPLATE_EXTENSIONS']):
        raise AutoCertificateError('Template kegiatan wajib file .pptx.')
    if interval < 1:
        interval = 1
    return {
        'name': name,
        'spreadsheet_id': spreadsheet_id,
        'worksheet_name': worksheet_name,
        'drive_folder_id': drive_folder_id,
        'polling_interval_minutes': interval,
        'template_file': template_file,
    }


def _preview_auto_event_setup(template_path: str, spreadsheet_id: str, worksheet_name: str | None) -> dict:
    parsed = fetch_form_rows(spreadsheet_id, worksheet_name=worksheet_name)
    validation = validate_event_configuration(parsed, template_path)
    columns = validation['columns']
    return {'parsed': parsed, 'validation': validation, 'columns': columns}


def _cleanup_job_artifacts(job_uuid: str):
    job_root = Path(current_app.config['JOB_DIR']) / job_uuid
    runtime_root = Path(current_app.config['RUNTIME_DIR']) / job_uuid
    try:
        shutil.rmtree(job_root, ignore_errors=True)
    except Exception:
        pass
    try:
        shutil.rmtree(runtime_root, ignore_errors=True)
    except Exception:
        pass


@certificates_bp.route('/')
@login_required
def dashboard():
    order_expr = db.func.coalesce(GenerationJob.started_at, GenerationJob.created_at)
    jobs = GenerationJob.query.order_by(order_expr.desc()).limit(10).all()
    events = AutoCertificateEvent.query.order_by(db.func.coalesce(AutoCertificateEvent.updated_at, AutoCertificateEvent.created_at).desc()).limit(10).all()
    dashboard_jobs = [
        {
            'job_uuid': job.job_uuid,
            'displayed_at': _display_datetime(job.started_at or job.created_at),
            'original_template_name': job.original_template_name,
            'original_excel_name': job.original_excel_name,
            'status_key': job.status,
            'status_label': _display_status(job.status),
            'processed_rows': job.processed_rows,
            'total_rows': job.total_rows,
            'progress_text': f"{job.processed_rows}/{job.total_rows} peserta",
            'progress_percent': round(((job.processed_rows / job.total_rows) * 100), 0) if job.total_rows else 0,
            'delete_url': url_for('certificates.delete_job', job_uuid=job.job_uuid),
            'can_delete': job.status not in {'running', 'paused'},
        }
        for job in jobs
    ]
    automation_events = [
        {
            'event_uuid': event.event_uuid,
            'name': event.name,
            'status_key': event.status,
            'status_label': _event_status_label(event.status),
            'success_responses': event.success_responses,
            'failed_responses': event.failed_responses,
            'pending_responses': event.pending_responses,
            'last_synced_at': _display_datetime(event.last_synced_at),
            'sync_automatic_label': _format_interval_label(event.polling_interval_minutes),
            'detail_url': url_for('certificates.auto_event_detail', event_uuid=event.event_uuid),
        }
        for event in events
    ]
    return render_template('certificate_dashboard.html', jobs=dashboard_jobs, automation_events=automation_events)


@certificates_bp.route('/automation/new', methods=['GET', 'POST'])
@login_required
def auto_event_new():
    events = AutoCertificateEvent.query.order_by(db.func.coalesce(AutoCertificateEvent.updated_at, AutoCertificateEvent.created_at).desc()).limit(20).all()
    automation_events = [
        {
            'event_uuid': event.event_uuid,
            'name': event.name,
            'status_key': event.status,
            'status_label': _event_status_label(event.status),
            'success_responses': event.success_responses,
            'failed_responses': event.failed_responses,
            'last_synced_at': _display_datetime(event.last_synced_at),
            'sync_automatic_label': _format_interval_label(event.polling_interval_minutes),
            'detail_url': url_for('certificates.auto_event_detail', event_uuid=event.event_uuid),
        }
        for event in events
    ]
    if request.method == 'POST':
        event_uuid = ''
        try:
            payload = _validate_auto_event_form(request.form, request.files)
            event_uuid = str(uuid4())
            parsed = fetch_form_rows(payload['spreadsheet_id'], worksheet_name=payload['worksheet_name'])
            template_path, template_filename = _save_auto_event_template(payload['template_file'], event_uuid, parsed.headers)
            validation = validate_event_configuration(parsed, template_path)
            drive_validation = _build_drive_validation(request.form.get('drive_folder_id') or payload['drive_folder_id'], payload['drive_folder_id'])
            columns = validation['columns']
            event = AutoCertificateEvent(
                event_uuid=event_uuid,
                name=payload['name'],
                spreadsheet_id=payload['spreadsheet_id'],
                spreadsheet_title=parsed.spreadsheet_title,
                worksheet_name=parsed.selected_sheet,
                drive_folder_id=payload['drive_folder_id'],
                drive_folder_name=drive_validation.get('folder_name') or payload['drive_folder_id'],
                template_filename=template_filename,
                name_column=columns.get('name') or 'Nama Lengkap',
                email_column=columns.get('email'),
                institution_column=columns.get('institution'),
                phone_column=columns.get('phone'),
                photo_column=columns.get('photo'),
                timestamp_column=columns.get('timestamp'),
                polling_interval_minutes=payload['polling_interval_minutes'],
                status='active',
                enabled=True,
                total_responses=0,
                pending_responses=0,
                processing_responses=0,
                success_responses=0,
                failed_responses=0,
                next_run_at=datetime.utcnow(),
            )
            db.session.add(event)
            db.session.commit()
            flash('Kegiatan auto-generate berhasil dibuat dan langsung diaktifkan.', 'success')
            return redirect(url_for('certificates.auto_event_new'))
        except (AutoCertificateError, SheetConfigurationError, DriveConfigurationError, RuntimeError, RefreshError, HttpError, ValueError) as exc:
            db.session.rollback()
            if event_uuid:
                _cleanup_auto_event_artifacts(event_uuid)
            flash(_friendly_google_configuration_message(str(exc)), 'danger')
            return render_template('auto_event_form.html', defaults=request.form, automation_events=automation_events)
        except TransportError as exc:
            db.session.rollback()
            if event_uuid:
                _cleanup_auto_event_artifacts(event_uuid)
            current_app.logger.warning('Google API transport error while creating automation event: %s', exc)
            flash(
                'Server tidak dapat terhubung ke layanan Google saat ini. '
                'Periksa koneksi internet / DNS server lalu coba lagi.',
                'danger',
            )
            return render_template('auto_event_form.html', defaults=request.form, automation_events=automation_events)
        except Exception as exc:
            db.session.rollback()
            if event_uuid:
                _cleanup_auto_event_artifacts(event_uuid)
            current_app.logger.exception('Unhandled error while creating automation event')
            flash(
                'Terjadi error internal saat menyimpan dan mengaktifkan kegiatan. '
                f'Detail teknis: {exc}',
                'danger',
            )
            return render_template('auto_event_form.html', defaults=request.form, automation_events=automation_events)
    defaults = {
        'polling_interval_minutes': current_app.config.get('AUTO_EVENT_DEFAULT_INTERVAL_MINUTES', 5),
    }
    return render_template('auto_event_form.html', defaults=defaults, automation_events=automation_events)


@certificates_bp.route('/automation/<event_uuid>')
@login_required
def auto_event_detail(event_uuid: str):
    event = AutoCertificateEvent.query.filter_by(event_uuid=event_uuid).first_or_404()
    summary = _event_summary(event)
    items = AutoCertificateItem.query.filter_by(event_id=event.id).order_by(AutoCertificateItem.id.desc()).limit(50).all()
    runs = AutoCertificateRun.query.filter_by(event_id=event.id).order_by(AutoCertificateRun.id.desc()).limit(10).all()
    return render_template('auto_event_detail.html', event=event, summary=summary, items=items, runs=runs)


@certificates_bp.route('/automation/<event_uuid>/sync', methods=['POST'])
@login_required
def auto_event_sync(event_uuid: str):
    event = AutoCertificateEvent.query.filter_by(event_uuid=event_uuid).first_or_404()
    try:
        summary = sync_event(event.id)
        flash(summary.message, 'success' if summary.failed_rows == 0 else 'warning')
    except AutoCertificateError as exc:
        flash(str(exc), 'danger')
    return redirect(url_for('certificates.auto_event_detail', event_uuid=event.event_uuid))


@certificates_bp.route('/automation/<event_uuid>/toggle', methods=['POST'])
@login_required
def auto_event_toggle(event_uuid: str):
    event = AutoCertificateEvent.query.filter_by(event_uuid=event_uuid).first_or_404()
    event.enabled = not event.enabled
    event.status = 'active' if event.enabled else 'inactive'
    if event.enabled and not event.next_run_at:
        event.next_run_at = datetime.utcnow()
    db.session.commit()
    flash('Automation kegiatan diaktifkan.' if event.enabled else 'Automation kegiatan dinonaktifkan.', 'success')
    return redirect(url_for('certificates.auto_event_detail', event_uuid=event.event_uuid))


@certificates_bp.route('/automation/<event_uuid>/retry', methods=['POST'])
@login_required
def auto_event_retry(event_uuid: str):
    event = AutoCertificateEvent.query.filter_by(event_uuid=event_uuid).first_or_404()
    count = retry_failed_items(event.id)
    flash(f'{count} peserta gagal dikembalikan ke antrean pending.', 'success')
    return redirect(url_for('certificates.auto_event_detail', event_uuid=event.event_uuid))


@certificates_bp.route('/automation/<event_uuid>/reset-processing', methods=['POST'])
@login_required
def auto_event_reset_processing(event_uuid: str):
    event = AutoCertificateEvent.query.filter_by(event_uuid=event_uuid).first_or_404()
    count = reset_processing_items(event.id)
    flash(f'{count} peserta macet dikembalikan ke antrean pending.', 'success')
    return redirect(url_for('certificates.auto_event_detail', event_uuid=event.event_uuid))


@certificates_bp.route('/automation/<event_uuid>/delete', methods=['POST'])
@login_required
def auto_event_delete(event_uuid: str):
    event = AutoCertificateEvent.query.filter_by(event_uuid=event_uuid).first_or_404()
    db.session.delete(event)
    db.session.commit()
    _cleanup_auto_event_artifacts(event_uuid)
    flash('Kegiatan auto-generate berhasil dihapus.', 'success')
    return redirect(url_for('certificates.auto_event_new'))


@certificates_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_job():
    step = (request.form.get('step') or '').strip() or 'validate'
    if request.method == 'POST':
        template_file = request.files.get('template_file')
        excel_file = request.files.get('excel_file')
        staged_template_path = (request.form.get('staged_template_path') or '').strip()
        staged_workbook_path = (request.form.get('staged_workbook_path') or '').strip()
        original_template_name = (request.form.get('original_template_name') or '').strip()
        original_excel_name = (request.form.get('original_excel_name') or '').strip()
        sheet_name = (request.form.get('sheet_name') or '').strip() or None
        drive_folder_id = (request.form.get('drive_folder_id') or '').strip()
        normalized_drive_folder_id = ''
        name_column = (request.form.get('name_column') or '').strip()
        institution_column = (request.form.get('institution_column') or '').strip()
        photo_column = (request.form.get('photo_column') or '').strip()

        try:
            normalized_drive_folder_id = _normalize_drive_folder_input(drive_folder_id)
        except DriveConfigurationError as exc:
            if step == 'mapping' and staged_workbook_path and Path(staged_workbook_path).exists():
                parsed = load_participants(staged_workbook_path, sheet_name=sheet_name)
                sample_conversion_preview = _build_sample_conversion_preview(staged_template_path, parsed) if staged_template_path and Path(staged_template_path).exists() else None
                flash(_friendly_google_configuration_message(str(exc)), 'danger')
                return _render_mapping_step(
                    parsed=parsed,
                    drive_folder_id=normalized_drive_folder_id,
                    staged_template_path=staged_template_path,
                    staged_workbook_path=staged_workbook_path,
                    original_template_name=original_template_name,
                    original_excel_name=original_excel_name,
                    selected_name_column=name_column,
                    selected_institution_column=institution_column,
                    selected_photo_column=photo_column,
                    drive_validation=_invalid_drive_validation(drive_folder_id, '', str(exc)),
                    excel_format_hint=_build_excel_format_hint(parsed.headers),
                    sample_conversion_preview=sample_conversion_preview,
                )
            flash(_friendly_google_configuration_message(str(exc)), 'danger')
            return _render_new_job_template(
                current_step='validate',
                drive_folder_id=drive_folder_id,
                drive_validation=_invalid_drive_validation(drive_folder_id, '', str(exc)),
                staged_template_path=staged_template_path,
                staged_workbook_path=staged_workbook_path,
                original_template_name=original_template_name,
                original_excel_name=original_excel_name,
            )

        if step == 'validate':
            job_uuid = Path(staged_template_path).parent.name if staged_template_path else str(uuid4())
            reuse_staged_files = (
                bool(staged_template_path and staged_workbook_path)
                and Path(staged_template_path).exists()
                and Path(staged_workbook_path).exists()
            )

            if reuse_staged_files:
                template_path = staged_template_path
                workbook_path = staged_workbook_path
            else:
                if not template_file or not template_file.filename or not _allowed(template_file.filename, current_app.config['ALLOWED_TEMPLATE_EXTENSIONS']):
                    flash('Template wajib file .pptx.', 'danger')
                    return _render_new_job_template(current_step='validate')
                if not excel_file or not excel_file.filename or not _allowed(excel_file.filename, current_app.config['ALLOWED_DATA_EXTENSIONS']):
                    flash('Data peserta wajib file .xlsx.', 'danger')
                    return _render_new_job_template(current_step='validate')

                template_path = _save_upload(template_file, job_uuid, 'pptx')
                workbook_path = _save_upload(excel_file, job_uuid, 'xlsx')
                original_template_name = template_file.filename
                original_excel_name = excel_file.filename
            try:
                parsed = load_participants(workbook_path, sheet_name=sheet_name)
                drive_validation = _build_drive_validation(drive_folder_id, normalized_drive_folder_id)
                excel_format_hint = _build_excel_format_hint(parsed.headers)
                sample_conversion_preview = _build_sample_conversion_preview(template_path, parsed)
                folder_name = drive_validation.get('folder_name') or normalized_drive_folder_id
                if drive_validation.get('status') == 'valid':
                    flash(f'Validasi berhasil. Data peserta terbaca {len(parsed.rows)} baris. Folder Drive tujuan: {folder_name}', 'success')
                else:
                    flash(f'Data peserta terbaca {len(parsed.rows)} baris. Folder ID berhasil dikenali, tetapi metadata folder belum terverifikasi. Silakan lanjutkan jika folder ini memang folder tujuan yang benar.', 'warning')
                if excel_format_hint.get('status') == 'custom':
                    missing_headers_text = ', '.join(excel_format_hint.get('missing_headers', []))
                    flash(f"Format header Excel berbeda dari contoh. Header standar yang belum terdeteksi: {missing_headers_text}. Bapak tetap bisa lanjut dan memetakan kolom secara manual.", 'warning')
                return _render_mapping_step(
                    parsed=parsed,
                    drive_folder_id=normalized_drive_folder_id,
                    staged_template_path=template_path,
                    staged_workbook_path=workbook_path,
                    original_template_name=original_template_name,
                    original_excel_name=original_excel_name,
                    drive_validation=drive_validation,
                    excel_format_hint=excel_format_hint,
                    sample_conversion_preview=sample_conversion_preview,
                )
            except (WorkbookValidationError, DriveConfigurationError, RuntimeError) as exc:
                preserve_staged_files = isinstance(exc, DriveConfigurationError)
                if not reuse_staged_files and not preserve_staged_files:
                    remove_files([template_path, workbook_path])
                    staged_template_path = ''
                    staged_workbook_path = ''
                    original_template_name = ''
                    original_excel_name = ''
                elif not reuse_staged_files and preserve_staged_files:
                    staged_template_path = template_path
                    staged_workbook_path = workbook_path
                flash(_friendly_google_configuration_message(str(exc)), 'danger')
                return _render_new_job_template(
                    current_step='validate',
                    drive_folder_id=normalized_drive_folder_id,
                    drive_validation=_invalid_drive_validation(drive_folder_id, normalized_drive_folder_id, str(exc)),
                    staged_template_path=staged_template_path,
                    staged_workbook_path=staged_workbook_path,
                    original_template_name=original_template_name,
                    original_excel_name=original_excel_name,
                )

        if step == 'mapping':
            if not staged_template_path or not staged_workbook_path:
                flash('File validasi tidak ditemukan. Silakan upload ulang.', 'danger')
                return redirect(url_for('certificates.new_job'))
            if not Path(staged_template_path).exists() or not Path(staged_workbook_path).exists():
                flash('File staging tidak tersedia lagi. Silakan upload ulang.', 'danger')
                return redirect(url_for('certificates.new_job'))
            try:
                parsed = load_participants(staged_workbook_path, sheet_name=sheet_name)
                drive_validation = _build_drive_validation(drive_folder_id, normalized_drive_folder_id)
                excel_format_hint = _build_excel_format_hint(parsed.headers)
                sample_conversion_preview = _build_sample_conversion_preview(staged_template_path, parsed)
                if not name_column or not institution_column:
                    flash('Silakan pilih kolom nama dan kolom instansi.', 'danger')
                    return _render_mapping_step(
                        parsed=parsed,
                        drive_folder_id=normalized_drive_folder_id,
                        staged_template_path=staged_template_path,
                        staged_workbook_path=staged_workbook_path,
                        original_template_name=original_template_name,
                        original_excel_name=original_excel_name,
                        drive_validation=drive_validation,
                        excel_format_hint=excel_format_hint,
                        sample_conversion_preview=sample_conversion_preview,
                    )
                missing_columns = [col for col in [name_column, institution_column, photo_column] if col and col not in parsed.headers]
                if missing_columns:
                    raise WorkbookValidationError(
                        f"Kolom pilihan tidak ditemukan pada Excel. Sistem mendeteksi header: {', '.join(parsed.headers)}. Sesuaikan dengan format contoh atau pilih ulang kolom yang tersedia."
                    )

                job_uuid = Path(staged_template_path).parent.name
                staged_root = Path(current_app.config['JOB_DIR']) / job_uuid
                staged_root.mkdir(parents=True, exist_ok=True)
                final_template_path = staged_root / 'template.pptx'
                final_original_template_path = staged_root / 'template-original.pptx'
                final_workbook_path = staged_root / 'participants.xlsx'
                safe_build_root = staged_root / '_pdf_safe_build'
                shutil.copy2(staged_template_path, final_original_template_path)
                build_pdf_safe_template(
                    staged_template_path,
                    str(final_template_path),
                    placeholders=_template_placeholders(parsed.headers),
                    working_dir=str(safe_build_root),
                    soffice_path=current_app.config.get('SOFFICE_PATH', ''),
                    cleanup_working_dir=True,
                )
                shutil.copy2(staged_workbook_path, final_workbook_path)

                job = GenerationJob(
                    job_uuid=job_uuid,
                    original_template_name=original_template_name or Path(staged_template_path).name,
                    original_excel_name=original_excel_name or Path(staged_workbook_path).name,
                    drive_folder_id=normalized_drive_folder_id,
                    selected_sheet=parsed.selected_sheet,
                    name_column=name_column,
                    institution_column=institution_column,
                    photo_column=photo_column or None,
                    total_rows=len(parsed.rows),
                    status='validated',
                    cancel_requested=False,
                    requested_action=None,
                )
                db.session.add(job)
                db.session.commit()
                remove_files([staged_template_path, staged_workbook_path])
                flash('Konfigurasi kolom berhasil disimpan. Template juga sudah diproses otomatis ke mode aman PDF. Job siap digenerate.', 'success')
                return redirect(url_for('certificates.review_job', job_uuid=job.job_uuid))
            except (WorkbookValidationError, DriveConfigurationError, RuntimeError) as exc:
                flash(_friendly_google_configuration_message(str(exc)), 'danger')
                if Path(staged_workbook_path).exists():
                    try:
                        parsed = load_participants(staged_workbook_path, sheet_name=sheet_name)
                    except WorkbookValidationError:
                        parsed = load_participants(staged_workbook_path)
                    return _render_mapping_step(
                        parsed=parsed,
                        drive_folder_id=normalized_drive_folder_id,
                        staged_template_path=staged_template_path,
                        staged_workbook_path=staged_workbook_path,
                        original_template_name=original_template_name,
                        original_excel_name=original_excel_name,
                        selected_name_column=name_column,
                        selected_institution_column=institution_column,
                        selected_photo_column=photo_column,
                        drive_validation=_invalid_drive_validation(drive_folder_id, normalized_drive_folder_id, str(exc)),
                        excel_format_hint=_build_excel_format_hint(parsed.headers),
                        sample_conversion_preview=_build_sample_conversion_preview(staged_template_path, parsed) if Path(staged_template_path).exists() else None,
                    )
                return redirect(url_for('certificates.new_job'))

    return _render_new_job_template(current_step='validate')


@certificates_bp.route('/samples/<sample_key>')
@login_required
def download_sample(sample_key: str):
    sample_config = SAMPLE_FILES.get(sample_key)
    if not sample_config:
        flash('File contoh yang diminta tidak tersedia.', 'warning')
        return redirect(url_for('certificates.new_job'))

    sample_path = _sample_files_dir() / sample_config['filename']
    if not sample_path.exists() or not sample_path.is_file():
        flash('File contoh belum tersedia pada server. Silakan hubungi administrator.', 'danger')
        return redirect(url_for('certificates.new_job'))

    return send_file(
        sample_path,
        as_attachment=True,
        download_name=sample_config['download_name'],
        mimetype='application/octet-stream',
        conditional=True,
    )


@certificates_bp.route('/staging-preview/<job_uuid>/<filename>')
@login_required
def staging_preview(job_uuid: str, filename: str):
    preview_root = Path(current_app.config['JOB_DIR']) / job_uuid / '_validation_preview'
    target = (preview_root / filename).resolve()
    try:
        target.relative_to(preview_root.resolve())
    except ValueError:
        flash('Preview tidak valid.', 'warning')
        return redirect(url_for('certificates.new_job'))
    if not target.exists() or not target.is_file():
        flash('File preview tidak tersedia lagi. Silakan validasi ulang template.', 'warning')
        return redirect(url_for('certificates.new_job'))
    return send_file(target, conditional=True)


@certificates_bp.route('/<job_uuid>')
@login_required
def review_job(job_uuid: str):
    job = GenerationJob.query.filter_by(job_uuid=job_uuid).first_or_404()
    started_flag = request.args.get('started') == '1'
    return render_template(
        'certificate_review.html',
        job=job,
        summary=_job_summary(job),
        start_info=_build_start_info(job, started_flag),
    )


@certificates_bp.route('/<job_uuid>/start', methods=['POST'])
@login_required
def start_job(job_uuid: str):
    job = GenerationJob.query.filter_by(job_uuid=job_uuid).first_or_404()
    if job.status != 'validated':
        flash('Job ini tidak bisa dijalankan lagi.', 'warning')
        return redirect(url_for('certificates.review_job', job_uuid=job.job_uuid))
    staged_root = Path(current_app.config['JOB_DIR']) / job.job_uuid
    template_path = staged_root / 'template.pptx'
    workbook_path = staged_root / 'participants.xlsx'
    if not template_path.exists() or not workbook_path.exists():
        flash('File staging job tidak ditemukan. Silakan upload ulang.', 'danger')
        return redirect(url_for('certificates.new_job'))
    job.cancel_requested = False
    job.requested_action = None
    db.session.commit()
    start_generation(current_app._get_current_object(), job.id, str(template_path), str(workbook_path))
    return redirect(url_for('certificates.review_job', job_uuid=job.job_uuid, started='1'))


@certificates_bp.route('/<job_uuid>/pause', methods=['POST'])
@login_required
def pause_job(job_uuid: str):
    job = GenerationJob.query.filter_by(job_uuid=job_uuid).first_or_404()
    if job.status != 'running':
        flash('Job ini tidak sedang berjalan, sehingga tidak bisa dijeda.', 'warning')
        return redirect(url_for('certificates.review_job', job_uuid=job.job_uuid))
    if _requested_action(job) is None:
        job.requested_action = 'pause'
        job.cancel_requested = False
        db.session.commit()
    return redirect(url_for('certificates.review_job', job_uuid=job.job_uuid, started='1'))


@certificates_bp.route('/<job_uuid>/resume', methods=['POST'])
@login_required
def resume_job(job_uuid: str):
    job = GenerationJob.query.filter_by(job_uuid=job_uuid).first_or_404()
    if job.status != 'paused':
        flash('Job ini tidak sedang dijeda, sehingga tidak bisa dilanjutkan.', 'warning')
        return redirect(url_for('certificates.review_job', job_uuid=job.job_uuid))
    staged_root = Path(current_app.config['JOB_DIR']) / job.job_uuid
    template_path = staged_root / 'template.pptx'
    workbook_path = staged_root / 'participants.xlsx'
    if not template_path.exists() or not workbook_path.exists():
        flash('File staging job tidak ditemukan lagi. Proses tidak bisa dilanjutkan.', 'danger')
        return redirect(url_for('certificates.review_job', job_uuid=job.job_uuid))
    job.cancel_requested = False
    job.requested_action = None
    job.completed_at = None
    db.session.commit()
    start_generation(current_app._get_current_object(), job.id, str(template_path), str(workbook_path))
    return redirect(url_for('certificates.review_job', job_uuid=job.job_uuid, started='1'))


@certificates_bp.route('/<job_uuid>/stop', methods=['POST'])
@login_required
def stop_job(job_uuid: str):
    job = GenerationJob.query.filter_by(job_uuid=job_uuid).first_or_404()
    if job.status == 'running':
        if _requested_action(job) is None:
            job.requested_action = 'stop'
            job.cancel_requested = False
            db.session.commit()
        return redirect(url_for('certificates.review_job', job_uuid=job.job_uuid, started='1'))

    if job.status == 'paused':
        job.requested_action = None
        job.cancel_requested = False
        job.status = 'cancelled'
        job.completed_at = datetime.utcnow()
        job.error_summary = 'Proses dihentikan oleh operator.'
        db.session.commit()
        _cleanup_job_artifacts(job.job_uuid)
        return redirect(url_for('certificates.review_job', job_uuid=job.job_uuid, started='1'))

    if job.status == 'validated':
        flash('Job belum mulai generate, sehingga tombol Batal/Stop belum aktif.', 'warning')
        return redirect(url_for('certificates.review_job', job_uuid=job.job_uuid))

    flash('Job ini tidak bisa dihentikan lagi.', 'warning')
    return redirect(url_for('certificates.review_job', job_uuid=job.job_uuid))


@certificates_bp.route('/<job_uuid>/delete', methods=['POST'])
@login_required
def delete_job(job_uuid: str):
    job = GenerationJob.query.filter_by(job_uuid=job_uuid).first_or_404()
    if job.status in {'running', 'paused'}:
        flash('Batch yang sedang berjalan atau dijeda tidak bisa dihapus.', 'warning')
        return redirect(url_for('certificates.dashboard'))

    job_id = job.job_uuid
    db.session.delete(job)
    db.session.commit()
    _cleanup_job_artifacts(job_id)
    flash('Riwayat batch berhasil dihapus beserta file PPTX dan Excel yang tersimpan pada sistem.', 'success')
    return redirect(url_for('certificates.dashboard'))


@certificates_bp.route('/<job_uuid>/status')
@login_required
def job_status(job_uuid: str):
    job = GenerationJob.query.filter_by(job_uuid=job_uuid).first_or_404()
    return jsonify({'ok': True, 'data': _job_summary(job)})
