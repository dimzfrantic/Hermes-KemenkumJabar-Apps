#!/usr/bin/env python3
"""
Incident Writer - PostgreSQL Incident Tracking untuk Kementerian Hukum Jawa Barat
Location: /home/ubnt/incidents/
"""

import sys
import os
import argparse
import re
import json
import mimetypes
from datetime import datetime
from pathlib import Path

# Google Drive imports
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import incident_db

# ============== CONFIGURATION ==============
SHEET_NAME = 'incident_log'
HISTORY_SHEET_NAME = 'incident_history'
ARCHIVE_SHEET_NAME = 'incident_archive'
ACTIVE_STATUSES = {'OPEN', 'IN_PROGRESS', 'PENDING'}
TERMINAL_STATUSES = {'RESOLVED', 'CLOSED'}
EXPECTED_HEADERS = [
    'ticket_code',
    'created_at',
    'lokasi',
    'masalah',
    'pelapor',
    'status',
    'durasi',
    'bukti_awal',
    'update_terakhir',
    'alias',
    'ditangani_oleh',
    'alasan_pending',
    'catatan_terakhir',
    'bukti_resolve',
    'folder_bukti'
]
HISTORY_HEADERS = [
    'update_id',
    'ticket_code',
    'alias',
    'update_time',
    'action',
    'status_before',
    'status_after',
    'ditangani_oleh',
    'alasan_pending',
    'catatan_terakhir',
    'catatan',
    'raw_message',
    'bukti_awal',
    'bukti_resolve',
    'folder_bukti',
    'bukti_status',
    'bukti_baru'
]
ARCHIVE_HEADERS = [
    'ticket_code',
    'created_at',
    'lokasi',
    'masalah',
    'pelapor',
    'status',
    'durasi',
    'bukti_awal',
    'update_terakhir',
    'alias',
    'ditangani_oleh',
    'alasan_pending',
    'catatan_terakhir',
    'bukti_resolve',
    'folder_bukti',
    'archived_at',
    'source_sheet'
]

CREDS_PATH = Path('/home/ubnt/.hermes/google_token.json')
HERMES_HOME = CREDS_PATH.parent
HERMES_IMAGE_CACHE_DIRS = [
    HERMES_HOME / 'cache' / 'images',
    HERMES_HOME / 'image_cache',
]
BUKTI_ROOT_FOLDER_ID = '1nrA72hXkQT1pQ0SVbeCSftDohcs-OdEh'
BUKTI_ROOT_FOLDER_LINK = f'https://drive.google.com/drive/folders/{BUKTI_ROOT_FOLDER_ID}'
# ============== END CONFIG ==============

def refresh_dashboard_sheet():
    """Dashboard portal adalah satu-satunya dashboard aktif saat ini."""
    return True, 'dashboard portal aktif; tidak ada sinkronisasi dashboard lain yang perlu dijalankan'

def get_creds():
    """Load and refresh OAuth2 credentials for Google Drive evidence storage."""
    with open(CREDS_PATH, 'r') as f:
        token_info = json.load(f)

    from google.oauth2 import credentials as oauth2_credentials
    from google.auth.transport import requests as google_requests

    creds = oauth2_credentials.Credentials.from_authorized_user_info(token_info)

    if not creds.valid or creds.expired:
        request = google_requests.Request()
        creds.refresh(request)
        new_token_info = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": list(creds.scopes) if creds.scopes else [],
            "universe_domain": creds.universe_domain,
            "expiry": creds.expiry.isoformat() if creds.expiry else None
        }
        with open(CREDS_PATH, 'w') as f:
            json.dump(new_token_info, f, indent=2)
    
    return creds


def get_drive_service():
    """Get authenticated Google Drive service."""
    creds = get_creds()
    return build('drive', 'v3', credentials=creds)


def sanitize_drive_name(value, fallback='Bukti Incident'):
    """Sanitize a folder name for Google Drive."""
    cleaned = re.sub(r'[\\/:*?"<>|]+', ' ', str(value or '')).strip()
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned[:120] if cleaned else fallback


def ensure_ticket_bukti_folder(ticket_code, alias, lokasi, existing_link=''):
    """Ensure one evidence folder exists for a ticket and return its link."""
    if existing_link:
        return existing_link

    service = get_drive_service()
    folder_name = sanitize_drive_name(f'{ticket_code} - tiket {alias} - {lokasi}', fallback=ticket_code)
    escaped_folder_name = folder_name.replace("'", "\\'")
    query = (
        f"name = '{escaped_folder_name}' "
        f"and '{BUKTI_ROOT_FOLDER_ID}' in parents "
        "and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    )
    results = service.files().list(
        q=query,
        spaces='drive',
        pageSize=1,
        fields='files(id, name, webViewLink)'
    ).execute()
    files = results.get('files', [])
    if files:
        return files[0].get('webViewLink') or f"https://drive.google.com/drive/folders/{files[0]['id']}"

    metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [BUKTI_ROOT_FOLDER_ID],
    }
    created = service.files().create(
        body=metadata,
        fields='id, name, webViewLink'
    ).execute()
    return created.get('webViewLink') or f"https://drive.google.com/drive/folders/{created['id']}"


def extract_drive_id(value):
    """Extract Google Drive file/folder ID from a Drive URL or raw ID."""
    raw = str(value or '').strip()
    if not raw:
        return ''
    match = re.search(r'/folders/([A-Za-z0-9_-]+)', raw)
    if match:
        return match.group(1)
    match = re.search(r'[?&]id=([A-Za-z0-9_-]+)', raw)
    if match:
        return match.group(1)
    if re.fullmatch(r'[A-Za-z0-9_-]{10,}', raw):
        return raw
    return ''


def merge_link_values(existing_value, new_values):
    """Merge evidence links while preserving order and uniqueness."""
    merged = []
    seen = set()
    for raw in [existing_value or ''] + list(new_values or []):
        for part in re.split(r'\s*\|\s*|\s*;\s*|\s*\n\s*', str(raw or '').strip()):
            value = part.strip()
            if not value or value in seen:
                continue
            merged.append(value)
            seen.add(value)
    return ' | '.join(merged)


def count_link_values(value):
    """Count distinct evidence links stored in a merged field."""
    return len([part for part in re.split(r'\s*\|\s*|\s*;\s*|\s*\n\s*', str(value or '').strip()) if part.strip()])


def build_evidence_filename(ticket_code, status_label, event_time, source_path, label='bukti', index=1):
    """Build a Drive-friendly evidence filename with status and timestamp."""
    source_name = Path(str(source_path or '')).name or f'{ticket_code}-{label}'
    stem = Path(source_name).stem or f'{ticket_code}-{label}'
    suffix = Path(source_name).suffix or ''
    normalized_status = re.sub(r'[^A-Za-z0-9]+', '_', str(status_label or 'OPEN').upper()).strip('_') or 'OPEN'
    normalized_label = re.sub(r'[^A-Za-z0-9]+', '_', str(label or 'bukti').lower()).strip('_') or 'bukti'
    safe_stem = sanitize_drive_name(stem, fallback=f'{ticket_code}-{normalized_label}').replace(' ', '_')
    timestamp = str(event_time or datetime.now().strftime('%d-%m-%Y %H:%M:%S')).replace(':', '-').replace(' ', '_')
    return sanitize_drive_name(
        f'{ticket_code}_{normalized_status}_{timestamp}_{normalized_label}_{index}_{safe_stem}{suffix}',
        fallback=f'{ticket_code}_{normalized_status}_{timestamp}_{normalized_label}_{index}{suffix}'
    )


def is_hermes_cached_image(path):
    """Return True when path points to a Hermes image cache file."""
    try:
        resolved = Path(path).resolve()
    except Exception:
        return False
    for cache_dir in HERMES_IMAGE_CACHE_DIRS:
        try:
            resolved.relative_to(cache_dir.resolve())
            return True
        except Exception:
            continue
    return False


def delete_cached_image_if_safe(path):
    """Delete a Hermes cached image after successful upload, if applicable."""
    if not is_hermes_cached_image(path):
        return False
    file_path = Path(path)
    try:
        file_path.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def upload_files_to_drive_folder(file_paths, folder_link, ticket_code, label='bukti', status_label='OPEN', event_time=''):
    """Upload one or more local files to a ticket evidence folder and return links."""
    folder_id = extract_drive_id(folder_link)
    if not folder_id:
        raise ValueError('Folder bukti tidak valid atau belum tersedia')

    uploads = []
    service = get_drive_service()
    for index, raw_path in enumerate(file_paths or [], 1):
        path = Path(str(raw_path or '').strip())
        if not raw_path:
            continue
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f'File bukti tidak ditemukan: {path}')
        mime_type = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
        metadata = {
            'name': build_evidence_filename(ticket_code, status_label, event_time, path, label=label, index=index),
            'parents': [folder_id],
        }
        media = MediaFileUpload(str(path), mimetype=mime_type, resumable=False)
        created = service.files().create(
            body=metadata,
            media_body=media,
            fields='id, name, webViewLink'
        ).execute()
        uploads.append(created.get('webViewLink') or f"https://drive.google.com/file/d/{created['id']}/view")
        delete_cached_image_if_safe(path)
    return uploads


