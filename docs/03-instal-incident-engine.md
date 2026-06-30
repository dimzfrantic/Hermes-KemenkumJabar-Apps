Instalasi Incident Engine

Dokumen ini menjelaskan instalasi backend utama insiden/tiket dengan pola non-interaktif berbasis skrip.

Ringkasan
- Backend utama tiket dan histori insiden
- Sumber status resmi untuk workflow incident
- Menggunakan PostgreSQL
- Dapat memakai Google Drive bila alur bukti diaktifkan

Lokasi source
- `apps/incident-portal/incident_engine/`

File penting
- `apps/incident-portal/incident_engine/incident_writer.py`
- `apps/incident-portal/incident_engine/incident_db.py`
- `apps/incident-portal/incident_engine/requirements.txt`
- `apps/incident-portal/incident_engine/AGENTS.md`
- `install/install-incidents.sh`
- `install/templates/incidents.env.example`

Langkah instalasi via skrip
1. Salin template env
   cp install/templates/incidents.env.example /tmp/incidents.env
2. Isi parameter wajib
   - DATABASE_URL
3. Isi parameter opsional bila fitur dipakai
   - GOOGLE_TOKEN_PATH
   - GOOGLE_CLIENT_SECRET_PATH
4. Jalankan installer
   bash install/install-incidents.sh --env-file /tmp/incidents.env

Yang dilakukan installer
- menyalin file env ke `apps/incident-portal/incident_engine/.env`
- membuat virtual environment bila belum ada
- meng-install dependency Python engine
- memverifikasi CLI `incident_writer.py --help`

Verifikasi pasca instalasi
- dependency terpasang
- database aktif
- schema tersedia
- create ticket berhasil
- update ticket berhasil
- history ticket tercatat
- portal dapat membaca status terbaru
