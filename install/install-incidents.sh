#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$BASE_DIR/../apps/incident-portal/incident_engine" && pwd)"
ENV_FILE=""
PYTHON_BIN="python3"
SKIP_VENV=false

# shellcheck disable=SC1091
source "$BASE_DIR/lib/common.sh"

usage() {
  cat <<'EOF'
Usage:
  install/install-incidents.sh --env-file /path/to/incidents.env [options]

Required env vars in --env-file:
  DATABASE_URL

Optional env vars:
  INCIDENT_DATABASE_URL
  GOOGLE_TOKEN_PATH
  GOOGLE_CLIENT_SECRET_PATH

Options:
  --app-dir PATH      Override direktori aplikasi
  --python BIN        Override interpreter Python
  --skip-venv         Jangan buat ulang/install venv
  -h, --help          Tampilkan bantuan
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file) ENV_FILE="$2"; shift ;;
    --app-dir) APP_DIR="$2"; shift ;;
    --python) PYTHON_BIN="$2"; shift ;;
    --skip-venv) SKIP_VENV=true ;;
    -h|--help) usage; exit 0 ;;
    *) usage_error "Argumen tidak dikenal: $1" ;;
  esac
  shift
done

[[ -n "$ENV_FILE" ]] || die "Gunakan --env-file"
load_env_file "$ENV_FILE"
require_vars DATABASE_URL
maybe_require_vars INCIDENT_DATABASE_URL GOOGLE_TOKEN_PATH GOOGLE_CLIENT_SECRET_PATH

copy_env_file "$ENV_FILE" "$APP_DIR/.env"
install_python_requirements "$APP_DIR" "$PYTHON_BIN" "$SKIP_VENV"

log "Verifikasi CLI Incident Engine"
(cd "$APP_DIR" && ./.venv/bin/python incident_writer.py --help >/dev/null)

log "Incident Engine selesai diinstall"
