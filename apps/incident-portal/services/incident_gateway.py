import importlib.util
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from functools import lru_cache
from flask import current_app
from services.incident_store import get_all_incidents, get_history, get_record, sync_portal_ticket_from_db

PORTAL_CATEGORY_ALIASES = {
    'COMPUTER': 'HARDWARE',
    'PRINTER': 'HARDWARE',
}

PORTAL_CATEGORY_TO_PREFIX = {
    'NETWORK': 'NET',
    'APPLICATION': 'APP',
    'HARDWARE': 'HW',
    'OTHER': 'OTH',
}


@lru_cache(maxsize=1)
def load_incident_module():
    script_path = Path(current_app.config['INCIDENT_WRITER_PATH']).resolve()
    script_dir = str(script_path.parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    spec = importlib.util.spec_from_file_location('incident_writer_portal', script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def build_portal_message(user, category_key, problem_summary, location):
    category_words = current_app.config['TICKET_CATEGORIES']
    normalized_category = normalize_portal_category(category_key)
    lead_word = str(category_words.get(normalized_category, 'gangguan') or 'gangguan').strip().lower()
    clean_summary = ' '.join(str(problem_summary or '').split())
    clean_location = ' '.join(str(location or '').split())

    summary_lower = clean_summary.lower()
    category_prefixes = {
        'NETWORK': ('wifi', 'jaringan', 'internet', 'router', 'modem', 'lan', 'network'),
        'APPLICATION': ('aplikasi', 'application', 'app', 'sistem'),
        'HARDWARE': ('hardware', 'komputer', 'laptop', 'printer', 'pc', 'cpu', 'monitor', 'scanner'),
        'OTHER': ('gangguan',),
    }
    known_prefixes = category_prefixes.get(normalized_category, (lead_word,))
    if any(summary_lower.startswith(f'{prefix} ') or summary_lower == prefix for prefix in known_prefixes):
        incident_summary = clean_summary
    else:
        incident_summary = f"{lead_word} {clean_summary}".strip()

    reporter_name = ' '.join(str(user.full_name or '').split())
    reporter_name = reporter_name.split(',', 1)[0].strip()
    reporter_name = reporter_name.split()[0] if reporter_name else 'Unknown'

    return f"{incident_summary} di {clean_location}. pelapor {reporter_name}"


def normalize_portal_category(category_key):
    key = str(category_key or '').strip().upper()
    if not key:
        return 'OTHER'
    return PORTAL_CATEGORY_ALIASES.get(key, key)


def portal_category_label(category_key):
    normalized = normalize_portal_category(category_key)
    return current_app.config['TICKET_CATEGORIES'].get(normalized, normalized.title())


def portal_category_prefix(category_key):
    normalized = normalize_portal_category(category_key)
    return PORTAL_CATEGORY_TO_PREFIX.get(normalized, 'OTH')


def create_incident_from_portal(user, category_key, problem_summary, location, attachment_path=None):
    incident_module = load_incident_module()
    normalized_category = normalize_portal_category(category_key)
    clean_summary = ' '.join(str(problem_summary or '').split())
    clean_location = ' '.join(str(location or '').split())
    reporter_name = ' '.join(str(user.full_name or '').split())
    reporter_name = reporter_name.split(',', 1)[0].strip()
    reporter_name = reporter_name.split()[0] if reporter_name else 'Unknown'
    args = SimpleNamespace(
        message='',
        summary=clean_summary,
        location=clean_location.upper() if clean_location else 'KANWIL',
        reporter=reporter_name,
        category=portal_category_prefix(normalized_category),
        sender='',
        bukti_awal='',
        bukti_awal_files=[attachment_path] if attachment_path else [],
    )
    response_text = incident_module.cmd_write(args)
    ticket_match = re.search(r'Tiket:\s*([A-Z]+-\d{8}-\d+)\s+alias:\s*tiket\s+(\d+)', response_text)
    if not ticket_match:
        raise RuntimeError(f'Gagal membaca tiket baru dari incident engine: {response_text}')
    return {
        'ticket_code': ticket_match.group(1),
        'ticket_alias': f"tiket {ticket_match.group(2)}",
        'raw_response': response_text,
    }

TERMINAL_STATUSES = {'RESOLVED', 'CLOSED'}


def get_incident_records_map(include_archive=True, force_refresh_source=False):
    active_records, archive_records = get_all_incidents(include_archive=True)
    records_map = {}
    for row in active_records:
        ticket_code = str(row.get('ticket_code', '')).strip().upper()
        if ticket_code:
            records_map[ticket_code] = row
    if include_archive:
        for row in archive_records:
            ticket_code = str(row.get('ticket_code', '')).strip().upper()
            if ticket_code:
                records_map[ticket_code] = row
    return records_map


def get_incident_record(ticket_code, records_map=None, force_refresh_source=False):
    normalized_code = str(ticket_code or '').strip().upper()
    if not normalized_code:
        return None
    if records_map is None:
        return get_record(normalized_code)
    return records_map.get(normalized_code)


def _apply_incident_record(portal_ticket, record):
    portal_ticket.status_cache = record.get('status', portal_ticket.status_cache or 'OPEN') or 'OPEN'
    portal_ticket.last_note_cache = record.get('catatan_terakhir', portal_ticket.last_note_cache)
    portal_ticket.handled_by_cache = record.get('ditangani_oleh', portal_ticket.handled_by_cache)
    portal_ticket.last_update_cache = record.get('update_terakhir', portal_ticket.last_update_cache)


def sync_portal_tickets(portal_tickets, active_only=False, force_refresh_source=False):
    tickets = list(portal_tickets or [])
    if not tickets:
        return 0
    records_map = get_incident_records_map(include_archive=True, force_refresh_source=force_refresh_source)
    synced = 0
    for portal_ticket in tickets:
        status = str(portal_ticket.status_cache or '').strip().upper()
        if active_only and status in TERMINAL_STATUSES and portal_ticket.last_update_cache:
            continue
        record = get_incident_record(portal_ticket.ticket_code, records_map=records_map)
        if not record:
            continue
        _apply_incident_record(portal_ticket, record)
        synced += 1
    return synced


def get_ticket_history(ticket_code, limit=20, force_refresh_source=False):
    return get_history(ticket_code, limit=limit)


def sync_portal_ticket(portal_ticket, records_map=None, force_refresh_source=False):
    return sync_portal_ticket_from_db(portal_ticket)
