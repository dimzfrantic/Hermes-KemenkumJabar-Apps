Migrasi SOUL, AGENTS, Memory, dan Konteks Hermes

Dokumen ini menjelaskan migrasi konteks Hermes dari server lama ke server baru.

Komponen migrasi utama
1. SOUL.md
- identitas global Hermes
- aman dipindahkan setelah review isi

2. AGENTS.md
- konteks lokal tiap aplikasi
- ikut bersama source code aplikasi
- review path absolut bila server berubah

3. MEMORY.md
- catatan stabil lintas sesi
- dipindah manual bila continuity dibutuhkan

4. USER.md
- preferensi user dan pola interaksi
- dipindah manual bila diperlukan

5. skills
- sangat disarankan ikut dipindah

6. config.yaml
- boleh dipindah setelah direview
- jangan salin mentah tanpa cek path dan provider

7. state.db
- opsional
- diperlukan bila ingin continuity session_search dan histori sesi

Mode migrasi yang disarankan
- mode ringan: SOUL.md, AGENTS.md, MEMORY.md, USER.md, skills, config yang dibersihkan
- mode penuh: semua di atas ditambah state.db/sessions bila perlu

Langkah verifikasi pasca migrasi
1. jalankan hermes doctor
2. cek hermes memory status
3. pastikan SOUL.md terbaca
4. pastikan AGENTS.md terbaca di folder aplikasi aktif
5. pastikan skills tersedia
6. uji provider/model
7. uji gateway bila dipakai

Jangan masuk git
- ~/.hermes/.env
- auth/token provider
- state produksi
- session produksi

Verifikasi pasca migrasi
- hermes doctor sukses
- hermes memory status sesuai
- SOUL.md terbaca
- AGENTS.md terbaca di folder aplikasi
- skills tersedia
