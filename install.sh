#!/bin/bash
# Instala el Panel SentinelOne para el usuario actual (no requiere sudo).
#   ./install.sh              instala en ~/.local/share/s1-panel + menú + escritorio
#   ./install.sh --autostart  además arranca el ícono de bandeja al iniciar sesión
set -e
SRC=$(dirname "$(readlink -f "$0")")
DEST="${XDG_DATA_HOME:-$HOME/.local/share}/s1-panel"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DESKTOP_DIR=$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")

install -d "$DEST/icons" "$APPS"
install -m 755 "$SRC/s1panel.py" "$DEST/s1panel.py"
install -m 644 "$SRC"/icons/*.svg "$DEST/icons/"

entry() { # entry <archivo> <args extra>
  cat > "$1" <<DESKTOP
[Desktop Entry]
Type=Application
Version=1.0
Name=Panel SentinelOne
Comment=Estado y acciones del agente SentinelOne
Exec=/usr/bin/python3 $DEST/s1panel.py $2
Icon=$DEST/icons/s1-ok.svg
Terminal=false
Categories=System;Security;
StartupNotify=false
DESKTOP
  chmod +x "$1"
}

entry "$APPS/sentinelone-panel.desktop" ""
if [ -d "$DESKTOP_DIR" ]; then
  entry "$DESKTOP_DIR/sentinelone-panel.desktop" ""
  # XFCE: marcar el lanzador como confiable
  gio set -t string "$DESKTOP_DIR/sentinelone-panel.desktop" metadata::xfce-exe-checksum \
    "$(sha256sum "$DESKTOP_DIR/sentinelone-panel.desktop" | cut -d' ' -f1)" 2>/dev/null || true
fi
if [ "${1:-}" = "--autostart" ]; then
  install -d "$HOME/.config/autostart"
  entry "$HOME/.config/autostart/sentinelone-panel.desktop" "--tray"
fi
echo "Panel SentinelOne instalado en $DEST"
