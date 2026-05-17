Instalasi Incident Engine

Dokumen ini menjelaskan instalasi backend utama insiden/tiket.

Ringkasan
- Backend utama tiket dan histori insiden
- Sumber status resmi untuk workflow incident
- Menggunakan PostgreSQL
- Dapat memakai Google Drive/credential tertentu bila alur bukti aktif

Lokasi source
- apps/incidents/

File penting
- incident_writer.py
- incident_db.py
- requirements.txt
- AGENTS.md

Dependency Python
- psycopg[binary]
- google-api-python-client
- google-auth
- google-auth-oauthlib
- google-auth-httplib2

Dependency sistem
- python3
- python3-venv
- python3-pip
- postgresql

Persiapan database
Tabel utama:
- incidents
- incident_history
- incident_attachments

Langkah instalasi
1. Masuk ke folder aplikasi
   cd /opt/kemenkumjabar/apps/incidents

2. Buat virtual environment
   python3 -m venv .venv

3. Aktifkan virtual environment
   source .venv/bin/activate

4. Install dependency
   pip install --upgrade pip
   pip install -r requirements.txt

5. Buat .env final berdasarkan .env.example

Variabel penting
- DATABASE_URL
- INCIDENT_DATABASE_URL (opsional bila dipisahkan)
- GOOGLE_TOKEN_PATH (opsional jika integrasi aktif)
- GOOGLE_CLIENT_SECRET_PATH (opsional jika integrasi aktif)

Contoh DATABASE_URL
- postgresql://incident_user:password@localhost:5432/incidents

Verifikasi database
- pastikan koneksi PostgreSQL sukses
- pastikan schema dapat dibuat/dibaca
- jalankan uji create/list/update tiket

Integrasi Google Drive
Bila alur bukti tetap aktif:
- salin token OAuth secara manual
- verifikasi permission file
- pastikan scope token sesuai kebutuhan

Uji jalan dasar
- source .venv/bin/activate
- python incident_writer.py --help
- jalankan alur uji create/list/update sesuai kebutuhan lokal

Model operasional
Incident Engine bisa dipakai sebagai:
- backend script internal
- komponen yang dipanggil portal
- backend operasional untuk workflow/chat tertentu

Verifikasi pasca instalasi
- dependency terpasang
- database aktif
- schema tersedia
- create ticket berhasil
- update ticket berhasil
- history ticket tercatat
- integrasi portal dapat membaca status

Catatan operasional
- Incident Engine adalah sumber status utama
- jangan masukkan .env asli dan credential Google ke git
- jika migrasi dari server lama, pertimbangkan restore database lebih dulu
