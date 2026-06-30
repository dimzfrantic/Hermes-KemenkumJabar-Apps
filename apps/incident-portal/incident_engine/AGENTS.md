# AGENTS.md - Incident Engine

## Fokus Folder
Folder ini khusus untuk engine sistem tiket/insiden inti di:
`apps/incident-portal/incident_engine/`

## Fungsi Utama
- create ticket
- update status
- history tiket
- bukti awal dan bukti selesai
- integrasi PostgreSQL
- integrasi Google Drive untuk lampiran/bukti

## Referensi Sistem
Script utama:
- `incident_writer.py`
- `incident_db.py`

Database utama:
- `incidents`
- `incident_history`
- `incident_attachments`
