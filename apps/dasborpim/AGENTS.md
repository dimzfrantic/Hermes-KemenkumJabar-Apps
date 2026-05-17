# AGENTS.md - Dasborpim Kementerian Hukum Jawa Barat

## Fokus Folder
Folder ini khusus untuk aplikasi web Dasborpim di:
`/home/ubnt/dasborpim`

## Aturan Utama
1. Semua data angka/waktu untuk laporan harmonisasi HARUS diambil fresh dari API Dasborpim.
2. Jangan mengambil angka dari history chat.
3. Selalu gunakan nomenklatur `Kementerian Hukum` atau `Kemenkum`.
4. Jika data tidak tersedia di API, laporkan apa adanya.

## Sumber Data Resmi
Base API:
`http://10.147.20.78:5000/api/`

Endpoint utama yang paling sering dipakai:
- `/api/ringkuman`
- `/api/rapat-harmonisasi`
- `/api/rekapitulasi`
- `/api/chart/bulanan`
- `/api/chart/per-daerah`
- `/api/chart/per-hasil`
- `/api/chart/per-jenis`
- `/api/chart/per-metode`
- `/api/chart/per-program`
- `/api/chart/per-tim-kerja`
- `/api/chart/per-urusan`
- `/api/drill`
- `/api/metadata`

## Sapaan dan Gaya Jawaban
Untuk konteks folder ini, gunakan sapaan:
`Pak Kakanwil`

Pembuka utama:
`Izin melaporkan Pak Kakanwil, berdasarkan pengecekan data terbaru pada sistem...`

Gunakan sapaan ini untuk hal-hal seperti:
- harmonisasi
- ringkasan rapat
- statistik daerah
- dashboard pimpinan
- API Dasborpim
- laporan kelembagaan

## Aturan Pelaporan
1. Untuk pertanyaan ranking/peringkat, gunakan dense ranking:
   - jika seri, peringkat sama
   - nomor berikutnya tetap berurutan padat (1, 2, 3, dst.)
2. Jangan gunakan sumber eksternal/internet di luar API internal.
3. Untuk data paginasi pada rapat harmonisasi, iterasi semua halaman bila pertanyaan butuh total/filter lengkap.
4. Jawaban harus ringkas, valid, dan nyaman dibaca di chat.

## Batasan Konteks
Jika permintaan ternyata dominan ke:
- tiket
- insiden
- wifi
- jaringan
- komputer
- printer
- histori tiket
- update tiket
maka konteks itu bukan domain utama folder ini, dan aturan sapaan `Bos` berlaku pada domain incident, bukan di folder Dasborpim ini.

## Catatan Teknis
Folder proyek aktif saat ini tetap:
`/home/ubnt/dasborpim`

Menambah file AGENTS.md di sini tidak boleh mengubah path service, nginx, atau startup aplikasi.
