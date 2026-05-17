# AGENTS.md - Incident Log Kementerian Hukum Jawa Barat

## Fokus Folder
Folder ini khusus untuk sistem tiket/insiden di:
`/home/ubnt/incidents`

## Aturan Utama
1. Gunakan data live dari sistem incident yang aktif; jangan mengambil status/angka dari history chat.
2. Selalu gunakan istilah `Kementerian Hukum` atau `Kemenkum`.
3. Output chat harus ringkas, HP-friendly, dan operasional.
4. Jika ada update tiket, prioritaskan ketelitian status, durasi, petugas, dan bukti.

## Sapaan dan Gaya Jawaban
Untuk konteks folder ini, gunakan sapaan:
`Bos`

Pembuka utama:
`Izin melaporkan Bos, berdasarkan pengecekan data terbaru pada sistem...`

Gunakan sapaan ini untuk hal-hal seperti:
- tiket
- insiden
- wifi
- internet
- jaringan
- komputer
- laptop
- printer
- gangguan teknis
- histori tiket
- update tiket
- dashboard tiket

## Referensi Sistem
Script utama:
- `/home/ubnt/incidents/incident_writer.py`
- `/home/ubnt/incidents/incident_db.py`

Database utama PostgreSQL:
- `incidents`
- `incident_history`
- `incident_attachments`

Dashboard yang dipakai:
- portal web `/home/ubnt/incident-portal`
- Google Sheets dashboard sudah tidak digunakan

## Aturan Operasional
1. Status resmi yang dipakai:
   - OPEN
   - IN_PROGRESS
   - PENDING
   - RESOLVED
   - CLOSED
2. `PENDING` wajib punya alasan yang jelas.
3. Referensi tiket di chat utamakan bentuk singkat seperti `tiket 6`.
4. Saat menampilkan tiket di chat, gunakan format HP-friendly satu baris per item.
5. Jika durasi tersedia, tampilkan durasi dalam laporan status.
6. Bukti foto yang dikirim saat status aktif masuk kelompok `bukti_awal`; saat status terminal masuk kelompok `bukti_resolve`.
7. Semua bukti tetap masuk ke folder Google Drive tiket yang sama, dan histori harus tetap bisa ditelusuri.

## Format Chat Tiket
Format utama:
`alias | KODE | LOKASI | MASALAH | STATUS`

Jika histori:
- satu baris ringkasan tiket
- lalu update per baris, urut lama ke baru

## Batasan Konteks
Jika permintaan ternyata dominan ke:
- harmonisasi
- API Dasborpim
- statistik rapat
- dashboard pimpinan
- laporan kelembagaan
maka konteks itu bukan domain utama folder ini, dan sapaan yang berlaku di domain tersebut adalah `Pak Kakanwil`.

## Catatan Teknis
Folder proyek aktif saat ini tetap:
`/home/ubnt/incidents`

Menambah file AGENTS.md di sini tidak boleh mengubah script inti incident atau alur upload bukti yang sudah berjalan.
