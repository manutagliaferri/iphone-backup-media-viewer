#!/bin/bash
# =============================================================================
# install.sh — Installa le dipendenze Python per BackupManager
# =============================================================================
# Uso:  bash install.sh
# =============================================================================

set -e
BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo ""
echo -e "${BOLD}╔══════════════════════════════════════╗${NC}"
echo -e "${BOLD}║       BackupManager — Installazione   ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════╝${NC}"
echo ""

# ── Python ────────────────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}✗ Python3 non trovato.${NC}"
    echo "  Installa Python3 da https://www.python.org/downloads/"
    echo "  oppure via Homebrew:  brew install python3"
    exit 1
fi

PY=$(python3 --version 2>&1)
echo -e "${GREEN}✓ ${PY} trovato${NC}"

# ── pip ───────────────────────────────────────────────────────────────────────
if ! python3 -m pip --version &>/dev/null; then
    echo -e "${YELLOW}⚠ pip non trovato, installazione in corso…${NC}"
    python3 -m ensurepip --upgrade
fi

# ── Pillow ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}📦 Installazione pacchetti Python…${NC}"
echo ""

install_pkg() {
    local pkg="$1"
    local display="$2"
    echo -n "  Installazione ${display}…  "
    if pip3 install --user "${pkg}" --quiet 2>&1; then
        echo -e "${GREEN}✓${NC}"
    else
        echo -e "${RED}✗ (vedi messaggio sopra)${NC}"
    fi
}

install_pkg "Pillow>=10.0.0"        "Pillow (gestione immagini)"
install_pkg "pillow-heif>=0.13.0"   "pillow-heif (supporto HEIC)"
install_pkg "opencv-python>=4.8.0"  "opencv-python (video player)"

# ── ffmpeg (opzionale, via Homebrew) ─────────────────────────────────────────
echo ""
if command -v ffmpeg &>/dev/null; then
    echo -e "${GREEN}✓ ffmpeg trovato (fallback video)${NC}"
else
    echo -e "${YELLOW}ℹ ffmpeg non trovato (opzionale).${NC}"
    echo "  Per installarlo:  brew install ffmpeg"
fi

# ── Flag installazione completata ─────────────────────────────────────────────
FLAGDIR="$HOME/.BackupManager"
mkdir -p "$FLAGDIR"
touch "$FLAGDIR/.deps_ok"

echo ""
echo -e "${GREEN}${BOLD}✅  Installazione completata!${NC}"
echo ""
echo "Per avviare BackupManager:"
echo -e "  ${BOLD}python3 src/main.py${NC}"
echo ""
echo "Per creare il bundle .app macOS:"
echo -e "  ${BOLD}bash build_app.sh${NC}"
echo ""
