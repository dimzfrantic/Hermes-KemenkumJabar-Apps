Instalasi Dasborpim

Dokumen ini menjelaskan langkah instalasi Dasborpim pada server baru.

Ringkasan
- Aplikasi web berbasis Flask
- Dependency Python dikelola melalui requirements.txt
- Umumnya dijalankan dengan gunicorn
- Database utama menggunakan PostgreSQL
- Data operasional dan pelaporan tetap mengacu ke API internal resmi

Lokasi source
- apps/dasborpim/

File penting
- app.py
- config.py
- init_db.py
- requirements.txt
- start.sh
- AGENTS.md

Dependency Python
- Flask
- Flask-SQLAlchemy
- Flask-Login
- Flask-WTF
- psycopg2-binary
- Werkzeug
- python-dotenv
- gunicorn
- openpyxl

Dependency sistem
- python3
- python3-venv
- python3-pip
- postgresql
- nginx (opsional)

Persiapan direktori
Contoh target deploy:
- /opt/kemenkumjabar/apps/dasborpim

Langkah instalasi
1. Masuk ke folder aplikasi
   cd /opt/kemenkumjabar/apps/dasborpim

2. Buat virtual environment
   python3 -m venv .venv

3. Aktifkan virtual environment
   source .venv/bin/activate

4. Install dependency
   pip install --upgrade pip
   pip install -r requirements.txt

5. Siapkan file environment
   - gunakan .env.example sebagai acuan
   - buat .env final secara manual

Variabel minimal yang perlu disiapkan
- SECRET_KEY
- DATABASE_URL

Persiapan PostgreSQL
1. Buat database
2. Buat user database
3. Berikan hak akses
4. Isi DATABASE_URL pada .env

Contoh format DATABASE_URL
- postgresql://dasborpim_user:password@localhost:5432/dasborpim

Inisialisasi database
- jalankan init_db.py bila diperlukan oleh alur aplikasi
- verifikasi schema dan user default sesuai implementasi final

Uji jalan manual
- source .venv/bin/activate
- python app.py
atau gunakan entrypoint final yang berlaku di codebase

Menjalankan dengan gunicorn
Contoh:
- .venv/bin/gunicorn --bind 0.0.0.0:5000 --workers 2 --timeout 120 "app:create_app()"

Systemd
Template tersedia di:
- deploy/systemd/dasborpim.service

Nginx opsional
Template tersedia di:
- deploy/nginx/dasborpim.nginx.conf

Verifikasi pasca instalasi
- virtual environment terbentuk
- requirements terpasang
- database dapat diakses
- aplikasi berjalan di port target
- gunicorn start tanpa error
- service systemd sehat bila dipakai
- reverse proxy sehat bila dipakai

Catatan operasional
- angka dan waktu operasional tetap harus diambil dari API internal resmi
- jangan masukkan .env produksi ke git
- bila path server berbeda, review AGENTS.md, systemd, dan nginx
