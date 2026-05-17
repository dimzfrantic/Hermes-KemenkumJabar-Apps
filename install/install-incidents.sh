#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../apps/incidents" && pwd)"
cd "$APP_DIR"
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cat <<'EOF'
Incident Engine selesai diinstall pada level dependency.
Langkah manual berikutnya:
1. Buat/copy .env final
2. Siapkan PostgreSQL dan DATABASE_URL
3. Siapkan credential Google bila integrasi Drive aktif
4. Uji create/list/update tiket secara manual
EOF
