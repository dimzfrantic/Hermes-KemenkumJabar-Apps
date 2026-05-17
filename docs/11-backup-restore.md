Backup dan Restore

Dokumen ini menjelaskan strategi backup dan restore untuk source, konfigurasi, data, dan komponen Hermes.

Kategori backup
1. Backup repo
- source code
- docs
- installer
- template deploy

2. Backup private operasional
- .env asli
- config final
- service final
- skills
- data pendukung non-publik

3. Backup rahasia
- token bot
- API key Hermes
- Google OAuth/token
- password database
- dump database produksi

Komponen penting yang perlu dibackup
- Dasborpim: source, .env, DB, service, nginx
- Incident Engine: source, .env, DB, credential Google bila aktif
- Incident Portal: source, .env, DB portal bila ada, service
- Certificate Generator: source, .env, token Google, template, font, cron, service
- Hermes: SOUL.md, MEMORY.md, USER.md, skills, config.yaml, .env, state.db opsional

Restore pada server baru
1. siapkan OS dan dependency
2. clone repo
3. buat ulang virtual environment
4. restore .env dan credential manual
5. restore database
6. restore komponen Hermes
7. aktifkan service
8. verifikasi tiap komponen

Urutan prioritas restore
- aplikasi inti dan database terlebih dahulu
- Hermes Agent dan gateway setelah aplikasi utama siap
- notifikasi, cron, dan lane tambahan setelah verifikasi dasar lulus

Catatan
- jangan restore .venv mentah dari server lama
- jangan commit backup rahasia ke git
- state.db opsional, hanya bila continuity session_search diperlukan