def get_sheet(sheet_name=SHEET_NAME, expected_headers=EXPECTED_HEADERS):
    """Get logical incident store handle backed by PostgreSQL."""
    return incident_db.get_db_sheet(sheet_name, expected_headers)

def get_history_sheet():
    """Get logical incident history store backed by PostgreSQL."""
    return incident_db.get_db_sheet(HISTORY_SHEET_NAME, HISTORY_HEADERS)

def get_archive_sheet():
    """Get logical archived incident store backed by PostgreSQL."""
    return incident_db.get_db_sheet(ARCHIVE_SHEET_NAME, ARCHIVE_HEADERS)

def row_from_record(record, headers):
    """Build row values from a record dict using the given header order."""
    return [record.get(header, '') for header in headers]

def find_record(records, ticket_code):
    """Find one record by ticket code and return (row_idx, record)."""
    for i, row in enumerate(records, 2):
        if str(row.get('ticket_code', '')).upper() == ticket_code.upper():
            return i, row
    return None, None

def get_all_records(include_archive=False):
    """Read active records and optionally archive records from PostgreSQL."""
    return incident_db.get_all_records(include_archive=include_archive)


def get_history_records(ticket_code=None):
    """Read incident history rows from PostgreSQL."""
    return incident_db.get_history_records(ticket_code=ticket_code)

def upsert_archive_record(record, archived_at, source_sheet=SHEET_NAME):
    """Create or update one archived record by ticket code."""
    archive_sheet = get_archive_sheet()
    archive_records = archive_sheet.get_all_records()
    archive_row_idx, _ = find_record(archive_records, record.get('ticket_code', ''))
    archive_record = dict(record)
    archive_record['archived_at'] = archived_at
    archive_record['source_sheet'] = source_sheet
    archive_row = row_from_record(archive_record, ARCHIVE_HEADERS)
    if archive_row_idx is None:
        archive_sheet.append_row(archive_row)
    else:
        end_col = chr(64 + len(ARCHIVE_HEADERS))
        archive_sheet.update([archive_row], 'A' + str(archive_row_idx) + ':' + end_col + str(archive_row_idx))

def move_record_to_archive(active_sheet, row_idx, record, archived_at):
    """Move one updated terminal ticket from incident_log to incident_archive."""
    upsert_archive_record(record, archived_at, SHEET_NAME)
    active_sheet.delete_rows(row_idx)

def restore_record_from_archive(active_sheet, archive_sheet, archive_row_idx, record):
    """Restore one archived ticket back into incident_log and remove archive metadata."""
    active_sheet.append_row(row_from_record(record, EXPECTED_HEADERS))
    archive_sheet.delete_rows(archive_row_idx)

def append_history_row(ticket_code, alias, action, status_before, status_after,
                       handled_by, pending_reason, catatan_terakhir, note, raw_message,
                       bukti_awal='', bukti_resolve='', folder_bukti='', bukti_status='', bukti_baru=''): 
    """Append one history entry after the main incident row has been written successfully."""
    history_sheet = get_history_sheet()
    update_time = datetime.now().strftime('%d-%m-%Y %H:%M:%S')
    update_id = ticket_code + '-' + datetime.now().strftime('%Y%m%d%H%M%S%f')
    row = [
        update_id,
        ticket_code,
        alias,
        update_time,
        action,
        status_before,
        status_after,
        handled_by,
        pending_reason,
        catatan_terakhir,
        note,
        raw_message,
        bukti_awal,
        bukti_resolve,
        folder_bukti,
        bukti_status,
        bukti_baru,
    ]
    history_sheet.append_row(row)

def recalculate_aliases(sheet):
    """Recalculate all aliases after a new ticket is created.
    
    Alias = position in sorted-by-date order (newest = 1).
    This ensures aliases are stable and unique.
    """
    records = sheet.get_all_records()
    if not records:
        return
    
    def get_date(row):
        try:
            return datetime.strptime(row.get("created_at", ""), "%d-%m-%Y %H:%M:%S")
        except:
            return datetime.min
    
    sorted_indices = sorted(
        enumerate(records, 2),
        key=lambda x: get_date(x[1]),
        reverse=True
    )
    
    for new_alias, (row_idx, row) in enumerate(sorted_indices, 1):
        sheet.update_cell(row_idx, 9, new_alias)

def generate_ticket_code(category='NET'):
    """Generate next ticket code and next global alias across active, archived, and history records."""
    active_records, archive_records = get_all_records(include_archive=True)
    history_records = get_history_sheet().get_all_records()
    records = active_records + archive_records + history_records

    prefix = category.upper()
    today = datetime.now().strftime('%Y%m%d')

    max_daily_num = 0
    max_alias_num = 0
    for row in records:
        code = str(row.get('ticket_code', ''))
        match = re.match(r'^(\w+)-(\d{8})-(\d+)$', code)
        if match and match.group(2) == today:
            try:
                num = int(match.group(3))
                max_daily_num = max(max_daily_num, num)
            except (ValueError, IndexError):
                pass
        try:
            max_alias_num = max(max_alias_num, int(row.get('alias', 0) or 0))
        except (TypeError, ValueError):
            pass

    new_daily_num = max_daily_num + 1
    new_alias_num = max_alias_num + 1
    return prefix + '-' + today + '-' + str(new_daily_num).zfill(3), new_alias_num

def detect_category(message):
    """Detect incident category from message."""
    msg_lower = message.lower()
    
    if any(kw in msg_lower for kw in ['wifi', 'internet', 'jaringan', 'router', 'modem', 'lan', 'putus', 'mati']):
        return 'NET'
    elif any(kw in msg_lower for kw in ['app', 'aplikasi', 'sistem', 'web', 'website', 'server', 'database']):
        return 'APP'
    elif any(kw in msg_lower for kw in ['komputer', 'laptop', 'printer', 'hardware', 'pc', 'monitor']):
        return 'HW'
    return 'INC'

def parse_location(message):
    """Extract location from message."""
    msg_lower = message.lower()
    location = 'KANWIL'
    msg_clean = re.sub(r'\s+', ' ', msg_lower).strip()
    
    # Problem keywords that should NOT be part of location
    problem_words = {'mati', 'total', 'rusak', 'putus', 'lemot', 'error',
                     'booting', 'restart', 'hang', 'lambat', 'pelosi',
                     'kecepatan', 'jaringan', 'internet', 'wifi', 'laptop',
                     'komputer', 'printer', 'hp', 'handphone',
                     'tidak', 'menyala', 'fungsi', 'berfungsi',
                     'atas', 'nama'}  # 'atas nama X' pattern indicators
    
    # Handle "diruang X" or "diruangan X" (NO space between di and ruang)
    diruang_match = re.search(r'\bdiruang(?:an)?\s+([a-zA-Z]{2,}(?:\s+[a-zA-Z]+){0,4})', msg_clean)
    if diruang_match:
        room_name = diruang_match.group(1).strip()
        words = room_name.split()
        # Filter out problem words and stop at "atas nama" pattern
        filtered = []
        for w in words:
            if w.lower() in {'atas', 'nama'}:
                break  # Stop at "atas nama" - everything after is person name
            filtered.append(w)
        if filtered:
            location = 'RUANG ' + ' '.join(filtered).upper()
            return location
    
    # Handle "ruangJdih" or "diruangJdih" (NO space after ruang)
    ruang_split = re.split(r'ruang(?:an)?', msg_clean)
    if len(ruang_split) > 1:
        remainder = ruang_split[1]
        if remainder and remainder[0].isalpha():
            word_match = re.match(r'([a-zA-Z]{2,})', remainder)
            if word_match:
                location = 'RUANG ' + word_match.group(1).upper()
                return location
    
    # Handle "ruang X" or "ruangan X" with space
    room_match = re.search(r'\bruang(?:an)?\.?\s+([a-zA-Z]{2,}(?:\s+[a-zA-Z]+){0,4})\b', msg_clean)
    if room_match:
        room_name = room_match.group(1).strip()
        # Split into words and filter out problem words
        words = room_name.split()
        words = [w for w in words if w.lower() not in problem_words]
        if words:
            location = 'RUANG ' + ' '.join(words).upper()
            return location
    
    # Handle "di ruang X" or "di ruangan X"
    di_room_match = re.search(r'\bdi\s+ruang(?:an)?\.?\s+([a-zA-Z]{2,}(?:\s+[a-zA-Z]+){0,4})\b', msg_clean)
    if di_room_match:
        room_name = di_room_match.group(1).strip()
        words = room_name.split()
        words = [w for w in words if w.lower() not in problem_words]
        if words:
            location = 'RUANG ' + ' '.join(words).upper()
            return location
    
    # Handle "lantai X" or "lt X"
    floor_match = re.search(r'\b(?:lantai|lt)\.?\s*(\d+)\b', msg_clean)
    if floor_match:
        location = 'Lantai ' + floor_match.group(1)
        return location
    
    # Handle "di lantai X"
    di_floor_match = re.search(r'\bdi\s+(?:lantai|lt)\.?\s*(\d+)\b', msg_clean)
    if di_floor_match:
        location = 'Lantai ' + di_floor_match.group(1)
        return location
    
    # Handle "kanwil" or "kantor"
    if re.search(r'\b(?:kanwil|kantor)\b', msg_clean):
        location = 'KANWIL'
        return location
    
    return location

