# Incident Portal

Portal web pegawai untuk pelaporan insiden TI Kementerian Hukum Jawa Barat.

Fitur MVP fase 1:
- Login pegawai berbasis NIP
- Import master pegawai dari Excel
- Ganti password saat login pertama
- Form tiket baru
- Submit tiket ke incident engine yang sudah aktif di `/home/ubnt/incidents`
- Notifikasi ke grup Telegram TI (jika env Telegram diisi)
- Dashboard pegawai untuk melihat status tiket miliknya
- Sinkron status tiket dari database incident PostgreSQL

Struktur penting:
- `app.py` : app factory Flask
- `models.py` : model user dan tiket portal
- `routes/` : auth, portal pegawai, admin import pegawai
- `services/incident_gateway.py` : integrasi ke incident writer dan database incident PostgreSQL
- `services/telegram_notifier.py` : notifikasi ke grup Telegram
- `uploads/` : lampiran tiket dari portal
- `instance/incident_portal.db` : database lokal portal

Cara jalan lokal:
1. `python3 -m venv .venv`
2. `source .venv/bin/activate`
3. `pip install -r requirements.txt`
4. salin `.env.example` menjadi `.env` dan sesuaikan nilainya
5. `python3 wsgi.py`

Login admin awal:
- NIP mengikuti `ADMIN_NIP`
- password mengikuti `ADMIN_PASSWORD`

Format Excel import pegawai minimal:
- `nip`
- `nama`
- `unit`
- `nomor_hp` (opsional)
