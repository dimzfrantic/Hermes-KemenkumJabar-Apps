Hermes-KemenkumJabar-Apps

Paket aplikasi internal Kementerian Hukum Jawa Barat untuk deployment, migrasi, dokumentasi operasional, dan integrasi Hermes secara modular.

Komponen utama:
- Dasborpim
- Incident Engine
- Incident Portal
- Certificate Generator
- Hermes Agent
- Hermes Gateway Telegram

Tujuan repo ini:
- menyediakan satu paket kerja yang rapi untuk instalasi di mesin baru
- memisahkan source code, dokumentasi, template deploy, dan file sensitif
- memudahkan migrasi SOUL.md, AGENTS.md, memory Hermes, service, dan konfigurasi aplikasi
- memungkinkan instalasi sebagian atau seluruh stack sesuai kebutuhan

Prinsip utama:
- instalasi modular: tidak wajib memasang semua komponen
- file sensitif tidak disimpan di git
- source aplikasi inti tetap dipisahkan dari konfigurasi produksi
- Hermes berfungsi sebagai layer otomasi dan komunikasi, bukan pengganti aplikasi inti

Struktur repo
- apps/
  Source code aplikasi yang sudah dibersihkan dari artefak sensitif dan runtime junk.
- docs/
  Dokumentasi arsitektur, instalasi, integrasi, migrasi, backup, dan troubleshooting.
- install/
  Installer modular per komponen dan installer gabungan.
- deploy/
  Template systemd, cron, dan nginx.
- migration/
  Checklist manual secrets, verifikasi pasca instalasi, dan helper migrasi.
- .hermes-template/
  Template SOUL.md, config.yaml.example, gateway.env.example, dan memory example.

Mode penggunaan
1. Install aplikasi tertentu saja
   Contoh: hanya Dasborpim, atau hanya Certificate Generator.

2. Install stack insiden
   - Incident Engine
   - Incident Portal

3. Install Hermes saja
   - Hermes Agent
   - Hermes Gateway Telegram

4. Install full stack
   - seluruh aplikasi
   - Hermes Agent
   - Hermes Gateway Telegram

Quick start
1. Baca docs/00-arsitektur.md
2. Baca docs/01-prasyarat-server.md
3. Baca docs/10-env-secrets-checklist.md
4. Jalankan installer sesuai kebutuhan:
   - install/install-shared-deps.sh
   - install/install-dasborpim.sh
   - install/install-incidents.sh
   - install/install-incident-portal.sh
   - install/install-certificate-generator.sh
   - install/install-hermes-agent.sh
   - install/install-hermes-gateway.sh
   - install/install-all.sh

Urutan baca dokumentasi yang disarankan
1. docs/00-arsitektur.md
2. docs/01-prasyarat-server.md
3. docs/10-env-secrets-checklist.md
4. docs/02-instal-dasborpim.md
5. docs/03-instal-incident-engine.md
6. docs/04-instal-incident-portal.md
7. docs/05-instal-certificate-generator.md
8. docs/06-instal-hermes-agent.md
9. docs/07-instal-hermes-gateway-telegram.md
10. docs/08-integrasi-hermes-aplikasi.md
11. docs/09-systemd-cron-service.md
12. docs/11-backup-restore.md
13. docs/12-migrasi-memory-soul-agents.md
14. docs/13-troubleshooting.md

Prasyarat umum server
- Ubuntu atau Debian
- git
- curl
- python3
- python3-venv
- python3-pip
- PostgreSQL
- nginx opsional
- LibreOffice/soffice untuk Certificate Generator
- font pendukung sertifikat
- akses internet untuk instalasi dependency
- token/kredensial manual sesuai komponen yang digunakan

Komponen sensitif yang tidak boleh masuk git
- file .env asli
- token Telegram
- API key provider/model Hermes
- Google OAuth/token
- auth.json Hermes
- database dump produksi
- uploads, lampiran, dan bukti produksi
- state.db dan session produksi Hermes

Komponen Hermes yang didukung migrasi
- SOUL.md
- AGENTS.md per aplikasi
- MEMORY.md
- USER.md
- skills
- config.yaml setelah disesuaikan
- state.db secara opsional jika continuity session diperlukan

Catatan deploy
- template di folder deploy/ adalah contoh awal dan perlu disesuaikan dengan path serta user server tujuan
- installer di folder install/ adalah dasar modular dan dapat disempurnakan sesuai lingkungan final
- file sensitif dan review manual disimpan terpisah dari repo git

Status repo saat ini
- struktur repo sudah dibangun
- source code inti sudah masuk dan disanitasi
- template Hermes dan deploy sudah tersedia
- dokumentasi inti sudah tersedia dan dapat dilanjutkan penyempurnaannya

Rekomendasi langkah berikutnya
- finalisasi isi dokumen prioritas per aplikasi
- finalisasi template deploy dan cron sesuai server tujuan
- uji installer modular pada server baru/staging
- lakukan commit lanjutan bertahap untuk penyempurnaan dokumentasi dan operasional
