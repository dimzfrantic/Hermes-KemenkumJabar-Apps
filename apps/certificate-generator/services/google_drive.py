from __future__ import annotations

import io
import re
import socket
import threading
import time
from pathlib import Path

from flask import current_app
from google.auth.exceptions import TransportError
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload, MediaIoBaseUpload
from httplib2.error import ServerNotFoundError

from services.google_auth import ensure_required_scopes, load_authorized_user_credentials


class DriveConfigurationError(RuntimeError):
    pass


_THREAD_LOCAL = threading.local()


def _resolve_host_with_retry(host: str, attempts: int = 3, delay_seconds: float = 1.0):
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            return socket.getaddrinfo(host, 443)
        except socket.gaierror as exc:
            last_error = exc
            if attempt == attempts:
                break
            time.sleep(delay_seconds * attempt)
    raise TransportError(f'Gagal resolve DNS host {host}: {last_error}')


def _warm_google_dns():
    for host in ('oauth2.googleapis.com', 'www.googleapis.com'):
        _resolve_host_with_retry(host)


def _cache_key(token_path: str, scopes: list[str]) -> tuple[str, tuple[str, ...]]:
    return (str(Path(token_path).expanduser().resolve()), tuple(scopes))


def load_credentials_from_path(token_path: str, scopes: list[str]) -> Credentials:
    token_file = Path(token_path)
    if not token_file.exists():
        raise DriveConfigurationError(f'Token Google tidak ditemukan di {token_file}')
    try:
        creds = load_authorized_user_credentials(str(token_file))
        ensure_required_scopes(creds, scopes, 'Token Google Drive')
        return creds
    except FileNotFoundError:
        raise DriveConfigurationError(f'Token Google tidak ditemukan di {token_file}')
    except RuntimeError as exc:
        raise DriveConfigurationError(str(exc)) from exc


def get_drive_service_from_config(token_path: str, scopes: list[str], use_cache: bool = False):
    cache = None
    key = None
    if use_cache:
        cache = getattr(_THREAD_LOCAL, 'drive_services', None)
        if cache is None:
            cache = {}
            _THREAD_LOCAL.drive_services = cache
        key = _cache_key(token_path, scopes)
        if key in cache:
            return cache[key]
    creds = load_credentials_from_path(token_path, scopes)
    _warm_google_dns()
    service = build('drive', 'v3', credentials=creds)
    if use_cache and cache is not None and key is not None:
        cache[key] = service
    return service


def get_drive_service():
    return get_drive_service_from_config(
        current_app.config['GOOGLE_TOKEN_PATH'],
        current_app.config['DRIVE_SCOPES'],
    )


def get_folder_metadata(folder_id: str) -> dict:
    service = get_drive_service()
    try:
        return service.files().get(fileId=folder_id, fields='id,name,webViewLink').execute()
    except ServerNotFoundError as exc:
        raise TransportError(f'Gagal terhubung ke Google Drive API: {exc}') from exc


def probe_folder_upload_with_config(folder_id: str, token_path: str, scopes: list[str], drive_service=None) -> dict:
    service = drive_service or get_drive_service_from_config(token_path, scopes)
    probe_name = '.hermes-drive-validation.txt'
    media = MediaIoBaseUpload(io.BytesIO(b'hermes drive validation probe'), mimetype='text/plain', resumable=False)
    try:
        created = service.files().create(
            body={'name': probe_name, 'parents': [folder_id]},
            media_body=media,
            fields='id,name,webViewLink,parents'
        ).execute()
    except ServerNotFoundError as exc:
        raise TransportError(f'Gagal terhubung ke Google Drive API: {exc}') from exc
    file_id = created.get('id')
    try:
        if file_id:
            service.files().delete(fileId=file_id).execute()
    except Exception:
        pass
    return created


def upload_pdf_with_config(
    file_path: str,
    folder_id: str,
    display_name: str,
    token_path: str,
    scopes: list[str],
    drive_service=None,
    use_cached_service: bool = False,
) -> dict:
    service = drive_service or get_drive_service_from_config(token_path, scopes, use_cache=use_cached_service)
    metadata = {
        'name': display_name,
        'parents': [folder_id],
    }
    media = MediaFileUpload(file_path, mimetype='application/pdf', resumable=False)
    try:
        return service.files().create(
            body=metadata,
            media_body=media,
            fields='id,name,webViewLink'
        ).execute()
    except ServerNotFoundError as exc:
        raise TransportError(f'Gagal upload ke Google Drive API: {exc}') from exc


def upload_pdf(file_path: str, folder_id: str, display_name: str) -> dict:
    return upload_pdf_with_config(
        file_path,
        folder_id,
        display_name,
        current_app.config['GOOGLE_TOKEN_PATH'],
        current_app.config['DRIVE_SCOPES'],
    )


def extract_drive_file_id(value: str | None) -> str | None:
    text = (value or '').strip()
    if not text:
        return None
    patterns = [
        r'/file/d/([a-zA-Z0-9_-]+)',
        r'[?&]id=([a-zA-Z0-9_-]+)',
        r'open\?id=([a-zA-Z0-9_-]+)',
        r'uc\?id=([a-zA-Z0-9_-]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    # Google Forms upload cells can contain one or more bare Drive URLs. If the
    # cell is already a raw file id, accept it cautiously.
    if re.fullmatch(r'[a-zA-Z0-9_-]{20,}', text):
        return text
    return None


def download_drive_file_with_config(
    file_ref: str,
    output_path: str,
    token_path: str,
    scopes: list[str],
    drive_service=None,
    use_cached_service: bool = False,
) -> str:
    file_id = extract_drive_file_id(file_ref)
    if not file_id:
        raise DriveConfigurationError('Link/ID foto peserta tidak dikenali.')
    service = drive_service or get_drive_service_from_config(token_path, scopes, use_cache=use_cached_service)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        request = service.files().get_media(fileId=file_id)
        with target.open('wb') as handle:
            downloader = MediaIoBaseDownload(handle, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
        return str(target)
    except ServerNotFoundError as exc:
        raise TransportError(f'Gagal download foto dari Google Drive API: {exc}') from exc


def download_drive_file(file_ref: str, output_path: str) -> str:
    return download_drive_file_with_config(
        file_ref,
        output_path,
        current_app.config['GOOGLE_TOKEN_PATH'],
        current_app.config['DRIVE_SCOPES'],
    )
