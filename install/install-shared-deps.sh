#!/usr/bin/env bash
set -euo pipefail

echo "==> Update package index"
sudo apt update

echo "==> Install shared system dependencies"
sudo apt install -y   git curl wget unzip ca-certificates software-properties-common   build-essential pkg-config python3 python3-venv python3-pip   nginx postgresql postgresql-contrib libreoffice libreoffice-impress fontconfig

echo "==> Version checks"
python3 --version || true
pip3 --version || true
psql --version || true
nginx -v || true
soffice --version || true

echo "==> Shared dependency installation selesai"
