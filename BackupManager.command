#!/bin/bash
# BackupManager.command
# Doppio clic su questo file per avviare l'app direttamente (senza costruire il bundle)
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Installa dipendenze se mancano
if ! python3 -c "import PIL" &>/dev/null 2>&1; then
    echo "📦 Prima installazione dipendenze…"
    pip3 install --user pillow pillow-heif opencv-python
fi

echo "🚀 Avvio BackupManager…"
cd "$SCRIPT_DIR"
python3 src/main.py