def parse_incident(message):
    """Parse incident details from natural language message."""
    msg_lower = message.lower()
    invalid_reporter_words = {
        'mati', 'total', 'rusak', 'putus', 'lemot', 'error', 'gangguan',
        'down', 'hang', 'lambat', 'booting', 'restart', 'tidak', 'menyala',
        'fungsi', 'berfungsi', 'printer', 'komputer', 'laptop', 'monitor',
        'wifi', 'internet', 'jaringan', 'server', 'database',
    }

    # Use parse_location for location extraction
    location = parse_location(message)

    # Extract reporter from "pelapor X", "atas nama X", atau pola langsung "komputer dimas di ..."
    reporter = 'Unknown'
    atas_nama_person = None  # Store "atas nama X" for summary
    direct_name_person = None  # Store direct name pattern: "komputer dimas di ..."
    
    # Highest priority: explicit "pelapor X"
    pelapor_match = re.search(r'\bpelapor\s+([a-zA-Z]+)', msg_lower)
    if pelapor_match:
        reporter = pelapor_match.group(1).title()
    
    # Next: "atas nama X"
    atas_nama_match = re.search(r'\batas\s+nama\s+([a-zA-Z]+)', msg_lower)
    if atas_nama_match:
        atas_nama_person = atas_nama_match.group(1).title()
        if reporter == 'Unknown':
            reporter = atas_nama_person
    
    # Fallback: direct name after device keyword, e.g. "komputer dimas di ruangan jdih tidak menyala"
    if reporter == 'Unknown' and not atas_nama_match:
        direct_name_match = re.search(
            r'^\s*(?:komputer|laptop|printer|pc|monitor|hp|handphone)\s+([a-zA-Z]+)\s+(?=di\s+ruang(?:an)?\b|diruang(?:an)?\b|di\s+lantai\b|di\s+kanwil\b)',
            msg_lower
        )
        if direct_name_match:
            candidate_name = direct_name_match.group(1).strip()
            if candidate_name.lower() not in invalid_reporter_words:
                direct_name_person = candidate_name.title()
                reporter = direct_name_person

    if str(reporter).strip().lower() in invalid_reporter_words:
        reporter = 'Unknown'
        direct_name_person = None

    summary = message.strip()
    # Work on lowercase version for pattern matching
    summary_lower = summary.lower()
    
    # Remove location references from summary using EXACT parsed location
    # Build variations of the location for removal (include both ruang/ruangan like parse_location)
    loc_lower = location.lower().strip()
    if loc_lower == 'ruang jdih':
        # Special case JDIH: remove all common variants
        summary_lower = re.sub(r'\bruangjdih\b', '', summary_lower, flags=re.IGNORECASE)
        summary_lower = re.sub(r'\bdiruangjdih\b', '', summary_lower, flags=re.IGNORECASE)
        summary_lower = re.sub(r'\bdi\s+ruang(?:an)?\.?\s+jdih\b', '', summary_lower, flags=re.IGNORECASE)
        summary_lower = re.sub(r'\bruang(?:an)?\.?\s+jdih\b', '', summary_lower, flags=re.IGNORECASE)
    elif loc_lower.startswith('ruang '):
        room_phrase = loc_lower[5:].strip()  # "imigrasi" or "rapat suhendro"
        room_words = room_phrase.split()
        # Remove "diruang/diruangan X Y Z" pattern
        summary_lower = re.sub(r'\bdiruang(?:an)?\s+' + re.escape(room_phrase) + r'\b', '', summary_lower, flags=re.IGNORECASE)
        # Remove "di ruangan/ruang X Y Z" (up to 5 words)
        summary_lower = re.sub(r'\bdi\s+ruang(?:an)?\.?\s+' + re.escape(room_phrase) + r'\b', '', summary_lower)
        # Also remove just "ruangan/ruang X Y Z"
        summary_lower = re.sub(r'\bruang(?:an)?\.?\s+' + re.escape(room_phrase) + r'\b', '', summary_lower)
        # Also try with just first 2-3 words in case location has more
        if len(room_words) >= 2:
            summary_lower = re.sub(r'\bdi\s+ruang(?:an)?\.?\s+' + ' '.join(room_words[:2]) + r'(?:\s+\w+){0,3}\b', '', summary_lower)
            summary_lower = re.sub(r'\bruang(?:an)?\.?\s+' + ' '.join(room_words[:2]) + r'(?:\s+\w+){0,3}\b', '', summary_lower)
    elif loc_lower.startswith('lantai '):
        summary_lower = re.sub(r'\bdi\s+' + re.escape(loc_lower) + r'\b', '', summary_lower)
        summary_lower = re.sub(r'\b' + re.escape(loc_lower) + r'\b', '', summary_lower)
    elif loc_lower == 'kanwil':
        summary_lower = re.sub(r'\bdi\s+kanwil\b', '', summary_lower)
    
    # Remove direct name after device keyword, e.g. "komputer dimas di ..."
    if direct_name_person:
        summary_lower = re.sub(
            r'^(\s*(?:komputer|laptop|printer|pc|monitor|hp|handphone))\s+' + re.escape(direct_name_person.lower()) + r'\b',
            r'\1',
            summary_lower,
            flags=re.IGNORECASE
        )
    # Remove "atas nama X" and the name itself from summary
    if atas_nama_match:
        summary_lower = re.sub(r'\batas\s+nama\s+[a-zA-Z]+\b', '', summary_lower)
    # Remove "pelapor X" from summary (metadata, not part of the problem)
    summary_lower = re.sub(r'\bpelapor\s+[a-zA-Z]+\.?\s*', '', summary_lower)
    # Clean up multiple spaces
    summary = re.sub(r'\s+', ' ', summary_lower).strip()
    # Remove trailing punctuation
    summary = re.sub(r'[\.\,]$', '', summary).strip()
    # Jika ada nama person dari "atas nama X" atau pola langsung, tampilkan di summary dalam tanda kurung
    person_for_summary = atas_nama_person or direct_name_person
    if person_for_summary and ('(' + person_for_summary + ')') not in summary:
        summary = summary + ' (' + person_for_summary + ')'

    return {
        'location': location,
        'reporter': reporter,
        'summary': summary,
        'category': detect_category(message)
    }

