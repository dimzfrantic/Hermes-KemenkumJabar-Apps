from __future__ import annotations

import fcntl
import os
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials


def _normalize_scope(scope: str) -> str:
    return (scope or '').strip()


def _scope_satisfies(granted_scope: str, required_scope: str) -> bool:
    granted = _normalize_scope(granted_scope)
    required = _normalize_scope(required_scope)
    if not granted or not required:
        return False
    if granted == required:
        return True

    # Google Sheets full scope also covers readonly access.
    if granted == 'https://www.googleapis.com/auth/spreadsheets' and required == 'https://www.googleapis.com/auth/spreadsheets.readonly':
        return True

    return False


def ensure_required_scopes(creds: Credentials, required_scopes: list[str], context_label: str):
    granted_scopes = list(getattr(creds, 'scopes', None) or [])
    missing = []
    for required_scope in required_scopes:
        if not any(_scope_satisfies(granted_scope, required_scope) for granted_scope in granted_scopes):
            missing.append(required_scope)

    if missing:
        raise RuntimeError(
            f'{context_label} belum memiliki scope yang dibutuhkan: {", ".join(missing)}. '
            f'Scope tersedia pada token saat ini: {", ".join(granted_scopes) or "(kosong)"}. '
            'Silakan perbarui token Google OAuth di server.'
        )


def _write_credentials(token_file: Path, creds: Credentials):
    tmp_file = token_file.with_suffix(token_file.suffix + '.tmp')
    tmp_file.write_text(creds.to_json())
    os.chmod(tmp_file, 0o600)
    tmp_file.replace(token_file)
    os.chmod(token_file, 0o600)


def load_authorized_user_credentials(token_path: str) -> Credentials:
    token_file = Path(token_path)
    if not token_file.exists():
        raise FileNotFoundError(f'Token Google tidak ditemukan di {token_file}')

    lock_file = token_file.with_suffix(token_file.suffix + '.lock')
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    with lock_file.open('a+') as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        creds = Credentials.from_authorized_user_file(str(token_file))
        if creds.expired:
            if not creds.refresh_token:
                raise RuntimeError(
                    'Token Google kedaluwarsa dan tidak memiliki refresh token. '
                    'Otorisasi ulang satu kali diperlukan.'
                )
            try:
                creds.refresh(Request())
            except RefreshError as exc:
                raise RuntimeError(
                    'Refresh token Google sudah dicabut/kedaluwarsa atau OAuth client tidak aktif. '
                    'Otorisasi ulang diperlukan; token akses biasa seharusnya diperbarui otomatis.'
                ) from exc
            _write_credentials(token_file, creds)
        return creds