from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from extensions import db
from models import PendingEvidence
from services.incident_gateway import load_incident_module


ACTIVE_PENDING_STATUSES = {None, ''}


def _short_error(exc_or_text):
    text = str(exc_or_text or '').strip()
    if not text:
        return ''
    if 'invalid_grant' in text:
        return 'Token/akses Google Drive perlu diperbarui.'
    if len(text) > 240:
        return text[:240] + '...'
    return text


def check_drive_health():
    """Return a small status dict without exposing token/secret contents."""
    try:
        incident_module = load_incident_module()
        token_path = Path(str(getattr(incident_module, 'CREDS_PATH', '')))
        token_exists = token_path.exists()
        if not token_exists:
            return {
                'ok': False,
                'status': 'missing_token',
                'message': 'Token Google Drive belum tersedia.',
                'account': '',
                'token_path': str(token_path),
            }
        service = incident_module.get_drive_service()
        about = service.about().get(fields='user(emailAddress,displayName)').execute()
        user = about.get('user', {}) or {}
        root_id = getattr(incident_module, 'BUKTI_ROOT_FOLDER_ID', '')
        root_ok = False
        if root_id:
            service.files().get(fileId=root_id, fields='id,name,trashed').execute()
            root_ok = True
        return {
            'ok': True,
            'status': 'ok',
            'message': 'Google Drive siap digunakan.',
            'account': user.get('emailAddress') or user.get('displayName') or '',
            'token_path': str(token_path),
            'root_ok': root_ok,
        }
    except Exception as exc:
        return {
            'ok': False,
            'status': 'error',
            'message': _short_error(exc),
            'account': '',
            'token_path': '',
            'root_ok': False,
        }


def pending_count():
    return PendingEvidence.query.filter(PendingEvidence.resolved_at.is_(None)).count()


def create_pending_evidence(ticket_code, status_label, evidence_kind, file_paths, note='', error_message='', created_by=''):
    rows = []
    for raw_path in file_paths or []:
        path = Path(str(raw_path or '').strip())
        if not path:
            continue
        row = PendingEvidence(
            ticket_code=str(ticket_code or '').strip().upper(),
            status_label=str(status_label or 'OPEN').strip().upper(),
            evidence_kind=str(evidence_kind or 'bukti_awal').strip() or 'bukti_awal',
            file_path=str(path),
            source_filename=path.name,
            note=note or '',
            error_message=_short_error(error_message),
            created_by=created_by or '',
        )
        db.session.add(row)
        rows.append(row)
    return rows


def retry_one_pending(row):
    incident_module = load_incident_module()
    file_path = Path(row.file_path)
    if not file_path.exists() or not file_path.is_file():
        row.retry_count = (row.retry_count or 0) + 1
        row.error_message = f'File lokal tidak ditemukan: {row.file_path}'
        return False, row.error_message

    is_resolve = row.evidence_kind == 'bukti_resolve'
    args = SimpleNamespace(
        ticket=row.ticket_code,
        status=row.status_label or 'IN_PROGRESS',
        note=row.note or 'Retry upload bukti tertunda',
        handled_by='',
        sender_name=row.created_by or 'Admin Portal',
        sender=row.created_by or 'Admin Portal',
        message='',
        bukti_awal='',
        bukti_resolve='',
        bukti_awal_files=[str(file_path)] if not is_resolve else [],
        bukti_resolve_files=[str(file_path)] if is_resolve else [],
    )
    response_text = str(incident_module.cmd_update(args) or '').strip()
    row.retry_count = (row.retry_count or 0) + 1
    if response_text.startswith('[ERROR]'):
        row.error_message = _short_error(response_text)
        return False, row.error_message

    row.resolved_at = datetime.utcnow()
    row.error_message = ''
    marker = 'Bukti resolve:' if is_resolve else 'Bukti awal:'
    uploaded_url = ''
    for line in response_text.splitlines():
        if line.startswith(marker):
            uploaded_url = line.split(':', 1)[1].strip()
            break
    row.uploaded_url = uploaded_url
    return True, response_text


def retry_pending_evidence(limit=20):
    rows = (
        PendingEvidence.query
        .filter(PendingEvidence.resolved_at.is_(None))
        .order_by(PendingEvidence.created_at.asc(), PendingEvidence.id.asc())
        .limit(limit)
        .all()
    )
    results = []
    for row in rows:
        ok, detail = retry_one_pending(row)
        results.append({'id': row.id, 'ticket_code': row.ticket_code, 'ok': ok, 'detail': detail})
    db.session.commit()
    return results


def pending_rows(limit=100):
    return (
        PendingEvidence.query
        .filter(PendingEvidence.resolved_at.is_(None))
        .order_by(PendingEvidence.created_at.desc(), PendingEvidence.id.desc())
        .limit(limit)
        .all()
    )
