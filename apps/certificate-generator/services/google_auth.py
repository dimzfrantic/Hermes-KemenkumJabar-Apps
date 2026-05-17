from __future__ import annotations

from pathlib import Path

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


def load_authorized_user_credentials(token_path: str) -> Credentials:
    token_file = Path(token_path)
    if not token_file.exists():
        raise FileNotFoundError(f'Token Google tidak ditemukan di {token_file}')
    return Credentials.from_authorized_user_file(str(token_file))