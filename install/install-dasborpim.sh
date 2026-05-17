#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../apps/dasborpim" && pwd)"
cd "$APP_DIR"
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cat <<'EOF'
Dasborpim selesai diinstall pada level dependency.
Langkah manual berikutnya:
1. Buat/copy .env final
2. Siapkan PostgreSQL dan DATABASE_URL
3. Review deploy/systemd/dasborpim.service
4. Review deploy/nginx/dasborpim.nginx.conf bila memakai reverse proxy
EOF