def parse_update_message(message):
    """Parse natural language status update like 'tiket 74 selesai oleh randy'."""
    parsed = {
        'ticket': None,
        'status': None,
        'handled_by': None,
        'use_sender_name_as_handler': False,
        'note': '',
    }

    if not message:
        return parsed

    msg_lower = re.sub(r'\s+', ' ', message.lower()).strip()

    ticket_match = re.search(r'\btiket\s+(\d+)\b', msg_lower)
    if ticket_match:
        parsed['ticket'] = 'tiket ' + ticket_match.group(1)

    if any(keyword in msg_lower for keyword in ['pending', 'ditunda', 'tertunda', 'menunggu']):
        parsed['status'] = 'PENDING'
    elif any(keyword in msg_lower for keyword in ['selesai', 'resolved', 'resolve', 'done', 'fix', 'beres', 'normal kembali', 'sudah normal', 'sudah diganti', 'sudah diperbaiki', 'berhasil diperbaiki']):
        parsed['status'] = 'RESOLVED'
    elif any(keyword in msg_lower for keyword in ['closed', 'close', 'tutup', 'ditutup']):
        parsed['status'] = 'CLOSED'
    elif any(keyword in msg_lower for keyword in ['in progress', 'in progres', 'progress', 'progres', 'ongoing', 'dikerjakan', 'proses', 'ditangani', 'dicek', 'diperiksa', 'mengganti', 'ganti', 'memperbaiki', 'diperbaiki', 'mengatasi', 'penanganan']):
        parsed['status'] = 'IN_PROGRESS'

    explicit_handler_match = re.search(r'\boleh\s+([a-zA-Z][a-zA-Z\s]{0,60})\b', message, re.IGNORECASE)
    if explicit_handler_match:
        candidate = re.sub(r'\s+', ' ', explicit_handler_match.group(1)).strip(' ,.-')
        normalized_candidate = re.sub(r'^oleh\s+', '', candidate, flags=re.IGNORECASE).strip()
        if normalized_candidate:
            if normalized_candidate.lower() == 'saya':
                parsed['use_sender_name_as_handler'] = True
            else:
                parsed['handled_by'] = normalized_candidate.title()

    progress_or_work_pattern = r'\btiket\s+\d+\s+(?:sedang\s+)?(?:dikerjakan|ditangani|proses|progress|progres|in\s+progress|in\s+progres|dicek|diperiksa|mengganti|ganti|memperbaiki|diperbaiki|mengatasi|penanganan)\b'
    resolved_pattern = r'\btiket\s+\d+\s+(?:sudah\s+)?(?:selesai|resolved|resolve|beres|sudah\s+diganti|sudah\s+diperbaiki|berhasil\s+diperbaiki)\b'

    if not parsed['handled_by'] and parsed['status'] == 'IN_PROGRESS':
        detail_after_progress_match = re.search(progress_or_work_pattern + r'\s*(.*)$', message, re.IGNORECASE)
        detail_after_progress = detail_after_progress_match.group(1).strip(' ,.-') if detail_after_progress_match else ''
        lowered_detail_after_progress = detail_after_progress.lower()
        invalid_handler_prefixes = (
            'dengan ', 'menggunakan ', 'pakai ', 'memakai ',
            'penggantian ', 'ganti ', 'pergantian ', 'sambil ', 'untuk ', 'karena '
        )
        if detail_after_progress:
            if lowered_detail_after_progress == 'saya':
                parsed['use_sender_name_as_handler'] = True
            elif lowered_detail_after_progress.startswith('oleh '):
                explicit_handler_after_progress = re.sub(r'^oleh\s+', '', detail_after_progress, flags=re.IGNORECASE).strip()
                if explicit_handler_after_progress:
                    parsed['handled_by'] = explicit_handler_after_progress.title()
            elif lowered_detail_after_progress.startswith(invalid_handler_prefixes):
                parsed['use_sender_name_as_handler'] = True
            else:
                parsed['use_sender_name_as_handler'] = True
        elif re.search(progress_or_work_pattern, message, re.IGNORECASE):
            parsed['use_sender_name_as_handler'] = True

    if not parsed['handled_by'] and not parsed['use_sender_name_as_handler'] and parsed['status'] == 'RESOLVED' and re.search(resolved_pattern, message, re.IGNORECASE):
        parsed['use_sender_name_as_handler'] = True

    pending_reason_match = re.search(r'\bpending\b[\s,:-]*(.+)$', message, re.IGNORECASE)
    if pending_reason_match:
        parsed['note'] = pending_reason_match.group(1).strip(' ,.-')
    elif parsed['status'] == 'PENDING':
        waiting_reason_match = re.search(r'\b(?:menunggu|ditunda|tertunda)\s+(.+)$', message, re.IGNORECASE)
        if waiting_reason_match:
            parsed['note'] = waiting_reason_match.group(1).strip()
    elif parsed['status'] in ['IN_PROGRESS', 'RESOLVED']:
        detail_match = re.search(
            r'\btiket\s+\d+\s+(?:sedang\s+)?(?P<action>dikerjakan|ditangani|proses|dicek|diperiksa|mengganti|ganti|memperbaiki|diperbaiki|mengatasi|penanganan|selesai|resolved|resolve|beres|sudah\s+diganti|sudah\s+diperbaiki|berhasil\s+diperbaiki)\s*(?P<detail>.*)$',
            message,
            re.IGNORECASE,
        )
        if detail_match:
            action = re.sub(r'\s+', ' ', detail_match.group('action')).strip()
            detail = detail_match.group('detail').strip(' ,.-')
            lowered_detail = detail.lower()
            generic_resolved_tails = {'', 'oleh', 'oleh saya'}
            detail_without_handler = re.sub(r'\s+oleh\s+[a-zA-Z][a-zA-Z\s]{0,60}$', '', detail, flags=re.IGNORECASE).strip(' ,.-')
            action_words_to_preserve = {'mengganti', 'ganti', 'memperbaiki', 'diperbaiki', 'mengatasi', 'penanganan'}
            if detail and lowered_detail != 'saya' and not lowered_detail.startswith('oleh '):
                if detail_without_handler and detail_without_handler != detail and action.lower() in action_words_to_preserve:
                    parsed['note'] = action + ' ' + detail_without_handler
                else:
                    parsed['note'] = detail_without_handler or detail
            elif parsed['status'] == 'RESOLVED' and lowered_detail in generic_resolved_tails:
                parsed['note'] = ''

    return parsed

def cmd_write(args):
    """Create new incident."""
    sheet = get_sheet()
    
    if hasattr(args, 'category') and getattr(args, 'category', ''):
        category = str(getattr(args, 'category', '')).strip().upper()
    elif hasattr(args, 'message'):
        category = detect_category(args.message)
    else:
        category = 'INC'
    ticket_code, global_num = generate_ticket_code(category)
    
    now = datetime.now().strftime('%d-%m-%Y %H:%M:%S')
    
    if hasattr(args, 'message') and args.message:
        # Approach #2: Gunakan parsing yang sudah disempurnakan
        parsed = parse_incident(args.message)
        location = parsed['location']
        summary = parsed['summary']
        reporter = parsed['reporter']
    else:
        location = args.location if hasattr(args, 'location') else 'Unknown'
        summary = args.summary if hasattr(args, 'summary') else args.message
        reporter = args.reporter if hasattr(args, 'reporter') else 'Unknown'
    
    # Only override with Signal sender if reporter could not be extracted (reporter is 'Unknown')
    sender_from_env = os.environ.get('HERMES_SIGNAL_SENDER', '')
    sender_from_arg = getattr(args, 'sender', '') or ''
    effective_sender = sender_from_arg or sender_from_env
    if reporter == 'Unknown' and effective_sender:
        reporter = effective_sender
    bukti_awal = getattr(args, 'bukti_awal', '') or ''
    folder_bukti_error = ''
    uploaded_bukti_awal = []
    try:
        folder_bukti = ensure_ticket_bukti_folder(ticket_code, global_num, location)
    except Exception as exc:
        folder_bukti = ''
        folder_bukti_error = str(exc)

    try:
        uploaded_bukti_awal = upload_files_to_drive_folder(
            getattr(args, 'bukti_awal_files', []) or [],
            folder_bukti,
            ticket_code,
            label='bukti-awal',
            status_label='OPEN',
            event_time=now,
        )
        bukti_awal = merge_link_values(bukti_awal, uploaded_bukti_awal)
    except Exception as exc:
        folder_bukti_error = folder_bukti_error or str(exc)
    
    row = [
        ticket_code,
        now,
        location,
        summary,
        reporter,
        'OPEN',
        '',
        bukti_awal,
        now,
        global_num,
        '',
        '',
        '',
        '',
        folder_bukti,
    ]
    
    sheet.append_row(row)
    append_history_row(
        ticket_code=ticket_code,
        alias=global_num,
        action='CREATE',
        status_before='',
        status_after='OPEN',
        handled_by='',
        pending_reason='',
        catatan_terakhir='Tiket dibuat',
        note=summary,
        raw_message=getattr(args, 'message', '') or summary,
        bukti_awal=bukti_awal,
        bukti_resolve='',
        folder_bukti=folder_bukti,
        bukti_status='OPEN' if uploaded_bukti_awal else '',
        bukti_baru=' | '.join(uploaded_bukti_awal),
    )

    dashboard_ok, dashboard_detail = refresh_dashboard_sheet()

    # Alias is locked to global_num - no recalculation
    alias_str = ' alias: tiket ' + str(global_num)
    folder_status = folder_bukti if folder_bukti else ('gagal dibuat otomatis (' + folder_bukti_error[:120] + ')' if folder_bukti_error else '-')
    bukti_awal_status = bukti_awal if bukti_awal else '-'

    msg = '\n[OK] Incident berhasil dibuat!\n\nTiket: ' + ticket_code + alias_str + '\nLokasi: ' + location + '\nMasalah: ' + summary[:60] + '\nPelapor: ' + reporter + '\nStatus: OPEN\nBukti awal: ' + bukti_awal_status + '\nFolder bukti: ' + folder_status + '\nFolder induk bukti: ' + BUKTI_ROOT_FOLDER_LINK + '\n\nUpdate: "tiket ' + str(global_num) + ' sudah selesai"'
    return msg

def cmd_list(args):
    """List recent incidents."""
    sheet = get_sheet()
    records = sheet.get_all_records()
    archive_records = []
    
    limit = getattr(args, 'limit', 10)
    status_filter = getattr(args, 'status', None)
    
    # Filter by status if specified
    if status_filter:
        status_filter = status_filter.upper()
        if status_filter in TERMINAL_STATUSES:
            archive_records = get_archive_sheet().get_all_records()
            records = records + archive_records
        records = [r for r in records if r.get('status', '').upper() == status_filter]
    
    if not records:
        status_word = 'berstatus ' + status_filter if status_filter else ''
        return 'Tidak ada incident ' + status_word + ' ditemukan.'
    
    sorted_records = sorted(records, key=lambda x: x.get('created_at', ''), reverse=True)
    
    status_label = 'BERSTATUS ' + status_filter if status_filter else 'TERBARU'
    lines = ['[i] DAFTAR INCIDENT ' + status_label, '='*40, 'Gunakan alias: "tiket 1", "tiket 2", dst.', '']
    
    for i, row in enumerate(sorted_records[:limit], 1):
        code = row.get('ticket_code', 'N/A')
        loc = row.get('lokasi', '-')
        masalah = row.get('masalah', '-')[:40]
        status = row.get('status', 'OPEN')
        created = row.get('created_at', '')[:16]
        durasi = row.get('durasi', '-')
        alias = row.get('alias', str(i))
        
        status_icon_map = {
            'OPEN': '[O]',
            'IN_PROGRESS': '[~]',
            'PENDING': '[!]',
            'RESOLVED': '[OK]',
            'CLOSED': '[X]'
        }
        status_icon = status_icon_map.get(status, '[?]')
        lines.append(status_icon + ' [' + code + '] alias: tiket ' + str(alias) + ' | ' + status)
        lines.append('   ' + loc + ' | ' + created + ' | ' + durasi)
        lines.append('   ' + masalah + '...')
        lines.append('')
    
    lines.append('Total: ' + str(len(sorted_records)) + ' incident')
    if not status_filter:
        lines.append('Filter: "list --status OPEN" untuk belum selesai')
    return '\n'.join(lines)

