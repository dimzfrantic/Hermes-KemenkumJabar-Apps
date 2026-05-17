Integrasi Hermes dengan Aplikasi Internal

Dokumen ini menjelaskan bagaimana Hermes terhubung dengan aplikasi dalam repo ini.

Prinsip umum
- aplikasi inti tetap menjadi sumber data utama
- Hermes adalah layer otomasi, dokumentasi, troubleshooting, dan komunikasi
- konteks global datang dari SOUL.md
- konteks lokal datang dari AGENTS.md per aplikasi

Integrasi per domain
1. Dasborpim
- Hermes membantu deployment, audit, dokumentasi, dan pelaporan operasional
- data numerik tetap harus dari API internal resmi

2. Incident Engine
- Hermes membantu workflow operasional dan audit backend
- status resmi tetap berasal dari Incident Engine

3. Incident Portal
- Hermes membantu deployment, monitoring, dan integrasi notifikasi
- portal tetap frontend pegawai

4. Certificate Generator
- Hermes membantu deployment, troubleshooting, cron, dan integrasi Google
- aplikasi generator tetap memegang logika dokumen

Integrasi Telegram
- DM untuk akses umum/personal
- grup/topik khusus untuk domain insiden atau lane operasional tertentu
- sangat disarankan memisahkan lane jika satu bot dipakai lintas domain
- bila satu bot dipakai untuk banyak domain, gunakan telegram.channel_prompts dan routing deterministik untuk mencegah jawaban lintas domain

Komponen migrasi penting
- SOUL.md
- AGENTS.md
- MEMORY.md
- USER.md
- skills
- config.yaml

Batasan penting
- Hermes tidak menggantikan database utama aplikasi
- logika bisnis utama tetap berada di masing-masing aplikasi
- secret, token, dan kredensial tetap dipasang manual di server

Catatan keamanan
- repo hanya menyimpan template dan dokumentasi
- route atau guard khusus lintas domain perlu diverifikasi lagi setelah deploy gateway
