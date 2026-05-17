#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../apps/incident-portal" && pwd)"
cd "$APP_DIR"
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cat <<'EOF'
Incident Portal selesai diinstall pada level dependency.
Langkah manual berikutnya:
1. Copy .env.example menjadi .env lalu sesuaikan
2. Siapkan admin awal dan DATABASE_URL
3. Siapkan INCIDENT_DATABASE_URL untuk integrasi backend
4. Review deploy/systemd/incident-portal.service
EOF