def parse_summary_message(message):
    """Parse natural language status summary request."""
    parsed = {
        'status': None,
        'mode': 'status',
    }

    if not message:
        return parsed

    msg_lower = re.sub(r'\s+', ' ', message.lower()).strip()

    if 'dashboard' in msg_lower:
        parsed['mode'] = 'dashboard'
        return parsed

    if any(keyword in msg_lower for keyword in ['petugas', 'teknisi', 'ditangani oleh']):
        parsed['mode'] = 'handlers'
        return parsed

    if any(keyword in msg_lower for keyword in ['rata-rata durasi', 'rata rata durasi', 'average durasi', 'avg durasi']):
        parsed['mode'] = 'avg_duration'
        return parsed

    if any(keyword in msg_lower for keyword in ['selesai hari ini', 'resolved hari ini', 'beres hari ini']):
        parsed['mode'] = 'resolved_today'
        parsed['status'] = 'RESOLVED'
        return parsed

    if any(keyword in msg_lower for keyword in ['sla merah', 'tiket merah', 'list tiket merah']):
        parsed['mode'] = 'urgent_red'
        return parsed

    if any(keyword in msg_lower for keyword in ['sla kuning', 'tiket kuning', 'list tiket kuning']):
        parsed['mode'] = 'urgent_yellow'
        return parsed

    if any(keyword in msg_lower for keyword in ['urgent', 'mendesak', 'butuh tindak lanjut', 'perlu tindak lanjut']):
        parsed['mode'] = 'urgent'
        return parsed

    if any(keyword in msg_lower for keyword in ['open', 'buka', 'belum selesai']):
        parsed['status'] = 'OPEN'
    elif any(keyword in msg_lower for keyword in ['progress', 'dikerjakan', 'proses', 'ditangani']):
        parsed['status'] = 'IN_PROGRESS'
    elif any(keyword in msg_lower for keyword in ['pending', 'menunggu', 'tertunda', 'ditunda']):
        parsed['status'] = 'PENDING'
    elif any(keyword in msg_lower for keyword in ['resolved', 'selesai', 'beres']):
        parsed['status'] = 'RESOLVED'
    elif any(keyword in msg_lower for keyword in ['closed', 'close', 'ditutup', 'tutup']):
        parsed['status'] = 'CLOSED'

    return parsed


def parse_duration_to_minutes(duration_text):
    """Convert strings like '1h 2m' or '46m' into integer minutes."""
    if not duration_text:
        return None
    text = str(duration_text).strip().lower()
    if not text or text in ['-', 'n/a']:
        return None

    hours = 0
    minutes = 0
    hour_match = re.search(r'(\d+)\s*h', text)
    minute_match = re.search(r'(\d+)\s*m', text)

    if hour_match:
        hours = int(hour_match.group(1))
    if minute_match:
        minutes = int(minute_match.group(1))

    if not hour_match and not minute_match and text.isdigit():
        return int(text)

    total = (hours * 60) + minutes
    return total if total >= 0 else None


def format_minutes(total_minutes):
    """Format minutes into compact human text."""
    if total_minutes is None:
        return '-'
    hours = total_minutes // 60
    minutes = total_minutes % 60
    if hours > 0:
        return str(hours) + 'h ' + str(minutes) + 'm'
    return str(minutes) + 'm'


def age_minutes_from_created(created_at, now=None):
    """Return age in minutes from created_at until now."""
    if not created_at:
        return None
    if now is None:
        now = datetime.now()
    try:
        created_dt = datetime.strptime(str(created_at).strip(), '%d-%m-%Y %H:%M:%S')
    except Exception:
        return None
    diff = now - created_dt
    return max(0, int(diff.total_seconds() / 60))


def parse_incident_dt(value):
    """Parse incident datetime string in DD-MM-YYYY HH:MM:SS format."""
    if not value:
        return None
    try:
        return datetime.strptime(str(value).strip(), '%d-%m-%Y %H:%M:%S')
    except Exception:
        return None


def build_latest_status_entry_times(history_rows):
    """Return latest entry time for each active status per ticket from history rows."""
    latest = {}
    for row in history_rows or []:
        ticket_code = str(row.get('ticket_code', '') or '').strip().upper()
        status_after = str(row.get('status_after', '') or '').strip().upper()
        update_dt = parse_incident_dt(row.get('update_time', ''))
        if not ticket_code or status_after not in ACTIVE_STATUSES or not update_dt:
            continue
        key = (ticket_code, status_after)
        prev_dt = latest.get(key)
        if prev_dt is None or update_dt > prev_dt:
            latest[key] = update_dt
    return latest


def status_stagnation_minutes(row, now, latest_status_entry_times):
    """Return stagnation minutes from the latest entry into the current active status."""
    ticket_code = str(row.get('ticket_code', '') or '').strip().upper()
    status = str(row.get('status', '') or '').strip().upper()
    start_dt = latest_status_entry_times.get((ticket_code, status))
    if not start_dt:
        start_dt = parse_incident_dt(row.get('update_terakhir', '')) or parse_incident_dt(row.get('created_at', ''))
    if not start_dt:
        return None
    return max(0, int((now - start_dt).total_seconds() / 60))


def get_sla_level_for_active_status(status, stagnation_minutes):
    """Return YELLOW/RED SLA level for active tickets or None if still normal."""
    if stagnation_minutes is None:
        return None
    status = str(status or '').strip().upper()
    if status == 'OPEN':
        return 'RED' if stagnation_minutes > 120 else 'YELLOW' if stagnation_minutes > 60 else None
    if status == 'IN_PROGRESS':
        return 'RED' if stagnation_minutes > 240 else 'YELLOW' if stagnation_minutes > 120 else None
    if status == 'PENDING':
        return 'RED' if stagnation_minutes > 1440 else 'YELLOW' if stagnation_minutes > 240 else None
    return None


