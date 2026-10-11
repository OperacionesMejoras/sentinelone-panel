#!/bin/bash
# Desinstala el Panel SentinelOne del usuario actual. No toca el agente SentinelOne.
DEST="${XDG_DATA_HOME:-$HOME/.local/share}/s1-panel"
DESKTOP_DIR=$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")
rm -rf "$DEST"
rm -f "${XDG_DATA_HOME:-$HOME/.local/share}/applications/sentinelone-panel.desktop" \
      "$DESKTOP_DIR/sentinelone-panel.desktop" "$HOME/.config/autostart/sentinelone-panel.desktop"
echo "Panel SentinelOne desinstalado."
