Instalasi Certificate Generator

Dokumen ini menjelaskan instalasi aplikasi generator sertifikat.

Ringkasan
- Menghasilkan sertifikat dari template PPTX
- Mengubah hasil menjadi PDF
- Dapat mengunggah ke Google Drive
- Mendukung automasi event melalui cron

Lokasi source
- apps/certificate-generator/

File penting
- app.py
- config.py
- wsgi.py
- requirements.txt
- scripts/sync_auto_events.py
- services/google_drive.py
- services/google_sheets.py
- services/pptx_generator.py

Dependency Python
- Flask
- Flask-Login
- Flask-SQLAlchemy
- python-dotenv
- openpyxl
- python-pptx
- google-api-python-client
- google-auth
- gunicorn

Dependency tambahan runtime yang perlu tersedia di environment
- Pillow dan dependency terkait jika digunakan package environment final

Dependency sistem
- python3
- python3-venv
- python3-pip
- libreoffice
- libreoffice-impress
- fontconfig

Sangat disarankan
- font Poppins ExtraBold atau font lain yang dipakai template final

Langkah instalasi
1. Masuk ke folder aplikasi
   cd /opt/kemenkumjabar/apps/certificate-generator

2. Buat virtual environment
   python3 -m venv .venv

3. Aktifkan
   source .venv/bin/activate

4. Install dependency
   pip install --upgrade pip
   pip install -r requirements.txt

5. Buat .env final dari .env.example

Variabel penting
- SECRET_KEY
- ADMIN_USERNAME
- ADMIN_PASSWORD
- ADMIN_DISPLAY_NAME
- GOOGLE_TOKEN_PATH
- SOFFICE_PATH
- MAX_PARALLEL_WORKERS
- JOB_RETRY_COUNT
- DB_COMMIT_BATCH_SIZE
- AUTO_EVENT_MAX_WORKERS
- AUTO_EVENT_DEFAULT_INTERVAL_MINUTES

Persiapan sistem
- verifikasi perintah soffice tersedia
- pasang font template yang dibutuhkan
- salin token Google secara manual

Uji jalan manual
- source .venv/bin/activate
- python app.py

Port default hasil audit
- 5062

Gunicorn
Contoh:
- .venv/bin/gunicorn -w 2 -b 0.0.0.0:5062 wsgi:app

Systemd
Template tersedia di:
- deploy/systemd/certificate-generator.service

Cron automasi
Template tersedia di:
- deploy/cron/certificate-generator.cron

Verifikasi pasca instalasi
- login admin berhasil
- template dapat dibaca
- file peserta dapat diproses
- PDF dapat dihasilkan
- font sesuai ekspektasi
- upload Google Drive berjalan bila aktif
- cron berjalan bila diaktifkan

Catatan operasional
- jangan commit token Google
- jangan commit template atau artefak produksi sensitif tanpa review
- jika hasil PDF berubah, cek font dan LibreOffice terlebih dahulu
