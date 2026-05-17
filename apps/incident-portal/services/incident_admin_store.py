from collections import Counter
from datetime import datetime

from services.incident_store import get_all_incidents, get_history, parse_dt


def get_dashboard_records():
    active, archive = get_all_incidents(include_archive=True)
    history_rows = get_history()
    return active, archive, history_rows


def latest_status_entry_times(history_rows):
    latest = {}
    for row in history_rows or []:
        ticket_code = str(row.get('ticket_code', '')).strip().upper()
        status_after = str(row.get('status_after', '')).strip().upper()
        update_dt = parse_dt(row.get('update_time'))
        if not ticket_code or status_after not in {'OPEN', 'IN_PROGRESS', 'PENDING'} or not update_dt:
            continue
        key = (ticket_code, status_after)
        prev = latest.get(key)
        if prev is None or update_dt > prev:
            latest[key] = update_dt
    return latest


def sync_state_summary(active_count, archive_count, history_count):
    return {
        'last_synced_at': datetime.utcnow(),
        'active_count': active_count,
        'archive_count': archive_count,
        'history_count': history_count,
        'last_error': None,
    }
