from __future__ import annotations

import json
import shutil
import threading
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from flask import current_app

from extensions import db
from models import GenerationJob, JobRowResult
from services.certificate_photos import PHOTO_PLACEHOLDER, prepare_certificate_photo
from services.excel_parser import load_participants
from services.google_drive import upload_pdf_with_config
from services.pptx_generator import build_text_replacements_from_row, convert_pptx_to_pdf_with_soffice, replace_placeholders
from services.storage import ensure_dir, remove_files, slugify_filename

_JOB_LOCKS: dict[str, threading.Lock] = {}


def _job_lock(job_uuid: str) -> threading.Lock:
    if job_uuid not in _JOB_LOCKS:
        _JOB_LOCKS[job_uuid] = threading.Lock()
    return _JOB_LOCKS[job_uuid]


def start_generation(app, job_id: int, template_path: str, workbook_path: str):
    thread = threading.Thread(
        target=_run_generation,
        args=(app, job_id, template_path, workbook_path),
        daemon=True,
    )
    thread.start()


def _requested_action(job: GenerationJob | None) -> str | None:
    if job is None:
        return None
    if job.requested_action:
        return job.requested_action
    if job.cancel_requested:
        return 'stop'
    return None


def _latest_row_results(job_id: int) -> dict[int, JobRowResult]:
    latest: dict[int, JobRowResult] = {}
    rows = JobRowResult.query.filter_by(job_id=job_id).order_by(JobRowResult.id.desc()).all()
    for row in rows:
        if row.row_number not in latest:
            latest[row.row_number] = row
    return latest


def _recalculate_job_counters(job: GenerationJob):
    latest_results = _latest_row_results(job.id)
    success_rows = sum(1 for row in latest_results.values() if row.status == 'success')
    failed_rows = sum(1 for row in latest_results.values() if row.status == 'failed')
    job.success_rows = success_rows
    job.failed_rows = failed_rows
    job.processed_rows = success_rows + failed_rows


def _cleanup_job_inputs(template_path: str, workbook_path: str):
    remove_files([template_path, workbook_path])
    try:
        template_parent = Path(template_path).parent
        workbook_parent = Path(workbook_path).parent
        Path(template_path).unlink(missing_ok=True)
        Path(workbook_path).unlink(missing_ok=True)
        if template_parent == workbook_parent and template_parent.exists() and not any(template_parent.iterdir()):
            template_parent.rmdir()
    except Exception:
        pass


def _cleanup_runtime_dir(runtime_root: Path | None):
    if runtime_root is None:
        return
    try:
        shutil.rmtree(runtime_root, ignore_errors=True)
    except Exception:
        pass


def _finalize_requested_action(job: GenerationJob, action: str):
    _recalculate_job_counters(job)
    job.requested_action = None
    job.cancel_requested = False
    job.completed_at = datetime.utcnow()
    if action == 'pause':
        job.status = 'paused'
        job.error_summary = 'Proses dijeda oleh operator. Silakan lanjutkan proses untuk meneruskan batch dari progres terakhir.'
    else:
        job.status = 'cancelled'
        job.error_summary = 'Proses dihentikan oleh operator.'
    db.session.commit()


def _finalize_completed(job: GenerationJob):
    _recalculate_job_counters(job)
    job.requested_action = None
    job.cancel_requested = False
    job.status = 'completed' if job.failed_rows == 0 else 'completed_with_errors'
    job.completed_at = datetime.utcnow()
    if job.status == 'completed':
        job.error_summary = None
    elif not job.error_summary:
        job.error_summary = 'Sebagian sertifikat gagal diproses. Silakan tinjau ringkasan error.'
    db.session.commit()


def _record_row_result(job: GenerationJob, result: dict):
    db.session.add(JobRowResult(
        job_id=job.id,
        row_number=result['row_number'],
        participant_name=result.get('participant_name'),
        institution_name=result.get('institution_name'),
        output_filename=result.get('output_filename'),
        drive_file_id=result.get('drive_file_id'),
        drive_link=result.get('drive_link'),
        status='success' if result['ok'] else 'failed',
        message=result['message'],
    ))
    _recalculate_job_counters(job)
    db.session.commit()


