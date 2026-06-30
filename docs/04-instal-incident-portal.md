Instalasi Incident Portal

Dokumen ini menjelaskan instalasi portal web pegawai/admin untuk pelaporan insiden TI.

Ringkasan
- Frontend pegawai dan admin
- Terkoneksi ke incident engine internal
- Dapat memakai notifikasi Telegram sesuai env

Lokasi source
- `apps/incident-portal/`
- `apps/incident-portal/incident_engine/`

File penting
- `apps/incident-portal/app.py`
- `apps/incident-portal/config.py`
- `apps/incident-portal/wsgi.py`
- `apps/incident-portal/requirements.txt`
- `apps/incident-portal/services/incident_gateway.py`
- `apps/incident-portal/incident_engine/incident_writer.py`
- `install/install-incident-portal.sh`
- `install/templates/incident-portal.env.example`

Langkah instalasi via skrip
1. Salin template env
   cp install/templates/incident-portal.env.example /tmp/incident-portal.env
2. Isi parameter wajib
   - SECRET_KEY
   - DATABASE_URL
   - DEFAULT_EMPLOYEE_PASSWORD
   - ADMIN_NIP
   - ADMIN_NAME
   - ADMIN_PASSWORD
   - INCIDENT_DATABASE_URL
3. Isi parameter opsional bila dipakai
   - INCIDENTS_DIR
   - INCIDENT_WRITER_PATH
   - TELEGRAM_BOT_TOKEN
   - TELEGRAM_GROUP_ID
   - TELEGRAM_TOPIC_INSIDEN_ID
4. Jalankan installer
   bash install/install-incident-portal.sh --env-file /tmp/incident-portal.env

Yang dilakukan installer
- menyalin file env ke `apps/incident-portal/.env`
- membuat virtual environment portal bila belum ada
- meng-install dependency Python portal
- memverifikasi aplikasi dengan `create_app()`

Verifikasi integrasi
- admin dapat login
- tiket baru dari portal masuk ke incident engine
- status tiket dapat dibaca kembali
- upload bukti berjalan
- notifikasi grup bekerja bila diaktifkan
