from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.google_oauth_refresh import exchange_code, start_flow

JAKARTA = ZoneInfo('Asia/Jakarta')


def _metadata_path(token_path: str) -> Path:
    token_file = Path(token_path)
    return token_file.with_suffix(token_file.suffix + '.meta.json')


def _write_private_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + '.tmp')
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    os.chmod(tmp_path, 0o600)
    tmp_path.replace(path)
    os.chmod(path, 0o600)


def record_authorization(token_path: str, testing_window_days: int = 7):
    authorized_at = datetime.now(timezone.utc)
    metadata = {
        'authorized_at': authorized_at.isoformat(),
        'renewal_due_at': (authorized_at + timedelta(days=max(1, testing_window_days))).isoformat(),
        'testing_window_days': max(1, testing_window_days),
    }
    _write_private_json(_metadata_path(token_path), metadata)
    return metadata


def ensure_authorization_metadata(token_path: str, testing_window_days: int = 7):
    token_file = Path(token_path)
    metadata_file = _metadata_path(token_path)
    if metadata_file.exists():
        try:
            metadata = json.loads(metadata_file.read_text())
            if metadata.get('authorized_at') and metadata.get('renewal_due_at'):
                return metadata
        except (OSError, ValueError, TypeError):
            pass
    if not token_file.exists():
        return {}
    authorized_at = datetime.fromtimestamp(token_file.stat().st_mtime, timezone.utc)
    metadata = {
        'authorized_at': authorized_at.isoformat(),
        'renewal_due_at': (authorized_at + timedelta(days=max(1, testing_window_days))).isoformat(),
        'testing_window_days': max(1, testing_window_days),
    }
    _write_private_json(metadata_file, metadata)
    return metadata


def _parse_datetime(value: str | None):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _display_datetime(value: datetime | None) -> str:
    if value is None:
        return '-'
    return value.astimezone(JAKARTA).strftime('%d %B %Y %H:%M WIB')


def get_oauth_status(token_path: str, client_secret_path: str, testing_window_days: int = 7) -> dict:
    token_file = Path(token_path)
    client_file = Path(client_secret_path)
    base = {
        'status_key': 'missing',
        'status_label': 'Token belum tersedia',
        'alert_class': 'danger',
        'message': 'Token Google belum tersedia. Lakukan otorisasi sebelum generate sertifikat.',
        'token_exists': token_file.exists(),
        'client_exists': client_file.exists(),
        'has_refresh_token': False,
        'authorized_at': '-',
        'renewal_due_at': '-',
        'days_remaining': None,
        'access_token_expiry': '-',
        'scopes': [],
    }
    if not client_file.exists():
        base['message'] = 'OAuth client tidak ditemukan pada server. Hubungi pengelola aplikasi.'
        return base
    if not token_file.exists():
        return base

    try:
        token_data = json.loads(token_file.read_text())
    except (OSError, ValueError, TypeError):
        base['status_key'] = 'invalid'
        base['status_label'] = 'File token tidak valid'
        base['message'] = 'File token Google tidak dapat dibaca. Lakukan otorisasi ulang.'
        return base

    base['has_refresh_token'] = bool(token_data.get('refresh_token'))
    base['scopes'] = list(token_data.get('scopes') or [])
    access_expiry = _parse_datetime(token_data.get('expiry'))
    base['access_token_expiry'] = _display_datetime(access_expiry)

    metadata = ensure_authorization_metadata(token_path, testing_window_days)
    authorized_at = _parse_datetime(metadata.get('authorized_at'))
    renewal_due = _parse_datetime(metadata.get('renewal_due_at'))
    base['authorized_at'] = _display_datetime(authorized_at)
    base['renewal_due_at'] = _display_datetime(renewal_due)

    if not base['has_refresh_token']:
        base['status_key'] = 'invalid'
        base['status_label'] = 'Refresh token tidak tersedia'
        base['message'] = 'Token tidak dapat diperbarui otomatis. Lakukan otorisasi ulang.'
        return base

    if renewal_due is None:
        base['status_key'] = 'warning'
        base['status_label'] = 'Jadwal token tidak diketahui'
        base['alert_class'] = 'warning'
        base['message'] = 'Perbarui token sebelum menjalankan kegiatan penting.'
        return base

    now = datetime.now(timezone.utc)
    remaining_seconds = (renewal_due - now).total_seconds()
    base['days_remaining'] = max(0, int(remaining_seconds // 86400))
    if remaining_seconds <= 0:
        base['status_key'] = 'overdue'
        base['status_label'] = 'Perlu diperbarui'
        base['alert_class'] = 'danger'
        base['message'] = 'Masa Testing diperkirakan sudah melewati tujuh hari. Perbarui token sebelum generate.'
    elif remaining_seconds <= 2 * 86400:
        base['status_key'] = 'warning'
        base['status_label'] = 'Segera diperbarui'
        base['alert_class'] = 'warning'
        base['message'] = 'Token mendekati batas masa Testing. Perbarui sekarang agar proses sertifikat tidak terganggu.'
    else:
        base['status_key'] = 'healthy'
        base['status_label'] = 'Siap digunakan'
        base['alert_class'] = 'success'
        base['message'] = 'Token tersedia dan refresh otomatis aktif.'
    return base


def begin_oauth_flow(client_secret_path: str, token_path: str, session_path: str, scopes: list[str]) -> dict:
    return start_flow(Path(client_secret_path), Path(token_path), Path(session_path), scopes)


def complete_oauth_flow(session_path: str, callback_url_or_code: str, testing_window_days: int = 7) -> dict:
    result = exchange_code(Path(session_path), callback_url_or_code)
    result['metadata'] = record_authorization(result['token_path'], testing_window_days)
    return result
