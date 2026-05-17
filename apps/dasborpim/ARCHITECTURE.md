# Resume Arsitektur - Dashboard Pimpinan (Bidang Legal Drafter)

## Ringkasan
Dashboard monitoring Rapat Harmonisasi untuk Bidang Legal Drafter (Pemerintahan Daerah Jawa Barat).
Flask + SQLAlchemy + Chart.js. SQLite (dev) / PostgreSQL (prod).

## Struktur Direktori
```
dasborpim/
├── app.py              # Factory: create_app()
├── config.py           # Konfigurasi (SECRET_KEY, DATABASE_URL, dll)
├── models/__init__.py  # SQLAlchemy models
├── routes/
│   ├── auth.py         # Login/logout (auth_bp)
│   ├── operator.py     # CRUD data (operator_bp) - prefix: /operator
│   ├── dashboard.py    # Dashboard pimpinan (dashboard_bp)
│   └── api.py          # REST API (api_bp) - prefix: /api
├── templates/
│   ├── base.html       # Layout umum (navbar, footer)
│   ├── login.html      # Form login
│   ├── operator/       # Template operator (form input, list)
│   └── dashboard/      # Template dashboard (chart, drill-down)
├── static/css/style.css
└── instance/dasborpim.db
```

## Arsitektur Backend

### app.py (Application Factory)
- Membuat Flask app via `create_app()`
- Inisialisasi: SQLAlchemy, Flask-Login, CSRFProtect
- Mendaftarkan 4 blueprint: auth, operator, dashboard, api
- Login manager redirect ke auth.login

### models/__init__.py (2 Model)

#### User
- Kolom: id, username, password_hash, role, nama_lengkap, created_at
- Role: "operator", "pimpinan", "admin"
- Method: set_password(), check_password()
- Property: is_operator, is_pimpinan, is_admin

#### RapatHarmonisasi
- Kolom: id, tanggal_rapat(Date), daerah, jenis, program_pembentukan, urusan_pemerintahan, nama_raperda, tim_kerja, hasil, metode, keterangan, created_by, created_at, updated_at
- Pilihan disimpan sebagai constant CLASS-level:
  - JENIS_CHOICES: ["Raperda (DPRD)", "Raperda (Pemda)", "Raperkada"]
  - PROGRAM_CHOICES: ["Propemperda", "Propemperkada", "Di luar Propemperkada"]
  - TIM_KERJA_CHOICES: ["Tim Kerja 1" s/d "Tim Kerja 4"]
  - HASIL_CHOICES: ["Selesai", "Dikembalikan"]
  - METODE_CHOICES: ["One Day Service", "Normal"]
  - DAERAH_CHOICES: 27 Kabupaten/Kota di Jawa Barat
  - URUSAN_PEMERINTAHAN_CHOICES: 13 urusan

### routes/auth.py
- `/login` GET/POST: Form login, redirect ke operator.index
- `/logout`: Logout, redirect ke dashboard.index

### routes/operator.py (Prefix: /operator)
- `before_request`: Cek login, block pimpinan dari akses input
- `GET /operator/`: List data dengan pagination (20/page) + filter tanggal
- `GET|POST /operator/tambah`: Form tambah data
- `GET|POST /operator/edit/<id>`: Form edit data
- `POST /operator/hapus/<id>`: Hapus data

### routes/dashboard.py
- `GET /`: Dashboard utama
  - hitung ringkasan (total, per_hasil, per_metode)
  - kirim ke template: ringkasan, is_pimpinan, tanggal_dari/sampai

### routes/api.py (Prefix: /api)
REST API untuk data & chart:
- `GET /api/`: List endpoints (metadata)
- `GET /api/metadata`: Daftar filter & pilihan
- `GET /api/rapat-harmonisasi`: List data dengan filter (page, per_page, filter)
- `GET /api/rekapitulasi`: Aggregasi per daerah/jenis/program/urusan/tim/hasil/metode
- `GET /api/chart/<kategori>`: Chart data untuk kategori tertentu
- `GET /api/chart/bulanan`: Chart per bulan
- `GET /api/drill`: Drill-down hierarkis (breakdown → records)
- `GET /api/ringkuman`: Ringkasan teks untuk agent
- `GET /api/bandingkan`: Bandingkan 2 periode
- `GET /api/cari`: Full-text search

