Checklist Manual Secrets dan Kredensial

Gunakan dokumen ini saat deploy ke server baru.

Checklist umum
- .env asli tiap aplikasi tersedia
- token Telegram tersedia
- API key/provider Hermes tersedia
- Google OAuth/token tersedia bila diperlukan
- password database tersedia
- password admin awal disimpan aman

Per komponen
1. Dasborpim
- SECRET_KEY
- DATABASE_URL

2. Incident Engine
- DATABASE_URL
- credential Google bila fitur aktif

3. Incident Portal
- SECRET_KEY
- DATABASE_URL
- ADMIN_* dan DEFAULT_EMPLOYEE_PASSWORD
- env notifikasi bila dipakai

4. Certificate Generator
- SECRET_KEY
- ADMIN_*
- GOOGLE_TOKEN_PATH
- token Google
- font/template final

5. Hermes
- ~/.hermes/.env
- SOUL.md final
- config.yaml final
- memory/skills bila dimigrasikan
- token bot Telegram dan allowlist chat/topic bila gateway dipakai

Aturan utama
- jangan simpan secret di repo git
- gunakan .env.example hanya sebagai acuan
- verifikasi permission file sensitif
