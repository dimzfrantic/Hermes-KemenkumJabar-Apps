from __future__ import annotations

import re
import socket
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from flask import current_app
from google.auth.exceptions import TransportError
from googleapiclient.discovery import build
from httplib2.error import ServerNotFoundError

from services.google_auth import ensure_required_scopes, load_authorized_user_credentials


class SheetConfigurationError(RuntimeError):
    pass


@dataclass
class ParsedSheet:
    spreadsheet_id: str
    spreadsheet_title: str
    sheet_names: list[str]
    selected_sheet: str
    headers: list[str]
    rows: list[dict]


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
    for host in ('oauth2.googleapis.com', 'sheets.googleapis.com'):
        _resolve_host_with_retry(host)


def normalize_spreadsheet_input(raw_value: str) -> str:
    value = (raw_value or '').strip()
    if not value:
        raise SheetConfigurationError('Spreadsheet Google Form Response wajib diisi.')
    if 'docs.google.com' not in value:
        return value
    match = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', value)
    if match:
        return match.group(1)
    raise SheetConfigurationError('Link Google Sheet tidak dikenali. Gunakan link spreadsheet atau Spreadsheet ID yang valid.')


def _cache_key(token_path: str, scopes: list[str]) -> tuple[str, tuple[str, ...]]:
    return (str(Path(token_path).expanduser().resolve()), tuple(scopes))


def load_credentials_from_path(token_path: str, scopes: list[str]) -> Credentials:
    token_file = Path(token_path)
    if not token_file.exists():
        raise SheetConfigurationError(f'Token Google tidak ditemukan di {token_file}')
    try:
        creds = load_authorized_user_credentials(str(token_file))
        ensure_required_scopes(creds, scopes, 'Token Google Sheets')
        return creds
    except FileNotFoundError:
        raise SheetConfigurationError(f'Token Google tidak ditemukan di {token_file}')
    except RuntimeError as exc:
        raise SheetConfigurationError(str(exc)) from exc


def get_sheets_service_from_config(token_path: str, scopes: list[str], use_cache: bool = False):
    cache = None
    key = None
    if use_cache:
        cache = getattr(_THREAD_LOCAL, 'sheets_services', None)
        if cache is None:
            cache = {}
            _THREAD_LOCAL.sheets_services = cache
        key = _cache_key(token_path, scopes)
        if key in cache:
            return cache[key]
    creds = load_credentials_from_path(token_path, scopes)
    _warm_google_dns()
    service = build('sheets', 'v4', credentials=creds)
    if use_cache and cache is not None and key is not None:
        cache[key] = service
    return service


def get_sheets_service():
    return get_sheets_service_from_config(
        current_app.config['GOOGLE_TOKEN_PATH'],
        current_app.config['SHEETS_SCOPES'],
    )


def fetch_form_rows(
    spreadsheet_id: str,
    worksheet_name: str | None = None,
    token_path: str = '',
    scopes: list[str] | None = None,
    service=None,
    use_cached_service: bool = False,
) -> ParsedSheet:
    normalized_id = normalize_spreadsheet_input(spreadsheet_id)
    sheets_service = service or get_sheets_service_from_config(
        token_path or current_app.config['GOOGLE_TOKEN_PATH'],
        scopes or list(current_app.config['SHEETS_SCOPES']),
        use_cache=use_cached_service,
    )
    try:
        metadata = sheets_service.spreadsheets().get(spreadsheetId=normalized_id).execute()
    except ServerNotFoundError as exc:
        raise TransportError(f'Gagal terhubung ke Google Sheets API: {exc}') from exc
    spreadsheet_title = metadata.get('properties', {}).get('title') or normalized_id
    sheet_names = [sheet.get('properties', {}).get('title', '') for sheet in metadata.get('sheets', []) if sheet.get('properties', {}).get('title')]
    if not sheet_names:
        raise SheetConfigurationError('Spreadsheet tidak memiliki worksheet yang dapat dibaca.')

    selected_sheet = worksheet_name or sheet_names[0]
    if selected_sheet not in sheet_names:
        raise SheetConfigurationError(f'Sheet {selected_sheet} tidak ditemukan pada spreadsheet response.')

    range_name = f"'{selected_sheet}'"
    try:
        values = sheets_service.spreadsheets().values().get(
            spreadsheetId=normalized_id,
            range=range_name,
        ).execute().get('values', [])
    except ServerNotFoundError as exc:
        raise TransportError(f'Gagal mengambil data Google Sheets: {exc}') from exc
    if not values:
        raise SheetConfigurationError('Spreadsheet response belum memiliki data.')

    headers = [str(cell).strip() if cell is not None else '' for cell in values[0]]
    if not any(headers):
        raise SheetConfigurationError('Header spreadsheet response pada baris pertama kosong.')

    normalized_headers = []
    seen = {}
    for index, header in enumerate(headers, start=1):
        value = header or f'Kolom {index}'
        if value in seen:
            seen[value] += 1
            value = f'{value} ({seen[value]})'
        else:
            seen[value] = 1
        normalized_headers.append(value)

    rows = []
    for row_number, row_values in enumerate(values[1:], start=2):
        row_dict = {}
        for index, header in enumerate(normalized_headers):
            row_dict[header] = str(row_values[index]).strip() if index < len(row_values) and row_values[index] is not None else ''
        if not any(row_dict.values()):
            continue
        row_dict['_row_number'] = row_number
        rows.append(row_dict)

    return ParsedSheet(
        spreadsheet_id=normalized_id,
        spreadsheet_title=spreadsheet_title,
        sheet_names=sheet_names,
        selected_sheet=selected_sheet,
        headers=normalized_headers,
        rows=rows,
    )