def _process_participant(
    runtime_root: Path,
    template_path: str,
    drive_folder_id: str,
    row_number: int,
    name: str,
    institution: str,
    photo_ref: str,
    text_replacements: dict[str, str],
    retry_count: int,
    google_token_path: str,
    drive_scopes: list[str],
    soffice_path: str,
) -> dict:
    base_name = slugify_filename(f'Sertifikat {name}', default=f'Sertifikat Peserta {row_number}')
    last_error = None
    for attempt in range(retry_count + 1):
        pptx_path = runtime_root / f'{uuid4().hex}-{base_name}.pptx'
        pdf_path = runtime_root / f'{pptx_path.stem}.pdf'
        photo_path = None
        try:
            image_replacements = {}
            photo_path = prepare_certificate_photo(
                photo_ref,
                runtime_root,
                google_token_path=google_token_path,
                drive_scopes=drive_scopes,
                row_number=row_number,
                use_cached_service=True,
            ) if photo_ref else None
            if photo_path:
                image_replacements[PHOTO_PLACEHOLDER] = photo_path
            replace_placeholders(
                template_path,
                str(pptx_path),
                text_replacements,
                image_replacements=image_replacements,
            )
            actual_pdf_path = convert_pptx_to_pdf_with_soffice(str(pptx_path), str(runtime_root), soffice_path)
            filename = f'{base_name}.pdf'
            upload_result = upload_pdf_with_config(
                actual_pdf_path,
                drive_folder_id,
                filename,
                google_token_path,
                drive_scopes,
                use_cached_service=True,
            )
            remove_files([pptx_path, actual_pdf_path, photo_path])
            return {
                'ok': True,
                'row_number': row_number,
                'participant_name': name,
                'institution_name': institution,
                'output_filename': filename,
                'drive_file_id': upload_result.get('id'),
                'drive_link': upload_result.get('webViewLink'),
                'message': 'Upload berhasil.',
                'attempts': attempt + 1,
            }
        except Exception as exc:
            last_error = str(exc)
            remove_files([pptx_path, pdf_path, photo_path])
    return {
        'ok': False,
        'row_number': row_number,
        'participant_name': name,
        'institution_name': institution,
        'output_filename': f'{base_name}.pdf',
        'message': last_error or 'Proses gagal tanpa detail error.',
        'attempts': retry_count + 1,
    }


