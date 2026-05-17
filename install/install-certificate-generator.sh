#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../apps/certificate-generator" && pwd)"
cd "$APP_DIR"
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cat <<'EOF'
Certificate Generator selesai diinstall pada level dependency.
Langkah manual berikutnya:
1. Copy .env.example menjadi .env lalu sesuaikan
2. Pastikan LibreOffice/soffice tersedia
3. Install font yang diperlukan template
4. Copy token Google secara manual
5. Review deploy/systemd/certificate-generator.service
6. Review deploy/cron/certificate-generator.cron
EOF
