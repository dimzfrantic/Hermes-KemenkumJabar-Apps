Checklist Environment Variables dan Secrets

Dokumen ini berisi daftar environment variables, token, dan file kredensial yang harus dipasang manual.

Prinsip umum
- secret tidak disimpan di GitHub
- yang masuk repo hanya file example/template
- semua nilai nyata dipasang manual pada server tujuan

Jangan commit ke Git
- file .env asli
- token Telegram
- API key provider/model Hermes
- Google OAuth/token
- auth.json Hermes
- password database
- password admin produksi
- dump database produksi

Boleh masuk repo
- .env.example
- config.yaml.example
- gateway.env.example
- template systemd/cron/nginx
- dokumentasi konfigurasi

Checklist per komponen

1. Dasborpim
Siapkan manual:
- SECRET_KEY
- DATABASE_URL
- user database
- password database

Verifikasi:
- aplikasi membaca .env dengan benar
- koneksi PostgreSQL berhasil

2. Incident Engine
Siapkan manual:
- DATABASE_URL
- INCIDENT_DATABASE_URL bila dipakai
- GOOGLE_TOKEN_PATH jika integrasi Drive aktif
- GOOGLE_CLIENT_SECRET_PATH jika diperlukan

Verifikasi:
- create/list/update tiket berjalan
- koneksi DB valid
- credential eksternal dapat dibaca user aplikasi

3. Incident Portal
Siapkan manual:
- SECRET_KEY
- DATABASE_URL
- DEFAULT_EMPLOYEE_PASSWORD
- ADMIN_NIP
- ADMIN_NAME
- ADMIN_PASSWORD
- INCIDENT_DATABASE_URL
- TELEGRAM_BOT_TOKEN bila notifikasi dipakai
- TELEGRAM_GROUP_ID bila dipakai
- TELEGRAM_TOPIC_INSIDEN_ID bila dipakai

Verifikasi:
- admin awal dapat login
- portal dapat membuat tiket
- status sinkron dengan backend

4. Certificate Generator
Siapkan manual:
- SECRET_KEY
- ADMIN_USERNAME
- ADMIN_PASSWORD
- ADMIN_DISPLAY_NAME
- GOOGLE_TOKEN_PATH
- SOFFICE_PATH bila perlu override
- MAX_PARALLEL_WORKERS
- JOB_RETRY_COUNT
- DB_COMMIT_BATCH_SIZE

Tambahan non-env:
- token Google OAuth aktif
- template PPTX final
- font yang dibutuhkan

Verifikasi:
- generate PDF berjalan
- upload Google Drive berjalan bila aktif
- soffice tersedia

5. Hermes Agent
Siapkan manual:
- ~/.hermes/.env
- API key/provider
- config.yaml final
- SOUL.md final
- MEMORY.md dan USER.md bila dimigrasikan
- skills bila dimigrasikan

Verifikasi:
- hermes doctor lolos
- model dapat dipanggil
- memory status sesuai
- persona sesuai SOUL.md

6. Hermes Gateway Telegram
Siapkan manual:
- TELEGRAM_BOT_TOKEN
- TELEGRAM_ALLOWED_USERS bila dipakai
- TELEGRAM_HOME_CHANNEL bila dipakai
- TELEGRAM_GROUP_ALLOWED_CHATS bila dipakai
- TELEGRAM_TOPIC_INSIDEN_ID bila dipakai

Verifikasi:
- bot merespons DM
- bot merespons grup/topik bila diaktifkan
- gateway log tidak menunjukkan error token

Pemeriksaan keamanan akhir
- tidak ada token di repo kerja
- tidak ada .env asli ikut ter-commit
- file credential dibatasi permission-nya
- secret disimpan terpisah dari repo

Rekomendasi praktik aman
- gunakan .env.example sebagai acuan
- simpan secret di password manager/vault internal
- jangan salin secret ke README
- rotasi token jika ada indikasi kebocoran
