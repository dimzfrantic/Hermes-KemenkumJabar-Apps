from __future__ import annotations

from datetime import datetime

from app import create_app
from extensions import db
from models import AutoCertificateEvent
from google.auth.exceptions import TransportError

from services.auto_certificate import AutoCertificateError, sync_event


def main():
    app = create_app()
    with app.app_context():
        now = datetime.utcnow()
        events = AutoCertificateEvent.query.filter_by(enabled=True).all()
        processed = 0
        for event in events:
            if event.next_run_at and event.next_run_at > now:
                continue
            try:
                summary = sync_event(event.id)
                print(f'[OK] {event.name}: {summary.message}')
            except TransportError as exc:
                print(f'[ERR] {event.name}: koneksi ke layanan Google gagal ({exc})')
            except AutoCertificateError as exc:
                print(f'[ERR] {event.name}: {exc}')
            processed += 1
        print(f'Processed {processed} event(s).')


if __name__ == '__main__':
    main()
