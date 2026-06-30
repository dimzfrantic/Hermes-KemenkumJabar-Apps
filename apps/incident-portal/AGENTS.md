# AGENTS.md - Incident Portal

## Fokus Folder
Folder ini khusus untuk portal web pegawai/admin pelaporan insiden TI di:
`apps/incident-portal/`

## Peran Aplikasi
Portal ini adalah wajah depan untuk:
- login pegawai
- input tiket baru
- melihat status tiket milik sendiri
- operasional/admin tiket
- sinkron status dari sistem incident utama

Sistem incident utama berada di:
`apps/incident-portal/incident_engine/`

## Aturan Utama
1. Portal ini tidak boleh memutus alur incident engine.
2. Pembuatan tiket baru dari portal harus masuk ke sistem incident utama.
3. Data status tiket yang tampil harus sinkron dengan data incident aktif/arsip.
4. Folder ini menjadi folder induk tunggal untuk portal, auth, master pegawai, dan integrasi ke incident engine.