def cmd_summary(args):
    """HP-friendly incident summary by status and simple analytics."""
    active_records, archive_records = get_all_records(include_archive=True)
    records = active_records + archive_records

    parsed_message = parse_summary_message(getattr(args, 'message', ''))
    status_filter = (getattr(args, 'status', None) or parsed_message.get('status') or '').upper()
    mode = getattr(args, 'mode', None) or parsed_message.get('mode') or 'status'
    limit = getattr(args, 'limit', 3)

    status_order = ['OPEN', 'IN_PROGRESS', 'PENDING', 'RESOLVED', 'CLOSED']
    counts = {status: 0 for status in status_order}
    for row in records:
        status = str(row.get('status', 'OPEN')).upper()
        if status not in counts:
            counts[status] = 0
        counts[status] += 1

    now = datetime.now()

    if mode == 'resolved_today':
        filtered = []
        for row in records:
            if str(row.get('status', '')).upper() != 'RESOLVED':
                continue
            updated_at = str(row.get('update_terakhir', '')).strip()
            try:
                updated_dt = datetime.strptime(updated_at, '%d-%m-%Y %H:%M:%S')
            except Exception:
                continue
            if updated_dt.date() == now.date():
                filtered.append(row)
        filtered = sorted(filtered, key=lambda x: x.get('update_terakhir', ''), reverse=True)
        lines = ['ringkasan | RESOLVED HARI INI | total ' + str(len(filtered))]
        for row in filtered[:limit]:
            alias = row.get('alias', '-')
            code = row.get('ticket_code', '-')
            lokasi = row.get('lokasi', '-')
            masalah = row.get('masalah', '-')
            handled_by = row.get('ditangani_oleh', '-') or '-'
            durasi = row.get('durasi', '-') or '-'
            lines.append('tiket ' + str(alias) + ' | ' + code + ' | ' + lokasi + ' | ' + masalah + ' | ' + handled_by + ' | ' + durasi)
        if not filtered:
            lines.append('tidak ada tiket selesai hari ini')
        return '\n'.join(lines)

    if mode == 'handlers':
        handler_counts = {}
        for row in records:
            status = str(row.get('status', '')).upper()
            handled_by = str(row.get('ditangani_oleh', '')).strip()
            if not handled_by:
                if status in ['RESOLVED', 'CLOSED']:
                    handled_by = 'Tim TI Kanwil'
                else:
                    continue
            handler_counts[handled_by] = handler_counts.get(handled_by, 0) + 1
        ranked = sorted(handler_counts.items(), key=lambda item: (-item[1], item[0]))
        lines = ['ringkasan | PETUGAS | total ' + str(len(ranked))]
        for name, total in ranked[:limit]:
            lines.append(name + ' | ' + str(total) + ' tiket')
        if not ranked:
            lines.append('tidak ada data petugas')
        return '\n'.join(lines)

    if mode == 'avg_duration':
        durations = []
        for row in records:
            if str(row.get('status', '')).upper() not in ['RESOLVED', 'CLOSED']:
                continue
            minutes = parse_duration_to_minutes(row.get('durasi', ''))
            if minutes is not None:
                durations.append(minutes)
        avg_minutes = round(sum(durations) / len(durations)) if durations else None
        lines = ['ringkasan | RATA-RATA DURASI | ' + format_minutes(avg_minutes)]
        lines.append('sumber | ' + str(len(durations)) + ' tiket selesai')
        return '\n'.join(lines)

    if mode == 'dashboard':
        active_rows = [r for r in active_records if str(r.get('status', '')).upper() in ACTIVE_STATUSES]
        open_rows = [r for r in active_rows if str(r.get('status', '')).upper() == 'OPEN']
        progress_rows = [r for r in active_rows if str(r.get('status', '')).upper() == 'IN_PROGRESS']
        pending_rows = [r for r in active_rows if str(r.get('status', '')).upper() == 'PENDING']

        def sort_by_created(rows):
            return sorted(rows, key=lambda x: x.get('created_at', ''))

        oldest_active = []
        for row in sort_by_created(active_rows)[:limit]:
            age_minutes = age_minutes_from_created(row.get('created_at', ''), now)
            oldest_active.append((row, format_minutes(age_minutes)))

        pending_reason_counts = {}
        for row in pending_rows:
            reason = str(row.get('alasan_pending', '')).strip() or 'Tanpa alasan'
            pending_reason_counts[reason] = pending_reason_counts.get(reason, 0) + 1
        pending_reason_ranked = sorted(pending_reason_counts.items(), key=lambda item: (-item[1], item[0]))

        active_handler_counts = {}
        for row in progress_rows + pending_rows:
            handled_by = str(row.get('ditangani_oleh', '')).strip() or 'Belum Diisi'
            active_handler_counts[handled_by] = active_handler_counts.get(handled_by, 0) + 1
        active_handler_ranked = sorted(active_handler_counts.items(), key=lambda item: (-item[1], item[0]))

        lines = [
            'dashboard | OPEN ' + str(len(open_rows)) + ' | IN_PROGRESS ' + str(len(progress_rows)) + ' | PENDING ' + str(len(pending_rows))
        ]

        if oldest_active:
            for row, age_text in oldest_active:
                lines.append(
                    'tertua | tiket ' + str(row.get('alias', '-')) + ' | ' + str(row.get('status', '-')) + ' | ' + str(row.get('lokasi', '-')) + ' | ' + str(row.get('masalah', '-')) + ' | umur ' + age_text
                )
        else:
            lines.append('tertua | tidak ada tiket aktif')

        if pending_reason_ranked:
            for reason, total in pending_reason_ranked[:limit]:
                lines.append('pending | ' + reason + ' | ' + str(total) + ' tiket')
        else:
            lines.append('pending | tidak ada tiket pending')

        if active_handler_ranked:
            for name, total in active_handler_ranked[:limit]:
                lines.append('petugas | ' + name + ' | ' + str(total) + ' tiket aktif')
        else:
            lines.append('petugas | tidak ada tiket aktif yang sedang ditangani')

        return '\n'.join(lines)

    if mode in {'urgent', 'urgent_red', 'urgent_yellow'}:
        history_records = get_history_records()
        latest_status_entry_times = build_latest_status_entry_times(history_records)
        urgent_rows = []
        for row in active_records:
            status = str(row.get('status', '')).upper()
            if status not in ACTIVE_STATUSES:
                continue
            stagnation_minutes = status_stagnation_minutes(row, now, latest_status_entry_times)
            sla_level = get_sla_level_for_active_status(status, stagnation_minutes)
            if sla_level not in {'YELLOW', 'RED'}:
                continue
            if mode == 'urgent_red' and sla_level != 'RED':
                continue
            if mode == 'urgent_yellow' and sla_level != 'YELLOW':
                continue
            urgent_rows.append({
                'row': row,
                'sla_level': sla_level,
                'stagnation_minutes': stagnation_minutes,
            })

        urgent_rows = sorted(
            urgent_rows,
            key=lambda item: (
                0 if item['sla_level'] == 'RED' else 1,
                -(item['stagnation_minutes'] or 0),
                str(item['row'].get('alias') or ''),
            ),
        )

        title = 'URGENT'
        empty_text = 'tidak ada tiket urgent (SLA kuning/merah)'
        if mode == 'urgent_red':
            title = 'SLA RED'
            empty_text = 'tidak ada tiket SLA merah'
        elif mode == 'urgent_yellow':
            title = 'SLA YELLOW'
            empty_text = 'tidak ada tiket SLA kuning'

        lines = ['ringkasan | ' + title + ' | total ' + str(len(urgent_rows))]
        for item in urgent_rows[:limit]:
            row = item['row']
            alias = row.get('alias', '-')
            code = row.get('ticket_code', '-')
            lokasi = row.get('lokasi', '-')
            masalah = row.get('masalah', '-')
            status = row.get('status', '-')
            age_text = format_minutes(item.get('stagnation_minutes'))
            lines.append(
                'tiket ' + str(alias) + ' | ' + str(code) + ' | ' + str(lokasi) + ' | ' + str(masalah) + ' | ' + str(status) + ' | SLA ' + str(item['sla_level']) + ' | durasi ' + age_text
            )

        if not urgent_rows:
            lines.append(empty_text)
        return '\n'.join(lines)

    lines = []
    if status_filter:
        filtered = [r for r in records if str(r.get('status', '')).upper() == status_filter]
        filtered = sorted(filtered, key=lambda x: x.get('created_at', ''), reverse=True)
        lines.append('ringkasan | ' + status_filter + ' | total ' + str(len(filtered)))
        for row in filtered[:limit]:
            alias = row.get('alias', '-')
            code = row.get('ticket_code', '-')
            lokasi = row.get('lokasi', '-')
            masalah = row.get('masalah', '-')
            durasi = row.get('durasi', '-') or '-'
            lines.append('tiket ' + str(alias) + ' | ' + code + ' | ' + lokasi + ' | ' + masalah + ' | ' + durasi)
        if not filtered:
            lines.append('tidak ada tiket berstatus ' + status_filter)
        return '\n'.join(lines)

    lines.append(
        'ringkasan | OPEN ' + str(counts.get('OPEN', 0)) + ' | IN_PROGRESS ' + str(counts.get('IN_PROGRESS', 0)) + ' | PENDING ' + str(counts.get('PENDING', 0)) + ' | RESOLVED ' + str(counts.get('RESOLVED', 0)) + ' | CLOSED ' + str(counts.get('CLOSED', 0))
    )

    for status in status_order:
        filtered = [r for r in records if str(r.get('status', '')).upper() == status]
        filtered = sorted(filtered, key=lambda x: x.get('created_at', ''), reverse=True)
        for row in filtered[:limit]:
            alias = row.get('alias', '-')
            code = row.get('ticket_code', '-')
            lokasi = row.get('lokasi', '-')
            masalah = row.get('masalah', '-')
            lines.append(status + ' | tiket ' + str(alias) + ' | ' + code + ' | ' + lokasi + ' | ' + masalah)

    return '\n'.join(lines)

def resolve_alias(ticket_input, records):
    """Resolve ticket alias to actual ticket code."""
    ticket_input = ticket_input.strip().upper()

    # Full ticket code
    if re.match(r'^(NET|APP|HW|INC|OTH)-\d{8}-\d{3}$', ticket_input):
        return ticket_input, None

    # Alias like "3", "tiket 3", "no 3" - use LOCKED alias column, not recency order
    alias_match = re.search(r'(?:TIKET|NO)?\s*(\d+)$', ticket_input, re.IGNORECASE)
    if alias_match:
        num = int(alias_match.group(1))
        for row in records:
            try:
                if int(row.get('alias', 0)) == num:
                    return row.get('ticket_code', ''), num
            except (TypeError, ValueError):
                continue
        return None, num

    # Try exact match
    for row in records:
        if row.get('ticket_code', '').upper() == ticket_input:
            return ticket_input, None
    return None, None

def parse_history_message(message):
    """Parse natural language history lookup like 'tiket 95 histori'."""
    parsed = {
        'ticket': None,
    }

    if not message:
        return parsed

    msg_lower = re.sub(r'\s+', ' ', message.lower()).strip()
    ticket_match = re.search(r'\btiket\s+(\d+)\b', msg_lower)
    if ticket_match:
        parsed['ticket'] = 'tiket ' + ticket_match.group(1)

    return parsed

