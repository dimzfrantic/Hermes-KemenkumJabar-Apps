Hermes-KemenkumJabar-Apps

Paket gabungan untuk deployment, migrasi, dan operasional aplikasi internal Kementerian Hukum Jawa Barat.

Cakupan repo ini meliputi:
- Dasborpim
- Incident Engine
- Incident Portal
- Certificate Generator
- Hermes Agent
- Hermes Gateway Telegram

Karakter utama repo:
- instalasi modular per komponen
- dokumentasi migrasi dan operasional
- pemisahan tegas antara file aman untuk git dan file sensitif/manual
- dukungan migrasi SOUL.md, AGENTS.md, memory Hermes, dan konfigurasi operasional

Struktur utama:
- apps/                 source code aplikasi (dibersihkan sebelum masuk git)
- docs/                 dokumentasi instalasi, migrasi, integrasi, troubleshooting
- install/              installer modular
- deploy/               template systemd, cron, nginx
- migration/            checklist dan helper migrasi
- .hermes-template/     template SOUL, config, gateway env, memory contoh

Prinsip keamanan:
- jangan commit file .env asli
- jangan commit token Telegram
- jangan commit API key provider/model
- jangan commit Google OAuth/token
- jangan commit auth.json, state.db, atau database dump produksi

Urutan baca yang disarankan:
1. docs/00-arsitektur.md
2. docs/01-prasyarat-server.md
3. docs/10-env-secrets-checklist.md
4. docs/02-07 instalasi aplikasi/Hermes
5. docs/08-09 integrasi dan service
6. docs/11-13 backup, migrasi, troubleshooting

Status folder ini:
- ini adalah repo kerja bersih pra-git
- source aplikasi belum seluruhnya dipindahkan
- file sensitif tetap dipisahkan di folder manual-config
