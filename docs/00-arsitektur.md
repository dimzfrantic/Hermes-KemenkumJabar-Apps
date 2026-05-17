Arsitektur Hermes-KemenkumJabar-Apps

Dokumen ini menjelaskan hubungan antar komponen utama dalam repo Hermes-KemenkumJabar-Apps.

Komponen utama
1. Dasborpim
   Dashboard pimpinan dan aplikasi domain pelaporan/kelembagaan.

2. Incident Engine
   Backend utama untuk tiket dan insiden, sumber status resmi operasional.

3. Incident Portal
   Frontend pegawai untuk login, input tiket, dan melihat status tiket.

4. Certificate Generator
   Aplikasi pembuat sertifikat dari template PPTX ke PDF dengan integrasi Google Drive/Sheets.

5. Hermes Agent
   Layer otomasi dan asisten operasional berbasis terminal, memory, skills, SOUL.md, dan AGENTS.md.

6. Hermes Gateway Telegram
   Jembatan komunikasi Telegram ke Hermes Agent.

Prinsip arsitektur
- modular: tiap komponen dapat dipasang terpisah
- terstruktur: source, deploy template, dan docs dipisah rapi
- aman: file sensitif tidak masuk repo git
- migratable: persona, AGENTS, memory, dan service dapat dipindah secara terkontrol
- operasional: systemd, cron, dan env dibuat eksplisit

Relasi komponen
1. Dasborpim
   - berdiri sebagai aplikasi web tersendiri
   - untuk data numerik dan waktu tetap mengacu ke API internal resmi

2. Incident Engine
   - menjadi backend resmi tiket dan histori insiden
   - menjadi sumber data utama bagi portal dan workflow insiden

3. Incident Portal
   - membaca dan menulis alur tiket melalui Incident Engine
   - bukan sumber status utama, melainkan frontend pegawai

4. Certificate Generator
   - berdiri sebagai aplikasi layanan dokumen
   - memerlukan LibreOffice/soffice, font, dan token Google bila integrasi aktif

5. Hermes Agent
   - memahami konteks global dari SOUL.md
   - memahami konteks lokal dari AGENTS.md tiap aplikasi
   - membantu deployment, audit, dokumentasi, troubleshooting, dan operasional

6. Hermes Gateway Telegram
   - memberi jalur DM/grup/topik ke Hermes
   - dapat dipisahkan lane operasionalnya sesuai domain

Mode deployment
1. Single app
   Contoh: hanya Dasborpim atau hanya Certificate Generator.

2. Incident stack
   - Incident Engine
   - Incident Portal

3. Hermes only
   - Hermes Agent
   - Hermes Gateway Telegram

4. Full stack
   - semua aplikasi
   - Hermes Agent
   - Hermes Gateway Telegram

Alur data ringkas
- Dasborpim: API internal -> aplikasi Dasborpim -> web dashboard -> pengguna
- Incident: pegawai/operator -> Incident Portal / workflow -> Incident Engine -> PostgreSQL
- Sertifikat: operator -> Certificate Generator -> PPTX/PDF -> Google Drive
- Hermes: pengguna -> Telegram/CLI -> Hermes -> konteks aplikasi -> jawaban/aksi operasional

Catatan implementasi
- path absolut pada AGENTS.md, systemd, cron, dan config wajib ditinjau jika server tujuan berbeda
- secret dan kredensial selalu dipindah manual
- state/history Hermes bersifat opsional dalam migrasi penuh