def cmd_update(args):
    """Update incident status and archive terminal tickets automatically."""
    active_sheet = get_sheet()
    archive_sheet = get_archive_sheet()
    active_records = active_sheet.get_all_records()
    archive_records = archive_sheet.get_all_records()
    all_records = active_records + archive_records

    parsed_message = parse_update_message(getattr(args, 'message', ''))

    ticket_input = (args.ticket if getattr(args, 'ticket', None) else parsed_message.get('ticket') or '').strip()
    if not ticket_input:
        return '[ERROR] Tiket wajib diisi untuk update status.'

    ticket_code, alias_num = resolve_alias(ticket_input, all_records)

    if not ticket_code:
        if alias_num is None:
            return '[ERROR] Tiket tidak valid: ' + ticket_input
        else:
            return '[ERROR] Alias "' + str(alias_num) + '" tidak ditemukan. Total insiden: ' + str(len(all_records))

    now = datetime.now().strftime('%d-%m-%Y %H:%M:%S')

    row_idx, current_record = find_record(active_records, ticket_code)
    target_sheet = active_sheet
    source_name = SHEET_NAME
    target_headers = EXPECTED_HEADERS

    if row_idx is None:
        row_idx, current_record = find_record(archive_records, ticket_code)
        target_sheet = archive_sheet
        source_name = ARCHIVE_SHEET_NAME
        target_headers = ARCHIVE_HEADERS

    if row_idx is None or current_record is None:
        return '[ERROR] Tiket tidak ditemukan: ' + ticket_code

    old_status = current_record.get('status', 'OPEN')
    current_alias = current_record.get('alias', '')

    new_status = 'OPEN'
    status_input = ''
    if getattr(args, 'status', None):
        status_input = args.status.upper()
    elif parsed_message.get('status'):
        status_input = parsed_message['status'].upper()

    if status_input:
        if status_input in ['RESOLVED', 'DONE', 'SELESAI', 'FIX']:
            new_status = 'RESOLVED'
        elif status_input in ['CLOSED', 'CLOSE', 'TUTUP']:
            new_status = 'CLOSED'
        elif status_input in ['IN_PROGRESS', 'PROGRESS', 'ONGOING']:
            new_status = 'IN_PROGRESS'
        elif status_input in ['PENDING', 'WAITING', 'DITUNDA', 'TERTUNDA']:
            new_status = 'PENDING'

    existing_durasi = current_record.get('durasi', '')
    durasi = existing_durasi
    should_calculate_duration = (
        new_status in TERMINAL_STATUSES
        and old_status not in TERMINAL_STATUSES
        and not existing_durasi
    )
    if should_calculate_duration:
        created = current_record.get('created_at', '')
        if created:
            try:
                start = datetime.strptime(created, '%d-%m-%Y %H:%M:%S')
                end = datetime.strptime(now, '%d-%m-%Y %H:%M:%S')
                diff = end - start
                minutes = int(diff.total_seconds() / 60)
                hours = minutes // 60
                mins = minutes % 60
                durasi = str(hours) + 'h ' + str(mins) + 'm' if hours > 0 else str(mins) + 'm'
            except:
                durasi = existing_durasi or 'N/A'

    sender_name = getattr(args, 'sender_name', '') or getattr(args, 'sender', '') or ''
    if parsed_message.get('use_sender_name_as_handler') and sender_name:
        sender_handler = re.sub(r'\s+', ' ', str(sender_name)).strip(' ,.-').title()
    else:
        sender_handler = ''

    explicit_handled_by = getattr(args, 'handled_by', '') or parsed_message.get('handled_by') or sender_handler
    should_use_sender_as_handler = (
        parsed_message.get('use_sender_name_as_handler')
        or (new_status in ['IN_PROGRESS', 'PENDING', 'RESOLVED'] and old_status in ['OPEN', 'PENDING', 'IN_PROGRESS'] and bool(sender_name))
    )
    if explicit_handled_by:
        handled_by = explicit_handled_by
    elif should_use_sender_as_handler and sender_name:
        handled_by = re.sub(r'\s+', ' ', str(sender_name)).strip(' ,.-').title()
    else:
        handled_by = current_record.get('ditangani_oleh', '') or 'Tim TI Kanwil'

    note = (args.note if hasattr(args, 'note') and args.note else '') or parsed_message.get('note', '')
    if new_status == 'PENDING' and not str(note or '').strip():
        return '[ERROR] Alasan pending wajib diisi.'
    bukti_awal = getattr(args, 'bukti_awal', '') or current_record.get('bukti_awal', '') or ''
    bukti_resolve = getattr(args, 'bukti_resolve', '') or current_record.get('bukti_resolve', '') or ''
    uploaded_bukti_awal = []
    uploaded_bukti_resolve = []
    folder_bukti_error = ''
    try:
        folder_bukti = ensure_ticket_bukti_folder(
            ticket_code,
            current_alias,
            current_record.get('lokasi', ''),
            current_record.get('folder_bukti', '') or ''
        )
    except Exception as exc:
        folder_bukti = current_record.get('folder_bukti', '') or ''
        folder_bukti_error = str(exc)

    try:
        uploaded_bukti_awal = upload_files_to_drive_folder(
            getattr(args, 'bukti_awal_files', []) or [],
            folder_bukti,
            ticket_code,
            label='bukti-awal',
            status_label=new_status,
            event_time=now,
        )
        bukti_awal = merge_link_values(bukti_awal, uploaded_bukti_awal)
    except Exception as exc:
        folder_bukti_error = folder_bukti_error or str(exc)

    try:
        uploaded_bukti_resolve = upload_files_to_drive_folder(
            getattr(args, 'bukti_resolve_files', []) or [],
            folder_bukti,
            ticket_code,
            label='bukti-resolve',
            status_label=new_status,
            event_time=now,
        )
        bukti_resolve = merge_link_values(bukti_resolve, uploaded_bukti_resolve)
    except Exception as exc:
        folder_bukti_error = folder_bukti_error or str(exc)
    pending_reason = note if new_status == 'PENDING' else ''
    catatan_terakhir = pending_reason if new_status == 'PENDING' and pending_reason else note
    if new_status == 'IN_PROGRESS' and handled_by and (not note or note.lower() == handled_by.lower()):
        catatan_terakhir = 'Dikerjakan oleh ' + handled_by
    elif new_status == 'RESOLVED' and handled_by and not note:
        catatan_terakhir = 'Selesai oleh ' + handled_by
    elif new_status == 'CLOSED' and not note:
        catatan_terakhir = 'Status diubah ke CLOSED'
    elif not catatan_terakhir:
        catatan_terakhir = 'Status diubah ke ' + new_status

    updated_record = dict(current_record)
    updated_record['status'] = new_status
    updated_record['durasi'] = durasi
    updated_record['update_terakhir'] = now
    updated_record['ditangani_oleh'] = handled_by
    updated_record['alasan_pending'] = pending_reason
    updated_record['catatan_terakhir'] = catatan_terakhir
    updated_record['bukti_awal'] = bukti_awal
    updated_record['bukti_resolve'] = bukti_resolve
    updated_record['folder_bukti'] = folder_bukti
    if source_name == ARCHIVE_SHEET_NAME:
        updated_record['archived_at'] = current_record.get('archived_at', '') or now
        updated_record['source_sheet'] = current_record.get('source_sheet', SHEET_NAME) or SHEET_NAME

    end_col = chr(64 + len(target_headers))
    target_row = row_from_record(updated_record, target_headers)
    target_sheet.update([target_row], 'A' + str(row_idx) + ':' + end_col + str(row_idx))

    archived_auto = False
    restored_auto = False
    if new_status in TERMINAL_STATUSES and source_name == SHEET_NAME:
        move_record_to_archive(active_sheet, row_idx, updated_record, now)
        archived_auto = True
    elif new_status in ACTIVE_STATUSES and source_name == ARCHIVE_SHEET_NAME:
        restore_record_from_archive(active_sheet, archive_sheet, row_idx, updated_record)
        restored_auto = True

    bukti_baru_links = uploaded_bukti_awal + uploaded_bukti_resolve
    bukti_status_entry = new_status if bukti_baru_links else ''

    append_history_row(
        ticket_code=ticket_code,
        alias=current_alias,
        action='UPDATE',
        status_before=old_status,
        status_after=new_status,
        handled_by=handled_by,
        pending_reason=pending_reason,
        catatan_terakhir=catatan_terakhir,
        note=note,
        raw_message=getattr(args, 'message', '') or note,
        bukti_awal=bukti_awal,
        bukti_resolve=bukti_resolve,
        folder_bukti=folder_bukti,
        bukti_status=bukti_status_entry,
        bukti_baru=' | '.join(bukti_baru_links),
    )

    dashboard_ok, dashboard_detail = refresh_dashboard_sheet()

    folder_status = folder_bukti if folder_bukti else ('gagal dibuat otomatis (' + folder_bukti_error[:120] + ')' if folder_bukti_error else '-')
    alias_display = 'tiket ' + str(current_alias or alias_num or '-')
    lokasi_display = current_record.get('lokasi', '-') or '-'
    masalah_display = current_record.get('masalah', '-') or '-'
    pelapor_display = current_record.get('pelapor', '-') or '-'
    response_lines = [
        '',
        '[OK] Incident diupdate!',
        '',
        'Alias: ' + alias_display,
        'Tiket: ' + ticket_code,
        'Lokasi: ' + lokasi_display,
        'Masalah: ' + masalah_display,
        'Pelapor: ' + pelapor_display,
        'Status: ' + old_status + ' -> ' + new_status,
        'Durasi: ' + (durasi if durasi else '-'),
        'Ditangani oleh: ' + handled_by,
        'Alasan pending: ' + (pending_reason if pending_reason else '-'),
    ]
    response_lines.extend([
        'Catatan: ' + (note if note else '-'),
        'Bukti awal: ' + (bukti_awal if bukti_awal else '-'),
        'Bukti resolve: ' + (bukti_resolve if bukti_resolve else '-'),
        'Folder bukti: ' + folder_status,
    ])
    return '\n'.join(response_lines)

