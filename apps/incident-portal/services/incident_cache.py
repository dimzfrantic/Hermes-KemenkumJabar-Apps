from datetime import datetime


def parse_portal_datetime(value):
    text = str(value or '').strip()
    if not text:
        return None
    for fmt in ('%d-%m-%Y %H:%M:%S', '%d-%m-%Y %H:%M', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None
