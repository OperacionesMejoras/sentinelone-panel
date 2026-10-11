# Panel SentinelOne

Interfaz gráfica (GTK3) para el agente **SentinelOne en Linux**, que en esta plataforma no trae interfaz propia y se maneja solo con `sentinelctl`. Pensado para XFCE o GNOME sobre X11.

## Qué hace

**Ícono en la bandeja**, que se actualiza cada 30 s sin pedir contraseña:

| Ícono | Estado |
|---|---|
| 🟢 | Agente activo y conectado a la consola |
| 🟡 | Agente activo pero **sin conexión** con la consola |
| 🔴 | Agente **detenido** (además muestra una notificación) |
| ⚪ | Estado desconocido |

- Clic izquierdo: abre u oculta la ventana.
- Clic derecho: Abrir panel, Actualizar estado, Escanear todo el sistema, Salir.
- Cerrar la ventana la deja en la bandeja.

**La ventana** tiene tarjetas con el estado del servicio, el agente, la conexión con la consola, Anti Tamper, el escaneo, la versión, el UUID y la URL de la consola. Los botones son:

| Botón | Comando |
|---|---|
| Actualizar | `control status`, `management status`, `policy status`, `engines status`, `scan status`, `quarantine list all`, `detector version`, `providers status`, `mounts exclusion get`, `version` |
| Iniciar agente | `control start` |
| Escanear… | `scan start <ruta>` (todo el sistema, un disco o la carpeta que elijas) |
| Abortar escaneo | `scan abort` |
| Reporte | `report summary`, `report status` |
| Generar logs | `log generate ~/s1-logs-<fecha>` (para soporte) |
| Copiar todo | Copia todas las salidas al portapapeles |

Cada salida se muestra completa en su propia pestaña.

### Lo que no hace, a propósito

No incluye detener, deshabilitar o desinstalar el agente, ni cambiar el token, el UUID, FIPS o la configuración. Esas operaciones quedan para la consola de gestión o para `sentinelctl` a mano, y la mayoría están bloqueadas por Anti Tamper.

## Seguridad

- **No instala nada con permisos de root.** Todo queda en `~/.local/share/s1-panel`.
- Cada acción privilegiada corre con `pkexec` y pide la contraseña en ese momento. No se guardan credenciales y no hay reglas de polkit.
- El ícono de la bandeja solo usa `systemctl is-active sentinelone`, que no necesita privilegios.
- El código no contiene tokens, site keys ni URLs de consola. Todo eso se lee del agente en ejecución.

## Requisitos

- Agente SentinelOne para Linux instalado (`/opt/sentinelone/bin/sentinelctl`)
- Python 3 con PyGObject y GTK 3 (`python3-gi`, `gir1.2-gtk-3.0`)
- `pkexec` (polkit) y un agente de autenticación gráfico (viene con XFCE, GNOME, Cinnamon y MATE)
- Bandeja del sistema compatible con XEmbed (XFCE la trae; en GNOME hace falta una extensión de AppIndicator/KStatusNotifier)

## Instalación

```bash
git clone https://github.com/OperacionesMejoras/sentinelone-panel.git
cd sentinelone-panel
./install.sh              # menú de aplicaciones + lanzador en el escritorio
./install.sh --autostart  # además, ícono en la bandeja al iniciar sesión (sin pedir contraseña)
```

Para desinstalar: `./uninstall.sh`. No toca el agente SentinelOne.

## Uso desde la terminal

```bash
python3 ~/.local/share/s1-panel/s1panel.py          # abre la ventana y actualiza (pide contraseña)
python3 ~/.local/share/s1-panel/s1panel.py --tray   # solo el ícono de bandeja
```

Si el panel ya está abierto, volver a ejecutarlo trae la ventana al frente: es una sola instancia.

## Licencia

MIT
