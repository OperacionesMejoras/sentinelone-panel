#!/bin/bash
# Genera dist/sentinelone-panel_<version>_all.deb (no requiere sudo).
#   packaging/build-deb.sh [version]
set -e
ROOT=$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)
VERSION=${1:-$(cat "$ROOT/VERSION")}
PKG=sentinelone-panel
BUILD=$(mktemp -d)
trap 'rm -rf "$BUILD"' EXIT
P="$BUILD/${PKG}_${VERSION}_all"

install -d "$P/DEBIAN" "$P/usr/share/s1-panel/icons" "$P/usr/bin" \
           "$P/usr/share/applications" "$P/usr/share/icons/hicolor/scalable/apps" \
           "$P/usr/share/doc/$PKG"
install -m 755 "$ROOT/s1panel.py" "$P/usr/share/s1-panel/s1panel.py"
install -m 644 "$ROOT"/icons/*.svg "$P/usr/share/s1-panel/icons/"
install -m 644 "$ROOT/icons/s1-ok.svg" "$P/usr/share/icons/hicolor/scalable/apps/sentinelone-panel.svg"
install -m 644 "$ROOT/README.md" "$P/usr/share/doc/$PKG/README.md"
install -m 644 "$ROOT/LICENSE" "$P/usr/share/doc/$PKG/copyright"

cat > "$P/usr/bin/sentinelone-panel" <<'SH'
#!/bin/sh
exec /usr/bin/python3 /usr/share/s1-panel/s1panel.py "$@"
SH
chmod 755 "$P/usr/bin/sentinelone-panel"

cat > "$P/usr/share/applications/sentinelone-panel.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Version=1.0
Name=Panel SentinelOne
Comment=Estado y acciones del agente SentinelOne
Exec=sentinelone-panel
Icon=sentinelone-panel
Terminal=false
Categories=System;Security;
StartupNotify=false
DESKTOP
chmod 644 "$P/usr/share/applications/sentinelone-panel.desktop"

cat > "$P/DEBIAN/control" <<CONTROL
Package: $PKG
Version: $VERSION
Section: admin
Priority: optional
Architecture: all
Depends: python3, python3-gi, gir1.2-gtk-3.0, pkexec | policykit-1, libnotify-bin
Recommends: sentinelagent
Maintainer: OperacionesMejoras <leandroreale@keepsmiling.com.ar>
Homepage: https://github.com/OperacionesMejoras/sentinelone-panel
Installed-Size: $(du -sk "$P/usr" | cut -f1)
Description: Panel GTK3 con ícono de bandeja para el agente SentinelOne en Linux
 Interfaz gráfica para sentinelctl: estado del agente, conexión con la
 consola, políticas, motores, escaneos y cuarentena, más acciones vía
 pkexec (iniciar agente, escanear, abortar, reporte, generar logs).
 No instala componentes con privilegios de root.
CONTROL

cat > "$P/DEBIAN/postinst" <<'SH'
#!/bin/sh
set -e
command -v update-desktop-database >/dev/null && update-desktop-database -q /usr/share/applications || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t /usr/share/icons/hicolor || true
exit 0
SH
cp "$P/DEBIAN/postinst" "$P/DEBIAN/postrm"
chmod 755 "$P/DEBIAN/postinst" "$P/DEBIAN/postrm"

mkdir -p "$ROOT/dist"
dpkg-deb --root-owner-group --build "$P" "$ROOT/dist/${PKG}_${VERSION}_all.deb"
