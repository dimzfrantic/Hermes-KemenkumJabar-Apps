Instalasi Hermes Agent

Dokumen ini menjelaskan instalasi Hermes Agent sebagai layer otomasi dan asisten operasional.

Tujuan
- menjalankan assistant terminal
- memakai SOUL.md, AGENTS.md, memory, dan skills
- menjadi fondasi untuk gateway Telegram

Path penting Hermes
- ~/.hermes/config.yaml
- ~/.hermes/.env
- ~/.hermes/SOUL.md
- ~/.hermes/memories/MEMORY.md
- ~/.hermes/memories/USER.md
- ~/.hermes/skills/
- ~/.hermes/logs/
- ~/.hermes/state.db

Prasyarat
- python3 tersedia
- curl tersedia untuk installer resmi berbasis shell
- koneksi internet tersedia untuk instalasi awal dan provider yang dipakai
- kredensial provider/model sudah disiapkan terpisah dari repo

Langkah instalasi
1. Jalankan installer Hermes atau gunakan script resmi
2. Verifikasi binary hermes tersedia
3. Jalankan setup awal
4. Pilih provider/model
5. Isi ~/.hermes/.env secara manual
6. Review ~/.hermes/config.yaml
7. Jalankan hermes doctor

Perintah penting
- hermes setup
- hermes model
- hermes doctor
- hermes config path
- hermes config env-path
- hermes tools list
- hermes memory status
- hermes skills list
- hermes gateway status

Konfigurasi dasar yang perlu ditinjau
- model.provider
- model.default
- model.base_url
- terminal.cwd
- toolsets
- memory.memory_enabled
- memory.user_profile_enabled
- display.platforms.telegram.tool_progress bila gateway Telegram dipakai
- telegram.channel_prompts bila satu bot dipakai untuk lebih dari satu lane/domain

Migrasi yang didukung
- SOUL.md
- AGENTS.md per aplikasi
- MEMORY.md
- USER.md
- skills
- config.yaml setelah direview
- state.db secara opsional

Verifikasi pasca instalasi
- command hermes dikenali shell
- hermes doctor sukses
- hermes config path menunjuk ke file yang benar
- hermes config env-path menunjuk ke env yang benar
- model dapat dipanggil
- skills tersedia bila dimigrasikan
- memory status sesuai harapan

Catatan keamanan
- ~/.hermes/.env tidak boleh masuk git
- auth/token provider tidak boleh masuk git
- file memory produksi dipindah manual bila diperlukan
- config final boleh dipindah, tetapi tetap harus ditinjau ulang bila path atau provider berubah