## Arsitektur Frontend

### base.html (Layout)
- Bootstrap 5.3.3 + Bootstrap Icons
- Chart.js 4.4.7 (CDN)
- Navbar: Dashboard, Input Data (jika authenticated), Login/Logout
- Flash messages dari Flask

### dashboard/index.html
Struktur:
1. **Filter tanggal**: Form GET dengan tanggal_dari & tanggal_sampai
2. **Kartu ringkasan**: 4 card (Total, Selesai, Dikembalikan, ODS) - clickable
3. **Charts** (jika pimpinan): per Daerah, per Jenis, per Status, per Metode, per Tim
4. **Drill-down section**: Breadcrumb + Search + Breakdown/Records

JavaScript Architecture:
- Global state: `currentFilters`, `isSearching`, `searchTimer`
- Functions:
  - `loadRecordsFromCard(tipe)`: Load data dari card click → tampilkan tabel langsung
  - `loadDrill()`: Load drill-down dari /api/drill
  - `selectItem(kategori, nilai)`: Pilih item drill-down → ADD ke currentFilters
  - `renderBreakdown(data)`: Render list breakdown (link + badge jumlah)
  - `renderRecords(data)`: Render tabel records
  - `searchDebounce()` / `searchData(q)`: Full-text search dengan debounce
  - `clearSearch()`: Reset search
  - `updateBreadcrumb()`: Update breadcrumb dari currentFilters (dengan try-catch)
  - `resetAll()`: Reset semua state
  - `goTo(index)`: Navigate breadcrumb ke level tertentu
  - `loadCharts()`: Load semua chart dari /api/rekapitulasi

## Kunci Arsitektur

### Drill-down Flow
1. User klik kartu ringkasan → `loadRecordsFromCard()` → tampilkan tabel
2. User klik tombol "Drill-Down" → `loadDrill()` → tampilkan breakdown
3. User pilih item (contoh: "Kota Depok") → `selectItem('daerah', 'Kota Depok')`
   - SET `currentFilters['daerah'] = 'Kota Depok'` (TIDAK reset!)
   - `loadDrill()` → fetch `/api/drill?daerah=Kota+Depok`
   - API return breakdown berikutnya (jenis)
4. User pilih item lagi (contoh: "Raperda") → `selectItem('jenis', 'Raperda (Pemda)')`
   - SET `currentFilters = {daerah: 'Kota Depok', jenis: 'Raperda (Pemda)'}`
   - `loadDrill()` → fetch dengan semua filter
   - API return records karena sudah cukup filter

### State Management
- `currentFilters`: Object {kategori: nilai} - KUMULATIF (tidak direset saat selectItem)
- `isSearching`: Boolean - apakah sedang dalam mode search
- `searchTimer`: Timer ID untuk debounce

### PENTING - Bug yang Diperbaiki
1. **Extra `>` di `<tr>>`**: Typo menyebabkan karakter `>` muncul di record table
2. **selectItem RESET currentFilters**: Awalnya mereset ke {} sebelum set filter baru, menyebabkan multi-level drill-down gagal. Fix: HAPUS reset, langsung SET currentFilters[kategori] = nilai
3. **Breadcrumb null error**: Akses `document.getElementById('breadcrumbList')` gagal karena HTML di-overwrite. Fix: gunakan try-catch, pastikan ID `breadcrumbList` tetap ada

### Helper Pattern
Semua helper API query menggunakan pattern yang sama:
- `_get_query(tanggal_dari, tanggal_sampai)`: Base query dengan filter tanggal
- `_apply_filters(query, filters)`: Apply filter kategoris
- `_record_to_dict(r)`: Convert model ke dict

### Deployment
- Service systemd: `/etc/systemd/system/dasborpim.service`
- Script startup: `/home/ubnt/start_dasborpim.sh`
- Koneksi database via DATABASE_URL environment variable

## Catatan untuk Pengembangan Layanan Lain
- Pola factory app (`create_app()`) dengan blueprint terpisah
- Model di `models/__init__.py`, filter pilihan sebagai class-level constants
- API dibagi: data, rekap, chart, search, metadata
- Frontend: Jinja2 template + vanilla JS + Chart.js
- State management: global object, kumulatif untuk drill-down
- Semua response API return JSON