def cmd_history(args):
    """Read ticket history from incident_history store."""
    active_records, archive_records = get_all_records(include_archive=True)
    records = active_records + archive_records
    history_records = get_history_sheet().get_all_records()

    parsed_message = parse_history_message(getattr(args, 'message', ''))
    ticket_input = (args.ticket if getattr(args, 'ticket', None) else parsed_message.get('ticket') or '').strip()
    if not ticket_input:
        return '[ERROR] Tiket wajib diisi untuk melihat histori.'

    ticket_code, alias_num = resolve_alias(ticket_input, records)
    if not ticket_code:
        if alias_num is None:
            return '[ERROR] Tiket tidak valid: ' + ticket_input
        return '[ERROR] Alias "' + str(alias_num) + '" tidak ditemukan. Total insiden: ' + str(len(records))

    current_record = None
    for row in records:
        if row.get('ticket_code', '').upper() == ticket_code:
            current_record = row
            break

    if current_record is None:
        return '[ERROR] Tiket tidak ditemukan: ' + ticket_code

    def parse_dt(value):
        try:
            return datetime.strptime(value, '%d-%m-%Y %H:%M:%S')
        except Exception:
            return datetime.min

    history_rows = [r for r in history_records if str(r.get('ticket_code', '')).upper() == ticket_code]
    created_cutoff = parse_dt(current_record.get('created_at', ''))
    if created_cutoff != datetime.min:
        filtered_history_rows = [
            r for r in history_rows
            if parse_dt(r.get('update_time', '')) >= created_cutoff
        ]
        if filtered_history_rows:
            history_rows = filtered_history_rows
    if not history_rows:
        return 'Histori tidak ditemukan untuk tiket ' + ticket_code

    history_rows = sorted(history_rows, key=lambda r: parse_dt(r.get('update_time', '')))
    limit = getattr(args, 'limit', 20) or 20
    if limit > 0:
        history_rows = history_rows[-limit:]

    alias_value = current_record.get('alias', alias_num or '')
    lokasi = current_record.get('lokasi', '-')
    masalah = current_record.get('masalah', '-')
    pelapor = current_record.get('pelapor', '-') or '-'
    status = current_record.get('status', '-')
    lines = [
        'tiket ' + str(alias_value) + ' | ' + ticket_code + ' | ' + lokasi + ' | ' + masalah + ' | ' + status,
        'Pelapor: ' + pelapor
    ]

    for item in history_rows:
        waktu = item.get('update_time', '-')
        waktu_ringkas = waktu[11:16] if len(waktu) >= 16 else waktu
        action = item.get('action', '-')
        status_after = item.get('status_after', '-') or '-'
        handled_by = item.get('ditangani_oleh', '-') or '-'
        catatan_terakhir = item.get('catatan_terakhir', '-') or '-'
        pending_reason = item.get('alasan_pending', '') or ''
        catatan = item.get('catatan', '') or ''
        bukti_status = item.get('bukti_status', '') or ''
        bukti_baru = item.get('bukti_baru', '') or ''

        detail = catatan_terakhir
        normalized_handler = re.sub(r'\s+', ' ', str(handled_by or '')).strip(' ,.-').title()
        normalized_detail = re.sub(r'\s+', ' ', str(detail or '')).strip(' ,.-')
        normalized_detail_lower = normalized_detail.lower()
        if normalized_handler and normalized_handler != '-':
            if normalized_detail_lower == ('dikerjakan oleh ' + normalized_handler).lower():
                detail = 'Dikerjakan'
            elif normalized_detail_lower == ('selesai oleh ' + normalized_handler).lower():
                detail = 'Selesai'
            elif normalized_detail_lower == ('dicek oleh ' + normalized_handler).lower():
                detail = 'Dicek'
            elif normalized_detail_lower == ('diperiksa oleh ' + normalized_handler).lower():
                detail = 'Diperiksa'
        if pending_reason and pending_reason not in detail:
            detail = detail + ' | ' + pending_reason
        elif catatan and catatan not in detail:
            detail = detail + ' | ' + catatan
        if bukti_baru:
            evidence_count = count_link_values(bukti_baru)
            label_status = bukti_status or status_after
            detail = detail + ' | foto ' + label_status + ': ' + str(evidence_count)

        lines.append(
            waktu_ringkas + ' | ' + action + ' | ' + status_after + ' | ' + handled_by + ' | ' + detail
        )

    return '\n'.join(lines)

def cmd_delete(args):
    """Delete an incident."""
    sheet = get_sheet()
    archive_sheet = get_archive_sheet()
    active_records = sheet.get_all_records()
    archive_records = archive_sheet.get_all_records()
    
    ticket_code, _ = resolve_alias(args.ticket.upper(), active_records + archive_records)
    
    if not ticket_code:
        return '[ERROR] Tiket tidak ditemukan: ' + args.ticket
    
    for i, row in enumerate(active_records, 2):
        if row.get('ticket_code', '').upper() == ticket_code:
            incident_db.purge_deleted_ticket(ticket_code)
            return '[OK] Tiket ' + ticket_code + ' dihapus dari incident_log.'

    for i, row in enumerate(archive_records, 2):
        if row.get('ticket_code', '').upper() == ticket_code:
            incident_db.purge_deleted_ticket(ticket_code)
            return '[OK] Tiket ' + ticket_code + ' dihapus dari incident_archive.'
    
    return '[ERROR] Tiket tidak ditemukan: ' + ticket_code

def main():
    parser = argparse.ArgumentParser(description='Kumjabar Incident Writer')
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    write_parser = subparsers.add_parser('write', help='Create new incident')
    write_parser.add_argument('--reporter', help='Nama pelapor')
    write_parser.add_argument('--sender', help='Nomor Signal pengirim')
    write_parser.add_argument('--location', help='Lokasi masalah')
    write_parser.add_argument('--summary', help='Ringkasan masalah')
    write_parser.add_argument('--message', help='Full message to parse')
    write_parser.add_argument('--bukti-awal', dest='bukti_awal', help='Link bukti awal insiden')
    write_parser.add_argument('--bukti-awal-file', dest='bukti_awal_files', action='append', default=[], help='Path file lokal bukti awal untuk diupload ke folder tiket')
    
    list_parser = subparsers.add_parser('list', help='List incidents')
    list_parser.add_argument('--limit', type=int, default=10, help='Max results')
    list_parser.add_argument('--status', help='Filter by status (OPEN, IN_PROGRESS, PENDING, RESOLVED, CLOSED)')
    
    history_parser = subparsers.add_parser('history', help='Read ticket history')
    history_parser.add_argument('--ticket', help='Ticket code or alias')
    history_parser.add_argument('--message', help='Natural language, contoh: tiket 95 histori')
    history_parser.add_argument('--limit', type=int, default=20, help='Max history rows')

    summary_parser = subparsers.add_parser('summary', help='Incident summary by status')
    summary_parser.add_argument('--status', help='Filter status (OPEN, IN_PROGRESS, PENDING, RESOLVED, CLOSED)')
    summary_parser.add_argument('--mode', help='Analytics mode (resolved_today, handlers, avg_duration, dashboard)')
    summary_parser.add_argument('--message', help='Natural language, contoh: tiket open, tiket pending, atau dashboard tiket')
    summary_parser.add_argument('--limit', type=int, default=3, help='Max tickets per status')
    
    update_parser = subparsers.add_parser('update', help='Update incident')
    update_parser.add_argument('--ticket', help='Ticket code or alias')
    update_parser.add_argument('--status', help='New status')
    update_parser.add_argument('--note', help='Catatan')
    update_parser.add_argument('--handled-by', dest='handled_by', help='Nama teknisi/penyelesai')
    update_parser.add_argument('--sender-name', dest='sender_name', help='Nama pengirim chat untuk fallback petugas saat update')
    update_parser.add_argument('--message', help='Full message to parse, contoh: tiket 74 selesai oleh randy')
    update_parser.add_argument('--bukti-awal', dest='bukti_awal', help='Link bukti awal insiden')
    update_parser.add_argument('--bukti-resolve', dest='bukti_resolve', help='Link bukti setelah penanganan/resolve')
    update_parser.add_argument('--bukti-awal-file', dest='bukti_awal_files', action='append', default=[], help='Path file lokal bukti awal untuk diupload ke folder tiket')
    update_parser.add_argument('--bukti-resolve-file', dest='bukti_resolve_files', action='append', default=[], help='Path file lokal bukti resolve untuk diupload ke folder tiket')
    
    delete_parser = subparsers.add_parser('delete', help='Delete incident')
    delete_parser.add_argument('--ticket', required=True, help='Ticket code or alias')
    
    args = parser.parse_args()
    
    if args.command == 'write':
        print(cmd_write(args))
    elif args.command == 'list':
        print(cmd_list(args))
    elif args.command == 'history':
        print(cmd_history(args))
    elif args.command == 'summary':
        print(cmd_summary(args))
    elif args.command == 'update':
        print(cmd_update(args))
    elif args.command == 'delete':
        print(cmd_delete(args))
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
