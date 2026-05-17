#!/usr/bin/env bash
set -euo pipefail
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Install shared dependencies"
bash "$BASE_DIR/install-shared-deps.sh"

echo "==> Install Dasborpim"
bash "$BASE_DIR/install-dasborpim.sh"

echo "==> Install Incident Engine"
bash "$BASE_DIR/install-incidents.sh"

echo "==> Install Incident Portal"
bash "$BASE_DIR/install-incident-portal.sh"

echo "==> Install Certificate Generator"
bash "$BASE_DIR/install-certificate-generator.sh"

echo "==> Install Hermes Agent"
bash "$BASE_DIR/install-hermes-agent.sh"

echo "==> Prepare Hermes Gateway"
bash "$BASE_DIR/install-hermes-gateway.sh"

cat <<'EOF'
Full stack baseline installation selesai.
Langkah manual berikutnya:
1. Copy semua .env final dan credential
2. Restore database bila migrasi
3. Review dan aktifkan systemd service
4. Review dan aktifkan cron yang diperlukan
5. Jalankan checklist verifikasi pasca instalasi
EOF
