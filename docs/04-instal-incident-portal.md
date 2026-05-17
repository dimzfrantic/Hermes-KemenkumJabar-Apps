Instalasi Incident Portal

Dokumen ini menjelaskan instalasi portal web pegawai untuk pelaporan insiden TI.

Ringkasan
- Frontend pegawai untuk login, input tiket, dan melihat status
- Terkoneksi ke Incident Engine
- Dapat memakai notifikasi tambahan sesuai env yang diaktifkan

Lokasi source
- apps/incident-portal/

File penting
- app.py
- config.py
- wsgi.py
- requirements.txt
- services/incident_gateway.py
- services/incident_cache.py
- AGENTS.md

Dependency Python
- Flask
- Flask-SQLAlchemy
- Flask-Login
- Flask-WTF
- Werkzeug
- python-dotenv
- openpyxl
- psycopg[binary]
- gunicorn

Dependency sistem
- python3
- python3-venv
- python3-pip
- postgresql
- nginx (opsional)

Langkah instalasi
1. Masuk ke folder aplikasi
   cd /opt/kemenkumjabar/apps/incident-portal

2. Buat virtual environment
   python3 -m venv .venv

3. Aktifkan
   source .venv/bin/activate

4. Install dependency
   pip install --upgrade pip
   pip install -r requirements.txt

5. Siapkan .env dari .env.example

Variabel penting
- SECRET_KEY
- DATABASE_URL
- DEFAULT_EMPLOYEE_PASSWORD
- ADMIN_NIP
- ADMIN_NAME
- ADMIN_PASSWORD
- INCIDENT_DATABASE_URL
- SIGNAL_ACCOUNT (opsional)
- SIGNAL_GROUP_ID (opsional)
- TELEGRAM_BOT_TOKEN (opsional sesuai fitur)
- TELEGRAM_GROUP_ID (opsional)
- TELEGRAM_TOPIC_INSIDEN_ID (opsional)

Database portal
- siapkan DATABASE_URL untuk database lokal portal bila dipakai
- siapkan INCIDENT_DATABASE_URL untuk sinkron dengan backend utama

Akun admin awal
- ADMIN_NIP
- ADMIN_NAME
- ADMIN_PASSWORD

Uji jalan manual
- source .venv/bin/activate
- python wsgi.py

Port default hasil audit
- 5050

Gunicorn
Contoh:
- .venv/bin/gunicorn -w 2 -b 0.0.0.0:5050 wsgi:app

Systemd
Template tersedia di:
- deploy/systemd/incident-portal.service

Nginx opsional
Template tersedia di:
- deploy/nginx/incident-portal.nginx.conf

Verifikasi integrasi
- admin dapat login
- tiket baru dari portal masuk ke Incident Engine
- status tiket dapat dibaca kembali
- sinkron status sesuai kebutuhan

Catatan operasional
- portal adalah frontend pegawai, bukan sumber status utama
- .env asli dan kredensial notifikasi tidak boleh masuk git
- review semua path absolut bila pindah server
