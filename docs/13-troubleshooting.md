Troubleshooting Umum

Dokumen ini merangkum masalah umum saat instalasi dan operasional stack.

1. Aplikasi gagal start
Kemungkinan penyebab:
- path WorkingDirectory salah
- venv salah
- dependency belum terpasang
- .env belum ada
- port bentrok
- permission salah

2. Dasborpim gagal jalan
- cek DATABASE_URL
- cek PostgreSQL
- cek gunicorn/service
- cek port bind dan nginx

3. Incident Engine gagal create/update/list
- cek DATABASE_URL
- cek schema/tabel
- cek dependency psycopg
- cek credential Google bila fitur aktif

4. Incident Portal tidak sinkron
- cek INCIDENT_DATABASE_URL
- cek backend Incident Engine
- cek service incident cache/gateway internal bila relevan

5. Certificate Generator gagal generate PDF
- cek LibreOffice/soffice
- cek SOFFICE_PATH
- cek font template
- cek permission folder kerja

6. Certificate Generator gagal upload Drive
- cek token Google
- cek scope
- cek path token
- cek koneksi internet

7. Hermes Agent gagal jalan
- cek hermes doctor
- cek provider/model
- cek ~/.hermes/.env
- cek config.yaml

8. Hermes tidak membaca persona/konteks
- cek SOUL.md
- cek AGENTS.md di folder aktif
- cek terminal.cwd
- mulai sesi Hermes baru

9. Telegram gateway tidak merespons
- cek token
- cek allowed chat/user/topic
- cek gateway.log
- cek provider Hermes sehat
- bila grup atau forum tidak merespons, verifikasi chat_id dan thread_id dari pesan nyata

10. Service jalan tapi memakai config lama
- lakukan restart penuh service
- cek daemon-reload
- cek PID/log terbaru

11. Routing lintas domain salah
- cek telegram.channel_prompts
- cek guard atau short-circuit pre-agent bila dipakai
- verifikasi lane DM, grup, dan topik sesuai desain
- lakukan uji nyata setelah restart gateway

Prinsip troubleshooting
- uji manual dulu sebelum menyalahkan systemd
- bedakan error aplikasi, env, service, dan integrasi
- cek log sebelum melakukan banyak perubahan sekaligus
