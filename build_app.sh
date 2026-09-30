#!/bin/bash
# =============================================================================
# build_app.sh — Crea BackupManager.app per macOS
# =============================================================================
# Uso:  bash build_app.sh
# Produce: BackupManager.app nella stessa cartella
# =============================================================================

set -e

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP="BackupManager"
APP_BUNDLE="$SCRIPT_DIR/${APP}.app"
CONTENTS="$APP_BUNDLE/Contents"
MACOS_DIR="$CONTENTS/MacOS"
RES_DIR="$CONTENTS/Resources"

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║    BackupManager — Creazione .app bundle  ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════╝${NC}"
echo ""

# ── Pulizia build precedente ──────────────────────────────────────────────────
echo -n "🧹  Pulizia build precedente… "
rm -rf "$APP_BUNDLE"
echo -e "${GREEN}✓${NC}"

# ── Struttura directory ───────────────────────────────────────────────────────
echo -n "📁  Creazione struttura .app… "
mkdir -p "$MACOS_DIR" "$RES_DIR"
echo -e "${GREEN}✓${NC}"

# ── Copia sorgenti ────────────────────────────────────────────────────────────
echo -n "📋  Copia file sorgente… "
cp -r "$SCRIPT_DIR/src"          "$RES_DIR/src"
cp -r "$SCRIPT_DIR/assets"       "$RES_DIR/assets"
cp    "$SCRIPT_DIR/requirements.txt" "$RES_DIR/"
echo -e "${GREEN}✓${NC}"

# ── Info.plist ────────────────────────────────────────────────────────────────
echo -n "📄  Scrittura Info.plist… "
cat > "$CONTENTS/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>BackupManager</string>
    <key>CFBundleIdentifier</key>
    <string>com.backupmanager.app</string>
    <key>CFBundleName</key>
    <string>BackupManager</string>
    <key>CFBundleDisplayName</key>
    <string>BackupManager</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundleVersion</key>
    <string>1.0.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleSignature</key>
    <string>????</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSPrincipalClass</key>
    <string>NSApplication</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.14</string>
    <key>NSRemovableVolumesUsageDescription</key>
    <string>BackupManager richiede accesso ai volumi rimovibili per leggere i backup iPhone su hard disk esterni.</string>
    <key>NSDesktopFolderUsageDescription</key>
    <string>BackupManager può salvare le foto esportate sulla scrivania.</string>
    <key>NSDocumentsFolderUsageDescription</key>
    <string>BackupManager può salvare le foto esportate nella cartella Documenti.</string>
    <key>NSDownloadsFolderUsageDescription</key>
    <string>BackupManager può salvare le foto esportate nella cartella Download.</string>
</dict>
</plist>
PLIST
echo -e "${GREEN}✓${NC}"

# ── PkgInfo ───────────────────────────────────────────────────────────────────
printf 'APPL????' > "$CONTENTS/PkgInfo"

# ── Icona .icns ───────────────────────────────────────────────────────────────
ICON_PNG="$SCRIPT_DIR/assets/icon.png"
if [ -f "$ICON_PNG" ]; then
    echo -n "🎨  Creazione AppIcon.icns… "
    ICONSET="$SCRIPT_DIR/assets/AppIcon.iconset"
    TRUE_PNG="$SCRIPT_DIR/assets/icon_build.png"
    mkdir -p "$ICONSET"

    # Converti sempre in PNG vero (gestisce anche JPEG con estensione .png)
    python3 -c "
from PIL import Image
img = Image.open('$ICON_PNG').convert('RGBA')
img.save('$TRUE_PNG', 'PNG')
" 2>/dev/null || cp "$ICON_PNG" "$TRUE_PNG"

    SRC="$TRUE_PNG"
    for SIZE in 16 32 64 128 256 512 1024; do
        sips -z $SIZE $SIZE "$SRC" \
             --out "$ICONSET/icon_${SIZE}x${SIZE}.png" &>/dev/null
    done
    # @2x alias
    cp "$ICONSET/icon_32x32.png"     "$ICONSET/icon_16x16@2x.png"
    cp "$ICONSET/icon_64x64.png"     "$ICONSET/icon_32x32@2x.png"
    cp "$ICONSET/icon_256x256.png"   "$ICONSET/icon_128x128@2x.png"
    cp "$ICONSET/icon_512x512.png"   "$ICONSET/icon_256x256@2x.png"
    cp "$ICONSET/icon_1024x1024.png" "$ICONSET/icon_512x512@2x.png"

    iconutil -c icns "$ICONSET" -o "$RES_DIR/AppIcon.icns" 2>/dev/null \
        && echo -e "${GREEN}✓${NC}" \
        || echo -e "${YELLOW}⚠ iconutil fallito (icona non critica)${NC}"

    rm -rf "$ICONSET" "$TRUE_PNG"
else
    echo -e "${YELLOW}⚠ assets/icon.png non trovata — l'app userà l'icona default${NC}"
fi

# ── Launcher eseguibile ───────────────────────────────────────────────────────
echo -n "🚀  Scrittura launcher… "
cat > "$MACOS_DIR/$APP" << 'LAUNCHER'
#!/bin/bash
# BackupManager launcher — avviato da macOS quando si apre l'app
#
# Cerca Python3, installa dipendenze se necessario, avvia main.py

SCRIPT="$(cd "$(dirname "$0")" && pwd)"
RESOURCES="$(dirname "$SCRIPT")/Resources"
FLAGFILE="$HOME/.BackupManager/.deps_ok"

# ── Verifica Python3 ──────────────────────────────────────────────────────────
PY3="$(command -v python3 2>/dev/null)"
if [ -z "$PY3" ]; then
    osascript <<EOF
        display alert "Python3 non trovato" ¬
            message "BackupManager richiede Python3.\n\nInstalla Python3 da:\nhttps://www.python.org/downloads/\n\noppure via Homebrew:\nbrew install python3" ¬
            buttons {"OK"} ¬
            default button "OK"
EOF
    exit 1
fi

# ── Dipendenze (solo la prima volta o se manca il flag) ───────────────────────
if [ ! -f "$FLAGFILE" ]; then
    mkdir -p "$HOME/.BackupManager"
    osascript -e 'display notification "Installazione dipendenze in corso (solo la prima volta)…" with title "BackupManager"' &>/dev/null || true

    "$PY3" -m pip install --user \
        "Pillow>=10.0.0" "pillow-heif>=0.13.0" "opencv-python>=4.8.0" \
        --quiet 2>&1

    touch "$FLAGFILE"
fi

# ── Avvio applicazione ────────────────────────────────────────────────────────
export PYTHONPATH="$RESOURCES/src:$PYTHONPATH"
cd "$RESOURCES"
exec "$PY3" "$RESOURCES/src/main.py"
LAUNCHER

chmod +x "$MACOS_DIR/$APP"
echo -e "${GREEN}✓${NC}"

# ── Risultato ─────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}✅  BackupManager.app creato con successo!${NC}"
echo ""
echo -e "   📍  Posizione: ${BOLD}$APP_BUNDLE${NC}"
echo ""
echo "   Per usarlo:"
echo "   • Doppio clic su BackupManager.app"
echo "   • Oppure trascinalo nella cartella Applicazioni"
echo ""
echo -e "${YELLOW}   Nota: al primo avvio macOS potrebbe chiedere conferma.${NC}"
echo -e "${YELLOW}   Vai su: Impostazioni → Privacy → Apri comunque${NC}"
echo ""

# ── Apri Finder sulla cartella ────────────────────────────────────────────────
open "$SCRIPT_DIR"
