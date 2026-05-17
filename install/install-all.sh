#!/usr/bin/env bash
set -euo pipefail
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$BASE_DIR/install-shared-deps.sh"
bash "$BASE_DIR/install-dasborpim.sh"
bash "$BASE_DIR/install-incidents.sh"
bash "$BASE_DIR/install-incident-portal.sh"
bash "$BASE_DIR/install-certificate-generator.sh"
bash "$BASE_DIR/install-hermes-agent.sh"
bash "$BASE_DIR/install-hermes-gateway.sh"
echo "Full stack install step selesai. Lanjut copy .env, token, config, DB restore, dan verifikasi manual."
