#!/usr/bin/env bash
set -euo pipefail
if ! command -v hermes >/dev/null 2>&1; then
  echo "ERROR: Hermes belum terpasang"
  exit 1
fi
echo "Copy Telegram env manually, then run: hermes gateway setup && hermes gateway install && hermes gateway start"
