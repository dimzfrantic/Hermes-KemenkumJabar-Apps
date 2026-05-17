Generator Sertifikat Internal

Ringkas:
- Upload template PPTX per proses
- Upload Excel peserta
- Preview sampel PDF
- Generate 1 PDF per peserta
- Upload otomatis ke folder Google Drive tetap
- Progress bar dan status proses
- File sementara lokal dihapus setelah upload sukses

Menjalankan:
1. python3 -m venv .venv
2. . .venv/bin/activate
3. pip install -r requirements.txt
4. cp .env.example .env lalu sesuaikan
5. python app.py

Akses default lokal:
- http://127.0.0.1:5062/login
- http://172.16.71.217:5062/login

Login awal:
- username default: admin
- password default: Admin123!

Kebutuhan runtime:
- token Google OAuth aktif di path GOOGLE_TOKEN_PATH
- scope Drive write tersedia
- LibreOffice/soffice terpasang untuk konversi PPTX ke PDF
- font Poppins ExtraBold sudah dipasang di server untuk hasil konsisten

Catatan performa:
- aplikasi kini memakai worker paralel terbatas dengan retry sederhana per peserta
- default aman: MAX_PARALLEL_WORKERS=2, JOB_RETRY_COUNT=1, DB_COMMIT_BATCH_SIZE=25
- untuk beban 1000 sertifikat, mulai dari 2 worker dulu; bila CPU/RAM longgar dan hasil stabil, naikkan bertahap ke 3 atau 4 worker
- skip preview setelah template final terkunci agar waktu total lebih singkat
- commit database dibuat per batch agar progres tetap konsisten tanpa terlalu sering write ke SQLite

Kolom placeholder template:
- {{nama}}
- {{instansi}}

Format Excel minimal:
- Nama
- Instansi