def _run_generation(app, job_id: int, template_path: str, workbook_path: str):
    runtime_root: Path | None = None
    with app.app_context():
        job = db.session.get(GenerationJob, job_id)
        if job is None:
            return
        lock = _job_lock(job.job_uuid)
        if not lock.acquire(blocking=False):
            return
        cleanup_inputs = True
        try:
            previous_status = job.status
            if previous_status == 'validated':
                JobRowResult.query.filter_by(job_id=job.id).delete()
                job.processed_rows = 0
                job.success_rows = 0
                job.failed_rows = 0
            else:
                _recalculate_job_counters(job)

            job.status = 'running'
            job.started_at = datetime.utcnow()
            job.completed_at = None
            job.cancel_requested = False
            job.requested_action = None
            job.error_summary = None
            db.session.commit()

            parsed = load_participants(workbook_path, sheet_name=job.selected_sheet)
            job = db.session.get(GenerationJob, job_id)
            if job is None:
                return
            job.total_rows = len(parsed.rows)
            db.session.commit()

            latest_results = _latest_row_results(job.id)
            successful_rows = {row_number for row_number, row in latest_results.items() if row.status == 'success'}
            participants = []
            for row in parsed.rows:
                job = db.session.get(GenerationJob, job_id)
                if job is None:
                    return
                action = _requested_action(job)
                if action in {'pause', 'stop'}:
                    _finalize_requested_action(job, action)
                    cleanup_inputs = action != 'pause'
                    return
                row_number = row.get('_row_number', 0)
                if row_number in successful_rows:
                    continue
                name = (row.get(job.name_column) or '').strip() if job.name_column else ''
                institution = (row.get(job.institution_column) or '').strip() if job.institution_column else ''
                photo_ref = (row.get(job.photo_column) or '').strip() if job.photo_column else ''
                text_replacements = build_text_replacements_from_row(row)
                try:
                    mapping = json.loads(job.mapping_json or '{}')
                except (TypeError, ValueError):
                    mapping = {}
                if mapping:
                    text_replacements = {
                        target: ('' if row.get(source) is None else str(row.get(source)).strip())
                        for source, target in mapping.items()
                        if target
                    }
                display_name = name or institution or f'Peserta {row_number}'
                participants.append((row_number, display_name, institution, photo_ref, text_replacements))

            runtime_root = ensure_dir(Path(current_app.config['RUNTIME_DIR']) / job.job_uuid)
            max_workers = max(1, int(current_app.config.get('MAX_PARALLEL_WORKERS', 3)))
            retry_count = max(0, int(current_app.config.get('JOB_RETRY_COUNT', 1)))
            google_token_path = current_app.config['GOOGLE_TOKEN_PATH']
            drive_scopes = list(current_app.config['DRIVE_SCOPES'])
            soffice_path = current_app.config.get('SOFFICE_PATH', '')

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                pending_futures = set()
                participant_iter = iter(participants)
                future_map = {}
                requested_action = None

                def submit_next() -> bool:
                    try:
                        row_number, name, institution, photo_ref, text_replacements = next(participant_iter)
                    except StopIteration:
                        return False
                    future = executor.submit(
                        _process_participant,
                        runtime_root,
                        template_path,
                        job.drive_folder_id,
                        row_number,
                        name,
                        institution,
                        photo_ref,
                        text_replacements,
                        retry_count,
                        google_token_path,
                        drive_scopes,
                        soffice_path,
                    )
                    pending_futures.add(future)
                    future_map[future] = (row_number, name, institution)
                    return True

                for _ in range(max_workers):
                    if not submit_next():
                        break

                while pending_futures:
                    done, pending_futures = wait(pending_futures, return_when=FIRST_COMPLETED)
                    job = db.session.get(GenerationJob, job_id)
                    if job is None:
                        return
                    action = _requested_action(job)
                    if action in {'pause', 'stop'} and requested_action is None:
                        requested_action = action
                        if action == 'pause':
                            job.error_summary = 'Permintaan pause sudah dicatat. Menunggu pekerjaan aktif selesai.'
                        else:
                            job.error_summary = 'Permintaan stop sudah dicatat. Menunggu pekerjaan aktif selesai.'
                        db.session.commit()
                        for future in list(pending_futures):
                            future.cancel()

                    for future in done:
                        row_number, name, institution = future_map.pop(future)
                        if future.cancelled():
                            continue
                        try:
                            result = future.result()
                        except Exception as exc:
                            result = {
                                'ok': False,
                                'row_number': row_number,
                                'participant_name': name,
                                'institution_name': institution,
                                'output_filename': f'Sertifikat {name}.pdf',
                                'message': str(exc),
                                'attempts': retry_count + 1,
                            }

                        job = db.session.get(GenerationJob, job_id)
                        if job is None:
                            return
                        _record_row_result(job, result)

                        if requested_action is None:
                            submit_next()

                job = db.session.get(GenerationJob, job_id)
                if job is None:
                    return
                final_action = requested_action or _requested_action(job)
                if final_action in {'pause', 'stop'}:
                    _finalize_requested_action(job, final_action)
                    cleanup_inputs = final_action != 'pause'
                else:
                    _finalize_completed(job)
                    cleanup_inputs = True
        except Exception as exc:
            job = db.session.get(GenerationJob, job_id)
            if job is not None:
                job.status = 'failed'
                job.requested_action = None
                job.cancel_requested = False
                _recalculate_job_counters(job)
                job.error_summary = str(exc)
                job.completed_at = datetime.utcnow()
                db.session.commit()
            cleanup_inputs = True
        finally:
            if cleanup_inputs:
                _cleanup_job_inputs(template_path, workbook_path)
                _cleanup_runtime_dir(runtime_root)
            lock.release()
