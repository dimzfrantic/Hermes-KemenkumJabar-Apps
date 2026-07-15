Instalasi Incident Portal

Dokumen ini menjelaskan instalasi portal web pegawai/admin untuk pelaporan insiden TI.

Ringkasan
- Frontend pegawai dan admin
- Terkoneksi ke incident engine internal
- Dapat memakai notifikasi Telegram sesuai env

Lokasi source
- `apps/incident-portal/`
- `apps/incident-portal/incident_engine/`

File penting
- `apps/incident-portal/app.py`
- `apps/incident-portal/config.py`
- `apps/incident-portal/wsgi.py`
- `apps/incident-portal/requirements.txt`
- `apps/incident-portal/services/incident_gateway.py`
- `apps/incident-portal/incident_engine/incident_writer.py`
- `install/install-incident-portal.sh`
- `install/templates/incident-portal.env.example`

Langkah instalasi via skrip
1. Salin template env
   cp install/templates/incident-portal.env.example /tmp/incident-portal.env
2. Isi parameter wajib
   - SECRET_KEY
   - DATABASE_URL
   - DEFAULT_EMPLOYEE_PASSWORD
   - ADMIN_NIP
   - ADMIN_NAME
   - ADMIN_PASSWORD
   - INCIDENT_DATABASE_URL
3. Isi parameter opsional bila dipakai
   - INCIDENTS_DIR
   - INCIDENT_WRITER_PATH
   - TELEGRAM_BOT_TOKEN
   - TELEGRAM_GROUP_ID
   - TELEGRAM_TOPIC_INSIDEN_ID
4. Jalankan installer
   bash install/install-incident-portal.sh --env-file /tmp/incident-portal.env

Yang dilakukan installer
- menyalin file env ke `apps/incident-portal/.env`
- membuat virtual environment portal bila belum ada
- meng-install dependency Python portal
- memverifikasi aplikasi dengan `create_app()`

Verifikasi integrasi
- admin dapat login
- tiket baru dari portal masuk ke incident engine
- status tiket dapat dibaca kembali
- upload bukti berjalan
- notifikasi grup bekerja bila diaktifkan

Fitur operasional
- `Admin > Operasional Tiket` menampilkan panel Drive Token Guard.
- Panel ini mengecek kesiapan token Google Drive dan jumlah bukti pending.
- Jika upload bukti gagal karena token Drive, file tetap dicatat sebagai pending evidence lokal.
- Setelah token valid, admin dapat menekan tombol retry bukti pending.
- `Admin > Riwayat Tiket` menampilkan histori update tiket dari database incident live dan mendukung pencarian alias seperti `tiket 2`.

Env terkait Google Drive
- `GOOGLE_TOKEN_PATH` menunjuk token OAuth Drive.
- `GOOGLE_CLIENT_SECRET_PATH` disimpan manual di server, jangan commit ke git.
- `BUKTI_ROOT_FOLDER_ID` menunjuk folder induk bukti Drive.

Pembaharuan Token Google Drive

Token Google Drive biasanya diperbarui otomatis selama `refresh_token` masih valid. Prosedur manual di bawah hanya diperlukan bila Drive Token Guard menampilkan token bermasalah, atau upload bukti gagal dengan pesan seperti `invalid_grant` / `Token/akses Google Drive perlu diperbarui`.

Lokasi token runtime:
- ikuti nilai env `GOOGLE_TOKEN_PATH`
- contoh instalasi: `/opt/kemenkumjabar/credentials/google_token.json`

Langkah manual:

1. Masuk ke server aplikasi.

2. Masuk ke folder engine incident:

   ```bash
   cd /opt/kemenkumjabar/apps/incident-portal/incident_engine
   ```

   Untuk instalasi non-produksi, sesuaikan path dengan lokasi deploy masing-masing.

3. Generate URL otorisasi Google:

   ```bash
   ../.venv/bin/python3 reauth_google_drive.py auth-url
   ```

4. Buka URL yang muncul di browser.

5. Login memakai akun Google Drive yang digunakan untuk menyimpan bukti tiket.

6. Izinkan akses Google Drive.

7. Setelah Google redirect ke alamat seperti di bawah, halaman `localhost` boleh gagal/blank; itu normal.

   ```text
   http://localhost:8089/?state=...&code=...&scope=...
   ```

8. Salin seluruh URL callback dari address bar browser.

9. Tukarkan callback URL menjadi token baru:

   ```bash
   OAUTHLIB_INSECURE_TRANSPORT=1 ../.venv/bin/python3 reauth_google_drive.py exchange 'URL_CALLBACK_DARI_BROWSER'
   ```

   Contoh format:

   ```bash
   OAUTHLIB_INSECURE_TRANSPORT=1 ../.venv/bin/python3 reauth_google_drive.py exchange 'http://localhost:8089/?state=...&code=...&scope=...'
   ```

10. Jika berhasil, output akan menampilkan:

    ```text
    TOKEN_OK
    ACCOUNT: akun-google-yang-dipakai
    ```

11. Pastikan permission token aman:

    ```bash
    chmod 600 "$GOOGLE_TOKEN_PATH"
    ```

    Jika env belum diekspor di shell, pakai path token yang tertulis di file `.env` portal.

12. Restart portal:

    ```bash
    systemctl --user restart incident-portal.service
    systemctl --user is-active incident-portal.service
    ```

    Status yang diharapkan:

    ```text
    active
    ```

13. Buka `Admin > Operasional Tiket`, lalu cek panel `Drive Token Guard`.

14. Jika ada bukti pending, klik `Retry bukti pending`.

Catatan keamanan:
- Jangan kirim isi file token ke chat.
- Jangan commit file token ke git.
- Jangan commit file client secret ke git.
- Jangan menulis nilai token, client secret, atau folder ID produksi ke dokumentasi publik.
