Prasyarat Server

Dokumen ini menjelaskan prasyarat minimum dan rekomendasi server untuk menjalankan Hermes-KemenkumJabar-Apps.

Sistem operasi yang disarankan
- Ubuntu 22.04 LTS
- Debian 12

Paket dasar sistem
- git
- curl
- wget
- unzip
- ca-certificates
- software-properties-common
- build-essential
- pkg-config
- python3
- python3-venv
- python3-pip

Paket server/aplikasi yang umum dibutuhkan
- postgresql
- postgresql-contrib
- nginx (opsional, tetapi disarankan untuk reverse proxy)
- libreoffice
- libreoffice-impress
- fontconfig

Kebutuhan per komponen
1. Dasborpim
- Python 3
- virtual environment
- PostgreSQL
- gunicorn

2. Incident Engine
- Python 3
- psycopg
- PostgreSQL
- kredensial Google bila alur bukti/upload aktif

3. Incident Portal
- Python 3
- PostgreSQL
- gunicorn
- env notifikasi bila dipakai

4. Certificate Generator
- Python 3
- gunicorn
- LibreOffice/soffice
- font yang sesuai
- token Google OAuth

5. Hermes Agent
- instalasi Hermes
- akses provider/model
- ~/.hermes/config.yaml dan ~/.hermes/.env

6. Hermes Gateway Telegram
- Hermes Agent sudah sehat
- Telegram Bot Token
- akses internet
- service gateway aktif

Port yang perlu diperhatikan
- 5000 untuk Dasborpim (default internal)
- 5050 untuk Incident Portal
- 5062 untuk Certificate Generator
- 80/443 bila memakai nginx reverse proxy

User dan permission
Disarankan menggunakan user operasional yang jelas dan konsisten.
Contoh pada server saat audit: ubnt.

Pastikan user:
- punya hak tulis pada folder aplikasi
- bisa membuat virtual environment
- bisa menjalankan service user-level bila dipilih
- punya akses ke file kredensial yang diperlukan

Timezone
Disarankan:
- Asia/Jakarta

Penting untuk:
- cron
- log
- timestamp tiket
- timestamp file dan dokumen

Akses integrasi eksternal
Beberapa komponen memerlukan akses keluar ke:
- Telegram API
- provider model Hermes
- Google API untuk Drive/Sheets
- repository package saat instalasi

Persiapan manual sebelum instalasi
- file .env asli tiap aplikasi
- Telegram Bot Token
- API key/provider Hermes
- Google token/OAuth
- template PPTX sertifikat
- font tambahan
- database dump bila migrasi dari server lama

Rekomendasi sumber daya minimum
Untuk penggunaan gabungan kecil-menengah:
- CPU minimal 4 core
- RAM minimal 8 GB
- Disk minimal 50 GB

Naikkan kapasitas bila:
- Certificate Generator dipakai berat
- histori Hermes besar
- banyak file lampiran/bukti
- banyak aplikasi aktif bersamaan

Checklist awal
- sistem operasi sesuai
- apt update berjalan
- python3 tersedia
- python3-venv tersedia
- PostgreSQL siap
- LibreOffice tersedia bila Certificate Generator dipasang
- internet tersedia
- secret/kredensial manual sudah disiapkan
