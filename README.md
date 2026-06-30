Hermes-KemenkumJabar-Apps

Paket aplikasi internal untuk deployment, migrasi, dokumentasi operasional, dan integrasi Hermes secara modular.

Komponen utama:
- Dasborpim
- Incident App (Portal + Incident Engine)
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
- instalasi diarahkan non-interaktif melalui skrip + file env yang diisi user sendiri

Struktur repo
- apps/
  Source code aplikasi yang sudah dibersihkan dari artefak sensitif dan runtime junk.
- docs/
  Dokumentasi arsitektur, instalasi, integrasi, migrasi, backup, dan troubleshooting.
- install/
  Installer modular per komponen, template env, dan installer gabungan.
- deploy/
  Template systemd, cron, dan nginx.
- migration/
  Checklist manual secrets, verifikasi pasca instalasi, dan helper migrasi.
- .hermes-template/
  Template SOUL.md, config.yaml.example, gateway.env.example, dan memory example.

Struktur aplikasi insiden
- apps/incident-portal/
  Web app admin/pegawai.
- apps/incident-portal/incident_engine/
  Engine inti tiket, histori, bukti, dan integrasi Drive.

Mode penggunaan
1. Install aplikasi tertentu saja
2. Install stack insiden
   - Incident App (portal + engine dalam satu folder induk)
3. Install Hermes saja
4. Install full stack

Quick start non-interaktif
1. Baca docs/00-arsitektur.md
2. Baca docs/01-prasyarat-server.md
3. Baca docs/10-env-secrets-checklist.md
4. Salin template env dari install/templates/
5. Isi semua nilai __REQUIRED__ dengan data final user sendiri
6. Jalankan installer sesuai kebutuhan:
   - bash install/install-shared-deps.sh
   - bash install/install-dasborpim.sh --env-file /path/dasborpim.env
   - bash install/install-incidents.sh --env-file /path/incidents.env
   - bash install/install-incident-portal.sh --env-file /path/incident-portal.env
   - bash install/install-certificate-generator.sh --env-file /path/certificate-generator.env
   - bash install/install-hermes-agent.sh --env-file /path/hermes-agent.env
   - bash install/install-hermes-gateway.sh --env-file /path/hermes-gateway.env
   - bash install/install-all.sh --config-dir /path/config-dir
