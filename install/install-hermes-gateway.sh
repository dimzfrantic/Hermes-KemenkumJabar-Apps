#!/usr/bin/env bash
set -euo pipefail
if ! command -v hermes >/dev/null 2>&1; then
  echo "ERROR: Hermes belum terpasang"
  exit 1
fi
cat <<'EOF'
Hermes Gateway baseline siap.
Langkah manual berikutnya:
1. Siapkan env Telegram secara manual
2. Jalankan hermes gateway setup
3. Jalankan hermes gateway install
4. Jalankan hermes gateway start
5. Verifikasi dengan hermes gateway status dan cek gateway.log
6. Uji DM serta grup/topik yang akan dipakai dengan pesan nyata
EOF
