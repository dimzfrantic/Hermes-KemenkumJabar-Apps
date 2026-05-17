Systemd, Cron, dan Service Operasional

Dokumen ini menjelaskan template service dan cron pada stack ini.

Komponen yang umum dijalankan sebagai service
- Dasborpim
- Incident Portal
- Certificate Generator
- Hermes Gateway Telegram

System service vs user service
- system service cocok untuk aplikasi server utama
- user service cocok untuk layanan user-level seperti gateway tertentu
- sesuaikan dengan desain server tujuan

Template yang tersedia
- deploy/systemd/dasborpim.service
- deploy/systemd/incident-portal.service
- deploy/systemd/certificate-generator.service
- deploy/systemd/hermes-gateway.service
- deploy/cron/certificate-generator.cron
- deploy/cron/dasborpim.cron

Langkah umum aktivasi service
1. salin template ke lokasi final
2. review path, user, WorkingDirectory, ExecStart
3. daemon-reload
4. enable service
5. start service
6. cek status dan log

Langkah umum perubahan service
- edit template/final file
- reload daemon
- restart service
- verifikasi PID berubah dan log sehat

Cron
- gunakan cron hanya untuk pekerjaan periodik
- pada repo ini contoh utama adalah sinkronisasi otomatis Certificate Generator dan tugas bantu Dasborpim
- review path, user, env, dan log tujuan sebelum diaktifkan

Verifikasi
- file unit berada di lokasi final yang benar
- WorkingDirectory dan ExecStart sesuai path server target
- service start tanpa error
- cron dapat dieksekusi manual sebelum dijadwalkan

Catatan
- template deploy pada repo adalah baseline, bukan final produksi
- semua path absolut wajib disesuaikan dengan server target
- untuk gateway Hermes, perhatikan apakah implementasi akhir memakai user service atau metode install bawaan Hermes
