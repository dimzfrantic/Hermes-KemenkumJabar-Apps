# Incident Portal

Portal web pegawai/admin untuk pelaporan dan operasional tiket insiden TI.

Arsitektur saat ini memakai satu folder induk:
- portal web/admin: `apps/incident-portal/`
- engine incident: `apps/incident-portal/incident_engine/`

Fitur utama:
- login pegawai berbasis NIP
- import master pegawai dari Excel
- ganti password saat login pertama
- form tiket baru
- submit tiket ke incident engine internal
- notifikasi Telegram opsional
- dashboard pegawai dan admin
- sinkron status tiket dari database incident PostgreSQL
- upload bukti awal dan bukti selesai

Struktur penting:
- `app.py` : app factory Flask
- `models.py` : model user dan tiket portal
- `routes/` : auth, portal pegawai, admin
- `services/incident_gateway.py` : integrasi ke incident engine
- `services/telegram_notifier.py` : notifikasi grup
- `incident_engine/` : engine inti tiket
- `uploads/` : lampiran tiket dari portal
- `instance/incident_portal.db` : database lokal portal

Cara jalan lokal:
1. `python3 -m venv .venv`
2. `source .venv/bin/activate`
3. `pip install -r requirements.txt`
4. salin `.env.example` menjadi `.env` dan sesuaikan nilainya
5. `python3 wsgi.py`

Catatan:
- source utama incident engine tidak lagi berada di folder terpisah `apps/incidents/`
- installer engine tetap tersedia, tetapi targetnya sekarang `apps/incident-portal/incident_engine/`

Fitur operasional:
- Drive Token Guard di menu `Operasional Tiket` untuk memantau kesiapan token Google Drive.
- Jika upload bukti gagal karena Drive/token, bukti dicatat sebagai `pending_evidence` lokal dan bisa di-retry.
- Menu `Riwayat Tiket` menampilkan histori update dari database incident live dan mendukung pencarian seperti `tiket 2`.
