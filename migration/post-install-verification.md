Checklist Verifikasi Pasca Instalasi

Verifikasi umum server
- python3 tersedia
- PostgreSQL aktif
- nginx aktif bila dipakai
- LibreOffice tersedia bila Certificate Generator dipasang

Verifikasi aplikasi
1. Dasborpim
- start sukses
- database dapat diakses
- halaman dapat dibuka

2. Incident Engine
- create/list/update tiket berhasil
- schema tersedia

3. Incident Portal
- login admin berhasil
- buat tiket berhasil
- sinkron status berhasil

4. Certificate Generator
- login admin berhasil
- generate PDF berhasil
- upload Drive berjalan bila aktif

Verifikasi Hermes
- hermes doctor sukses
- model dapat dipanggil
- SOUL.md dan AGENTS.md terbaca
- gateway status sehat bila dipakai
- bila satu bot dipakai lintas domain, uji masing-masing lane dengan pesan nyata

Verifikasi keamanan
- tidak ada secret tertinggal di repo kerja
- permission credential sesuai
- backup awal pasca deploy sudah dibuat
