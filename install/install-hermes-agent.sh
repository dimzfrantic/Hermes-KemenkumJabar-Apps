#!/usr/bin/env bash
set -euo pipefail
if command -v hermes >/dev/null 2>&1; then
  echo "Hermes already installed: $(command -v hermes)"
else
  curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash
fi
cat <<'EOF'
Hermes Agent installer selesai.
Langkah manual berikutnya:
1. Jalankan hermes setup
2. Siapkan ~/.hermes/.env
3. Review ~/.hermes/config.yaml
4. Copy SOUL.md, memory, dan skills bila dimigrasikan
5. Jalankan hermes doctor
6. Jalankan hermes tools list dan hermes memory status untuk verifikasi dasar
EOF
