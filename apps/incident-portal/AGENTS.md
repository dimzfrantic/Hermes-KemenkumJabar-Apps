# AGENTS.md - Incident Portal Kementerian Hukum Jawa Barat

## Fokus Folder
Folder ini khusus untuk portal web pegawai pelaporan insiden TI di:
`/home/ubnt/incident-portal`

## Peran Aplikasi
Portal ini adalah wajah depan untuk pegawai:
- login pegawai
- input tiket baru
- melihat status tiket milik sendiri
- sinkron status dari sistem incident utama

Sistem incident utama tetap berada di:
`/home/ubnt/incidents`

## Aturan Utama
1. Portal ini tidak boleh memutus alur incident yang sudah berjalan di `/home/ubnt/incidents`.
2. Pembuatan tiket baru dari portal harus masuk ke sistem incident utama.
3. Data status tiket yang tampil ke pegawai harus sinkron dengan data incident aktif/arsip.
4. Gunakan nomenklatur `Kementerian Hukum` atau `Kemenkum`.
5. Folder ini hanya untuk portal web pegawai, auth, master pegawai, dan integrasi ke incident engine.

## Login Pegawai
- login menggunakan NIP
- akun pegawai diimpor dari file Excel master
- password awal dapat ditentukan admin
- pegawai wajib mengganti password saat login pertama

## Integrasi Incident
- submit tiket portal harus membuat tiket baru di incident engine
- update status lanjutan tetap bisa dilakukan oleh petugas TI melalui Signal seperti alur saat ini
- dashboard pegawai harus menampilkan status terbaru tiket miliknya

## Notifikasi Signal
- notifikasi tiket baru dikirim ke grup Signal TI jika konfigurasi `SIGNAL_ACCOUNT` dan `SIGNAL_GROUP_ID` tersedia
- jika konfigurasi Signal belum diisi, portal tetap boleh membuat tiket, tetapi notifikasi grup dicatat sebagai pending/failed di log lokal aplikasi

## Catatan Teknis
- Jangan memindahkan folder `/home/ubnt/incidents` atau `/home/ubnt/dasborpim` dari portal ini.
- Portal ini adalah aplikasi terpisah, bukan subfolder dari `incidents`.
