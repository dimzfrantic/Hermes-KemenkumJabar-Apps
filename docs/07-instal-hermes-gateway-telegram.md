Instalasi Hermes Gateway Telegram

Dokumen ini menjelaskan penyiapan Hermes Gateway agar Hermes dapat diakses lewat Telegram.

Prasyarat
- Hermes Agent sudah terinstal
- provider/model Hermes sudah sehat
- bot Telegram sudah dibuat
- token bot tersedia
- koneksi internet tersedia

Data yang perlu disiapkan
- TELEGRAM_BOT_TOKEN
- TELEGRAM_ALLOWED_USERS (opsional)
- TELEGRAM_HOME_CHANNEL (opsional)
- TELEGRAM_GROUP_ALLOWED_CHATS (opsional)
- TELEGRAM_GROUP_ALLOWED_USERS (opsional untuk kompatibilitas lama)
- TELEGRAM_TOPIC_INSIDEN_ID (opsional)
- TELEGRAM_REQUIRE_MENTION (opsional)
- TELEGRAM_FREE_RESPONSE_CHATS (opsional)

File konfigurasi
- ~/.hermes/.env untuk token sensitif
- ~/.hermes/config.yaml untuk perilaku gateway
- .hermes-template/gateway.env.example sebagai acuan template

Langkah instalasi
1. pastikan Hermes sehat
2. isi env Telegram secara manual
3. jalankan hermes gateway setup bila diperlukan
4. install service gateway
5. start gateway
6. cek status
7. uji DM
8. uji grup/topik bila diaktifkan

Perintah operasional penting
- hermes gateway install
- hermes gateway start
- hermes gateway stop
- hermes gateway restart
- hermes gateway status

Log penting
- ~/.hermes/logs/gateway.log

Verifikasi
- bot merespons DM
- bot merespons grup/topik sesuai konfigurasi
- log tidak menunjukkan error token atau routing fatal
- bila topik dipakai, verifikasi chat_id dan thread_id dari pesan nyata, bukan asumsi manual

Pola routing yang direkomendasikan
- DM untuk pelaporan/pemantauan yang bersifat personal atau pimpinan
- grup/topik operasional untuk domain spesifik
- jika satu bot dipakai lintas domain, pisahkan lane dengan channel_prompts dan guard yang jelas

Catatan keamanan
- jangan commit token Telegram
- batasi chat/group/topic yang diizinkan
- gunakan lane operasional yang jelas bila satu bot dipakai untuk banyak domain
