#!/usr/bin/env python3
"""Panel SentinelOne: interfaz GTK3 para sentinelctl con ícono en la bandeja.

- El ícono de bandeja consulta `systemctl is-active sentinelone` cada 30 s (sin contraseña).
- Todo lo que necesita root se ejecuta con pkexec (pide contraseña en cada acción).
- Cerrar la ventana la oculta en la bandeja; "Salir" desde el menú del ícono cierra el panel.
- `--tray` arranca solo con el ícono, sin abrir la ventana ni pedir contraseña.
"""
import datetime
import os
import re
import shlex
import subprocess
import sys
import threading

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk, Pango  # noqa: E402

APP_ID = "ar.local.s1panel"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
ICONS = {k: os.path.join(APP_DIR, "icons", f"s1-{k}.svg") for k in ("ok", "warn", "bad", "unk")}
SENTINELCTL = "/opt/sentinelone/bin/sentinelctl"
SERVICE = "sentinelone"
TRAY_POLL_SECONDS = 30

# (clave, título de pestaña, argumentos de sentinelctl)
STATUS_SECTIONS = [
    ("control", "Agente", ["control", "status"]),
    ("management", "Consola", ["management", "status"]),
    ("policy", "Políticas", ["policy", "status"]),
    ("engines", "Motores", ["engines", "status"]),
    ("scan", "Escaneo", ["scan", "status"]),
    ("quarantine", "Cuarentena", ["quarantine", "list", "all"]),
    ("detector", "Detectores", ["detector", "version"]),
    ("providers", "Proveedores", ["providers", "status"]),
    ("mounts", "Exclusiones", ["mounts", "exclusion", "get"]),
    ("version", "Versión", ["version"]),
]
REPORT_SECTIONS = [
    ("report-summary", "Reporte resumen", ["report", "summary"]),
    ("report-status", "Reporte estado", ["report", "status"]),
]

KV_RE = re.compile(r"^(\S.*?)\s{2,}(\S.*)$")


def build_script(sections):
    lines = []
    for key, _title, args in sections:
        cmd = " ".join(shlex.quote(a) for a in [SENTINELCTL, *args])
        lines.append(f"echo '@@@SECTION {key}'; timeout 90 {cmd} </dev/null 2>&1; echo \"@@@RC $?\"")
    return "\n".join(lines)


def parse_sections(output):
    """Devuelve {clave: (texto, rc)} a partir de la salida marcada con @@@SECTION/@@@RC."""
    result, key, buf = {}, None, []
    for line in output.splitlines():
        if line.startswith("@@@SECTION "):
            key, buf = line.split(" ", 1)[1].strip(), []
        elif line.startswith("@@@RC ") and key:
            result[key] = ("\n".join(buf).strip(), line.split(" ", 1)[1].strip())
            key = None
        elif key:
            buf.append(line)
    return result


def parse_kv(text):
    kv = {}
    for line in text.splitlines():
        m = KV_RE.match(line.rstrip())
        if m:
            kv[m.group(1).strip()] = m.group(2).strip()
    return kv


def run_as_root(script):
    """Ejecuta el script con pkexec. Devuelve (ok, salida, mensaje_error)."""
    try:
        p = subprocess.run(["pkexec", "/bin/sh", "-c", script], capture_output=True, text=True, timeout=1800)
    except subprocess.TimeoutExpired:
        return False, "", "La operación tardó demasiado y se canceló."
    except FileNotFoundError:
        return False, "", "No se encontró pkexec."
    if p.returncode in (126, 127) and "@@@SECTION" not in p.stdout:
        return False, p.stdout, "Autenticación cancelada o rechazada."
    return True, p.stdout + p.stderr, ""


def service_active():
    try:
        p = subprocess.run(["systemctl", "is-active", SERVICE], capture_output=True, text=True, timeout=10)
        return p.stdout.strip()
    except Exception:
        return "unknown"


class PanelWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Panel SentinelOne")
        self.app = app
        self.set_default_size(820, 600)
        self.set_icon_from_file(ICONS["unk"])
        self.connect("delete-event", self.on_delete)

        header = Gtk.HeaderBar(show_close_button=True, title="Panel SentinelOne")
        self.set_titlebar(header)
        self.spinner = Gtk.Spinner()
        refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        refresh.set_tooltip_text("Actualizar estado (pide contraseña)")
        refresh.connect("clicked", lambda *_: self.app.refresh_status())
        header.pack_start(refresh)
        header.pack_start(self.spinner)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=12)
        self.add(root)

        # Tarjetas de estado
        grid = Gtk.Grid(column_spacing=24, row_spacing=6)
        root.pack_start(grid, False, False, 0)
        self.fields = {}
        labels = [
            ("service", "Servicio"),
            ("agent", "Agente"),
            ("conn", "Conexión con consola"),
            ("tamper", "Anti Tamper"),
            ("scan", "Escaneo"),
            ("version", "Versión"),
            ("uuid", "UUID"),
            ("url", "Consola"),
            ("updated", "Actualizado"),
        ]
        for i, (key, title) in enumerate(labels):
            t = Gtk.Label(label=title, xalign=0)
            t.get_style_context().add_class("dim-label")
            v = Gtk.Label(label="—", xalign=0, selectable=True)
            v.set_ellipsize(Pango.EllipsizeMode.END)
            grid.attach(t, (i % 3) * 2, i // 3, 1, 1)
            grid.attach(v, (i % 3) * 2 + 1, i // 3, 1, 1)
            self.fields[key] = v

        # Acciones
        actions = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=8, column_spacing=6)
        root.pack_start(actions, False, False, 0)
        self.buttons = []
        for label, icon, cb, tip in [
            ("Actualizar", "view-refresh-symbolic", self.app.refresh_status, "Consultar todo el estado del agente"),
            ("Iniciar agente", "media-playback-start-symbolic", self.app.agent_start, "sentinelctl control start"),
            ("Escanear…", "system-search-symbolic", self.ask_scan, "Lanzar un escaneo de disco"),
            ("Abortar escaneo", "process-stop-symbolic", self.app.scan_abort, "sentinelctl scan abort"),
            ("Reporte", "x-office-document-symbolic", self.app.report, "Reporte resumen y de estado"),
            ("Generar logs", "document-save-symbolic", self.app.logs, "Archivo de logs para soporte"),
            ("Copiar todo", "edit-copy-symbolic", self.copy_all, "Copiar todas las salidas al portapapeles"),
        ]:
            b = Gtk.Button(label=label, image=Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON), always_show_image=True)
            b.set_tooltip_text(tip)
            b.connect("clicked", lambda _b, f=cb: f())
            actions.add(b)
            if label != "Copiar todo":
                self.buttons.append(b)

        # Salidas crudas por sección
        self.notebook = Gtk.Notebook(scrollable=True)
        root.pack_start(self.notebook, True, True, 0)
        self.views = {}

        self.status = Gtk.Label(xalign=0, label="Tocá Actualizar para consultar el agente (pide contraseña).")
        self.status.set_ellipsize(Pango.EllipsizeMode.END)
        root.pack_start(self.status, False, False, 0)

    def on_delete(self, *_):
        self.hide()
        return True

    def set_busy(self, busy, msg=None):
        (self.spinner.start if busy else self.spinner.stop)()
        for b in self.buttons:
            b.set_sensitive(not busy)
        if msg:
            self.status.set_text(msg)

    def show_section(self, key, title, text, rc):
        if key not in self.views:
            tv = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.NONE, left_margin=8, top_margin=6)
            sw = Gtk.ScrolledWindow()
            sw.add(tv)
            self.notebook.append_page(sw, Gtk.Label(label=title))
            self.views[key] = tv
            sw.show_all()
        body = text or "(sin salida)"
        if rc not in ("0", None):
            body += f"\n\n[código de salida: {rc}]"
        self.views[key].get_buffer().set_text(body)

    def focus_section(self, key):
        tv = self.views.get(key)
        if tv:
            self.notebook.set_current_page(self.notebook.page_num(tv.get_parent()))

    def copy_all(self):
        parts = []
        for i in range(self.notebook.get_n_pages()):
            page = self.notebook.get_nth_page(i)
            title = self.notebook.get_tab_label_text(page)
            buf = page.get_child().get_buffer()
            parts.append(f"===== {title}\n{buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)}")
        Gtk.Clipboard.get_default(self.get_display()).set_text("\n\n".join(parts), -1)
        self.status.set_text("Copiado al portapapeles.")

    def ask_scan(self):
        dlg = Gtk.Dialog(title="Escanear con SentinelOne", transient_for=self, modal=True)
        dlg.add_buttons("Cancelar", Gtk.ResponseType.CANCEL, "Escanear", Gtk.ResponseType.OK)
        box = dlg.get_content_area()
        box.set_spacing(8)
        box.set_border_width(12)
        box.add(Gtk.Label(label="Carpeta desde donde escanear:", xalign=0))
        chooser = Gtk.FileChooserButton(title="Elegir carpeta", action=Gtk.FileChooserAction.SELECT_FOLDER)
        chooser.set_filename("/")
        box.add(chooser)
        quick = Gtk.Box(spacing=6)
        for label, path in [("Todo el sistema (/)", "/"), ("Disco datos", "/mnt/datos"), ("Mi carpeta", os.path.expanduser("~"))]:
            if os.path.isdir(path):
                b = Gtk.Button(label=label)
                b.connect("clicked", lambda _b, p=path: chooser.set_filename(p))
                quick.add(b)
        box.add(quick)
        dlg.show_all()
        resp = dlg.run()
        path = chooser.get_filename() or "/"
        dlg.destroy()
        if resp == Gtk.ResponseType.OK:
            self.app.scan_start(path)


class PanelApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.win = None
        self.tray = None
        self.busy = False
        self.connectivity = None  # "On" / "Off" / None (sin verificar)
        self.last_service = None

    # --- ciclo de vida -------------------------------------------------
    def do_startup(self):
        Gtk.Application.do_startup(self)
        self.hold()  # seguir vivo con la ventana oculta
        self.win = PanelWindow(self)
        self.setup_tray()
        self.poll_service()
        GLib.timeout_add_seconds(TRAY_POLL_SECONDS, self.poll_service)

    def do_command_line(self, cmdline):
        args = cmdline.get_arguments()[1:]
        if "--tray" not in args:
            first_show = not self.win.get_visible() and self.connectivity is None
            self.present_window()
            if first_show:
                self.refresh_status()
        return 0

    def present_window(self):
        self.win.show_all()
        self.win.present()

    def quit_app(self):
        self.release()
        self.quit()

    # --- bandeja ---------------------------------------------------------
    def setup_tray(self):
        self.tray = Gtk.StatusIcon()
        self.tray.set_from_file(ICONS["unk"])
        self.tray.set_title("SentinelOne")
        self.tray.set_tooltip_text("SentinelOne: consultando…")
        self.tray.connect("activate", lambda *_: self.toggle_window())
        self.tray.connect("popup-menu", self.on_tray_menu)

    def toggle_window(self):
        if self.win.get_visible() and self.win.is_active():
            self.win.hide()
        else:
            self.present_window()

    def on_tray_menu(self, icon, button, time):
        menu = Gtk.Menu()
        for label, cb in [
            ("Abrir panel", self.present_window),
            ("Actualizar estado", lambda: (self.present_window(), self.refresh_status())),
            ("Escanear todo el sistema", lambda: self.scan_start("/")),
            (None, None),
            ("Salir", self.quit_app),
        ]:
            if label is None:
                menu.append(Gtk.SeparatorMenuItem())
                continue
            item = Gtk.MenuItem(label=label)
            item.connect("activate", lambda _i, f=cb: f())
            menu.append(item)
        menu.show_all()
        menu.popup(None, None, Gtk.StatusIcon.position_menu, icon, button, time)

    def poll_service(self):
        def work():
            state = service_active()
            GLib.idle_add(self.update_tray, state)
        threading.Thread(target=work, daemon=True).start()
        return True

    def update_tray(self, state):
        if state == "active":
            if self.connectivity == "Off":
                icon, tip = "warn", "SentinelOne activo, SIN conexión con la consola"
            elif self.connectivity == "On":
                icon, tip = "ok", "SentinelOne activo y conectado a la consola"
            else:
                icon, tip = "ok", "SentinelOne activo (conexión sin verificar: abrí el panel y actualizá)"
        elif state in ("inactive", "failed"):
            icon, tip = "bad", f"SentinelOne DETENIDO (servicio {state})"
        else:
            icon, tip = "unk", f"SentinelOne: estado desconocido ({state})"
        self.tray.set_from_file(ICONS[icon])
        self.tray.set_tooltip_text(tip)
        self.win.set_icon_from_file(ICONS[icon])
        self.win.fields["service"].set_text(state)
        if self.last_service == "active" and state != "active":
            subprocess.Popen(["notify-send", "-u", "critical", "-i", ICONS["bad"], "SentinelOne", "El agente se detuvo."])
        self.last_service = state
        return False

    # --- ejecución con root ----------------------------------------------
    def run_root(self, sections, busy_msg, on_done):
        if self.busy:
            return
        self.busy = True
        self.win.set_busy(True, busy_msg)

        def work():
            ok, out, err = run_as_root(build_script(sections))
            GLib.idle_add(finish, ok, out, err)

        def finish(ok, out, err):
            self.busy = False
            self.win.set_busy(False)
            if not ok:
                self.win.status.set_text(err)
                return False
            parsed = parse_sections(out)
            titles = {k: t for k, t, _ in sections}
            for key, (text, rc) in parsed.items():
                self.win.show_section(key, titles.get(key, key), text, rc)
            on_done(parsed)
            self.poll_service()
            return False

        threading.Thread(target=work, daemon=True).start()

    def refresh_status(self):
        self.run_root(STATUS_SECTIONS, "Consultando el agente…", self.apply_status)

    def apply_status(self, parsed):
        f = self.win.fields
        control = parsed.get("control", ("", ""))[0]
        ckv = parse_kv(control)
        if "must be running" in control:
            f["agent"].set_text("Detenido")
        else:
            f["agent"].set_text(ckv.get("Agent state", control.splitlines()[0] if control else "—"))
        mkv = parse_kv(parsed.get("management", ("", ""))[0])
        self.connectivity = mkv.get("Connectivity")
        f["conn"].set_text(self.connectivity or "—")
        f["tamper"].set_text(mkv.get("Anti Tamper", "—"))
        f["uuid"].set_text(mkv.get("UUID", "—"))
        f["url"].set_text(mkv.get("URL", "—"))
        f["url"].set_tooltip_text(mkv.get("URL", ""))
        version = parsed.get("version", ("", ""))[0]
        f["version"].set_text(next((l.strip() for l in version.splitlines() if l.strip()), "—"))
        scan = parsed.get("scan", ("", ""))[0]
        f["scan"].set_text(next((l.strip() for l in scan.splitlines() if l.strip()), "—"))
        f["updated"].set_text(datetime.datetime.now().strftime("%H:%M:%S"))
        self.win.status.set_text("Estado actualizado.")

    def agent_start(self):
        self.run_root([("agent-start", "Inicio", ["control", "start"])], "Iniciando agente…",
                      lambda p: (self.win.focus_section("agent-start"), self.win.status.set_text("Listo. Tocá Actualizar para ver el estado.")))

    def scan_start(self, path):
        if not os.path.isdir(path):
            self.win.status.set_text(f"Ruta inválida: {path}")
            return
        self.present_window()
        self.run_root([("scan-start", "Inicio escaneo", ["scan", "start", path]),
                       ("scan", "Escaneo", ["scan", "status"])],
                      f"Iniciando escaneo de {path}…",
                      lambda p: (self.win.focus_section("scan"), self.win.status.set_text(f"Escaneo de {path} solicitado. Usá Actualizar para ver el avance.")))

    def scan_abort(self):
        self.run_root([("scan-abort", "Abortar escaneo", ["scan", "abort"]), ("scan", "Escaneo", ["scan", "status"])],
                      "Abortando escaneo…", lambda p: self.win.focus_section("scan"))

    def report(self):
        self.run_root(REPORT_SECTIONS, "Generando reporte…", lambda p: self.win.focus_section("report-summary"))

    def logs(self):
        dest = os.path.join(os.path.expanduser("~"), "s1-logs-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
        uid = os.getuid()
        if self.busy:
            return
        self.busy = True
        self.win.set_busy(True, "Generando archivo de logs (puede tardar)…")
        script = (f"mkdir -p {shlex.quote(dest)} && echo '@@@SECTION logs' && "
                  f"timeout 600 {SENTINELCTL} log generate {shlex.quote(dest)} </dev/null 2>&1; echo \"@@@RC $?\"; "
                  f"chown -R {uid}: {shlex.quote(dest)}")

        def work():
            ok, out, err = run_as_root(script)
            GLib.idle_add(finish, ok, out, err)

        def finish(ok, out, err):
            self.busy = False
            self.win.set_busy(False)
            if not ok:
                self.win.status.set_text(err)
                return False
            text, rc = parse_sections(out).get("logs", (out, "?"))
            self.win.show_section("logs", "Logs", f"{text}\n\nDestino: {dest}", rc)
            self.win.focus_section("logs")
            self.win.status.set_text(f"Logs guardados en {dest}")
            return False

        threading.Thread(target=work, daemon=True).start()


if __name__ == "__main__":
    sys.exit(PanelApp().run(sys.argv))
