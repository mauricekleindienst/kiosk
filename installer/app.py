"""Kiosk einrichten: a step-by-step window for the Raspberry Pi desktop that checks the system, sets
up GitHub access for nightly updates and runs scripts/install.sh (or uninstall.sh), with progress.
Start it with a double click on "Kiosk einrichten" or: python3 installer/app.py"""

import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402

TOKENS = Path(__file__).resolve().parents[1] / "web" / "shared" / "styles" / "tokens.css"
STEPS = ["Willkommen", "Prüfung", "Optionen", "Updates", "Installation", "Fertig"]
WINDOW = (780, 600)
PAD = 24


def palette():
    """The light colors of the kiosk's design tokens, so the installer looks like the product."""
    text = TOKENS.read_text(encoding="utf-8")
    light = text[: text.index("@media")]
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})\b", light))


class SetupApp:
    def __init__(self, root, backend=core):
        self.root = root
        self.core = backend
        self.colors = palette()
        self.step = 0
        self.mode = tk.StringVar(value="install")
        self.admin = tk.BooleanVar(value=True)
        self.cec = tk.BooleanVar(value=False)
        self.updates = tk.BooleanVar(value=True)
        self.repository = tk.StringVar(value=backend.REPOSITORY)
        self.branch = tk.StringVar(value=backend.current_branch())
        self.password = tk.StringVar()
        self.access = None
        self.public_key = None
        self.messages = queue.Queue()
        self.running = False
        self.succeeded = False
        self._style()
        root.title("Kiosk einrichten")
        root.geometry(f"{WINDOW[0]}x{WINDOW[1]}")
        root.minsize(640, 520)
        root.configure(background=self.colors["bg-page"])
        self.header = ttk.Frame(root, style="Surface.TFrame", padding=(PAD, 16))
        self.header.pack(fill="x")
        ttk.Label(self.header, text="Kiosk einrichten", style="Title.TLabel").pack(side="left")
        self.progress_label = ttk.Label(self.header, style="Muted.Surface.TLabel")
        self.progress_label.pack(side="right")
        self.body = ttk.Frame(root, style="Page.TFrame", padding=PAD)
        self.body.pack(fill="both", expand=True)
        footer = ttk.Frame(root, style="Surface.TFrame", padding=(PAD, 12))
        footer.pack(fill="x", side="bottom")
        self.back = ttk.Button(footer, text="Zurück", command=self.previous)
        self.back.pack(side="left")
        self.next = ttk.Button(footer, text="Weiter", style="Primary.TButton", command=self.forward)
        self.next.pack(side="right")
        root.bind("<Escape>", lambda _event: self.close())
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.show()

    def _style(self):
        c = self.colors
        style = ttk.Style(self.root)
        style.theme_use("clam")
        base = ("TkDefaultFont", 11)
        style.configure(".", background=c["bg-page"], foreground=c["text"], font=base, focuscolor=c["focus-ring"])
        style.configure("Page.TFrame", background=c["bg-page"])
        style.configure("Surface.TFrame", background=c["surface"])
        style.configure("Card.TFrame", background=c["surface"], relief="solid", borderwidth=1, bordercolor=c["border"])
        style.configure("TLabel", background=c["bg-page"], foreground=c["text"])
        style.configure("Title.TLabel", background=c["surface"], font=("TkDefaultFont", 15, "bold"))
        style.configure("Heading.TLabel", font=("TkDefaultFont", 14, "bold"))
        style.configure("Muted.TLabel", foreground=c["text-muted"])
        style.configure("Muted.Surface.TLabel", background=c["surface"], foreground=c["text-muted"])
        for state in ("ok", "warn", "missing"):
            color = {"ok": c["success"], "warn": c["warning"], "missing": c["danger"]}[state]
            style.configure(f"{state}.TLabel", foreground=color, font=("TkDefaultFont", 11, "bold"))
        style.configure("TButton", padding=(16, 8), background=c["surface"], bordercolor=c["input-border"], relief="solid")
        style.map("TButton", background=[("active", c["bg-hover"]), ("disabled", c["bg-page"])])
        style.configure("Primary.TButton", background=c["button-bg"], foreground=c["button-text"], bordercolor=c["button-bg"])
        style.map("Primary.TButton", background=[("active", c["text-muted"]), ("disabled", c["text-subtle"])])
        style.configure("TCheckbutton", background=c["bg-page"])
        style.configure("TRadiobutton", background=c["bg-page"])
        style.configure("TEntry", fieldbackground=c["surface"], bordercolor=c["input-border"], padding=6)

    # Navigation

    def clear(self):
        for child in self.body.winfo_children():
            child.destroy()

    def show(self):
        self.clear()
        self.progress_label.configure(text=f"Schritt {self.step + 1} von {len(STEPS)}: {STEPS[self.step]}")
        self.back.configure(state="normal" if 0 < self.step < 4 else "disabled")
        self.next.configure(text="Weiter", state="normal")
        [self.page_welcome, self.page_checks, self.page_options, self.page_updates, self.page_install, self.page_done][self.step]()

    def previous(self):
        if self.step > 0 and not self.running:
            self.step -= 1
            self.show()

    def forward(self):
        if self.running:
            return
        if self.step == 0 and self.mode.get() == "remove":
            self.step = 4
        elif self.step == 3 and self.updates.get() and not self.access:
            self.note.configure(text="Bitte erst „Zugang prüfen“ wählen, oder automatische Updates ausschalten.", style="warn.TLabel")
            return
        elif self.step == 4 and not self.succeeded:
            self.start_work()
            return
        elif self.step == 5:
            self.close()
            return
        else:
            self.step += 1
        self.show()

    def close(self):
        if not self.running:
            self.root.destroy()

    def text(self, value, style="TLabel", **pack):
        label = ttk.Label(self.body, text=value, style=style, wraplength=WINDOW[0] - 2 * PAD - 20, justify="left")
        label.pack(anchor="w", **({"pady": (0, 10)} | pack))
        return label

    # Pages

    def page_welcome(self):
        self.text("Willkommen", "Heading.TLabel")
        self.text("Dieses Fenster richtet den Raspberry Pi als Büro-Bildschirm ein: Datenserver, Vollbild beim "
                  "Start, Nachtmodus und automatische Updates. Danach stellst du alles Weitere in der Verwaltung "
                  "im Browser ein.")
        if self.core.installed():
            self.text("Der Kiosk ist auf diesem Gerät schon eingerichtet.", "Muted.TLabel")
            ttk.Radiobutton(self.body, text="Einrichtung wiederholen oder reparieren", variable=self.mode, value="install").pack(anchor="w", pady=4)
            ttk.Radiobutton(self.body, text="Kiosk von diesem Gerät entfernen", variable=self.mode, value="remove").pack(anchor="w", pady=4)
        else:
            self.mode.set("install")
        self.next.focus_set()

    def page_checks(self):
        self.text("Prüfung", "Heading.TLabel")
        grid = ttk.Frame(self.body, style="Page.TFrame")
        grid.pack(fill="x", pady=(0, 12))
        blocking = False
        for row, check in enumerate(self.core.checks()):
            ttk.Label(grid, text=check.label).grid(row=row, column=0, sticky="w", padx=(0, 16), pady=4)
            ttk.Label(grid, text={"ok": "OK", "warn": "Hinweis", "missing": "Fehlt"}[check.state], style=f"{check.state}.TLabel").grid(row=row, column=1, sticky="w", padx=(0, 16))
            ttk.Label(grid, text=check.detail, style="Muted.TLabel", wraplength=420).grid(row=row, column=2, sticky="w")
            blocking |= check.state == "missing" and check.label == "Python"
        if blocking:
            self.text("Mit dieser Python-Version kann der Kiosk nicht laufen. Bitte Raspberry Pi OS Bookworm oder neuer verwenden.", "missing.TLabel")
            self.next.configure(state="disabled")

    def page_options(self):
        self.text("Optionen", "Heading.TLabel")
        ttk.Checkbutton(self.body, text="Verwaltung im Firmennetz erreichbar machen (Port 8081)", variable=self.admin).pack(anchor="w", pady=4)
        self.text("Über die Verwaltung stellst du Kacheln, Logo, Nachtmodus und mehr ein. Sie ist durch ein Passwort geschützt.", "Muted.TLabel", padx=(28, 0))
        ttk.Checkbutton(self.body, text="Fernseher über HDMI-CEC ein- und ausschalten (installiert v4l-utils)", variable=self.cec).pack(anchor="w", pady=4)
        self.text("Nur für Fernseher. Monitore schaltet der Nachtmodus auch ohne CEC ab.", "Muted.TLabel", padx=(28, 0))

    def page_updates(self):
        self.text("Automatische Updates", "Heading.TLabel")
        ttk.Checkbutton(self.body, text="Nachts automatisch die neueste Version aus GitHub holen", variable=self.updates).pack(anchor="w", pady=(0, 8))
        form = ttk.Frame(self.body, style="Page.TFrame")
        form.pack(fill="x", pady=(0, 8))
        ttk.Label(form, text="Repository").grid(row=0, column=0, sticky="w", padx=(0, 12), pady=4)
        ttk.Entry(form, textvariable=self.repository, width=40).grid(row=0, column=1, sticky="we")
        ttk.Label(form, text="Branch").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=4)
        ttk.Entry(form, textvariable=self.branch, width=40).grid(row=1, column=1, sticky="we")
        self.text("Ist das Repository privat, braucht der Pi einen Lese-Schlüssel (Deploy Key). Erzeuge ihn hier und trage ihn "
                  "auf GitHub ein: Repository, Settings, Deploy keys, Add deploy key; „Allow write access“ bleibt aus.", "Muted.TLabel")
        actions = ttk.Frame(self.body, style="Page.TFrame")
        actions.pack(anchor="w", pady=(0, 8))
        ttk.Button(actions, text="Schlüssel erzeugen", command=self.make_key).pack(side="left", padx=(0, 8))
        self.copy = ttk.Button(actions, text="Schlüssel kopieren", command=self.copy_key, state="disabled")
        self.copy.pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Zugang prüfen", command=self.check_access).pack(side="left")
        self.key_box = tk.Text(self.body, height=3, wrap="char", relief="solid", borderwidth=1,
                               background=self.colors["surface"], foreground=self.colors["text"], font=("TkFixedFont", 10))
        self.key_box.pack(fill="x", pady=(0, 8))
        self.key_box.insert("1.0", self.public_key or "")
        self.key_box.configure(state="disabled")
        if self.public_key:
            self.copy.configure(state="normal")
        self.note = self.text("Zugang geprüft." if self.access else "", "ok.TLabel" if self.access else "Muted.TLabel")

    def page_install(self):
        removing = self.mode.get() == "remove"
        self.text("Kiosk entfernen" if removing else "Installation", "Heading.TLabel")
        if self.core.needs_sudo_password():
            row = ttk.Frame(self.body, style="Page.TFrame")
            row.pack(fill="x", pady=(0, 10))
            ttk.Label(row, text="Passwort für Administratorrechte (sudo)").pack(anchor="w")
            entry = ttk.Entry(row, textvariable=self.password, show="•", width=32)
            entry.pack(anchor="w", pady=(4, 0))
            entry.focus_set()
        self.bar = ttk.Progressbar(self.body, mode="indeterminate")
        self.bar.pack(fill="x", pady=(0, 10))
        self.log = tk.Text(self.body, height=14, wrap="word", relief="solid", borderwidth=1,
                           background=self.colors["surface"], foreground=self.colors["text"], font=("TkFixedFont", 10))
        self.log.pack(fill="both", expand=True)
        self.log.configure(state="disabled")
        self.next.configure(text="Entfernen" if removing else "Installieren")

    def page_done(self):
        if self.mode.get() == "remove":
            self.text("Entfernt", "Heading.TLabel")
            self.text("Der Kiosk startet nicht mehr automatisch. Einstellungen und Bilder bleiben erhalten.")
        else:
            self.text("Fertig", "Heading.TLabel")
            self.text("Nach dem Neustart öffnet sich der Bildschirm im Vollbild.")
            if self.admin.get():
                self.text("Die Verwaltung erreichst du von jedem Gerät im Firmennetz unter:")
                for url in self.core.admin_urls():
                    self.text(url, "Heading.TLabel", padx=(16, 0))
                self.text("Beim ersten Öffnen fragt sie nach dem Code, den der Bildschirm unten zeigt.", "Muted.TLabel")
            ttk.Button(self.body, text="Jetzt neu starten", style="Primary.TButton",
                       command=lambda: subprocess.Popen(["sudo", "-A" if self.password.get() else "-n", "reboot"],
                                                        env=self.reboot_env())).pack(anchor="w", pady=(12, 0))
        self.back.configure(state="disabled")
        self.next.configure(text="Schließen")

    # Actions

    def make_key(self):
        try:
            self.public_key = self.core.ensure_key()
        except (OSError, RuntimeError) as err:
            self.note.configure(text=str(err), style="missing.TLabel")
            return
        self.key_box.configure(state="normal")
        self.key_box.delete("1.0", "end")
        self.key_box.insert("1.0", self.public_key)
        self.key_box.configure(state="disabled")
        self.copy.configure(state="normal")
        self.note.configure(text="Schlüssel erzeugt. Kopieren, auf GitHub eintragen, dann „Zugang prüfen“.", style="Muted.TLabel")

    def copy_key(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.public_key or "")
        self.note.configure(text="In die Zwischenablage kopiert.", style="Muted.TLabel")

    def check_access(self):
        repository = self.repository.get().strip()
        if not self.core.valid_repository(repository):
            self.note.configure(text="Bitte das Repository als Besitzer/Name angeben, z. B. mauricekleindienst/kiosk.", style="missing.TLabel")
            return
        self.note.configure(text="Prüfe den Zugang…", style="Muted.TLabel")
        self.root.update_idletasks()
        self.access = self.core.test_access(repository)
        if self.access == "public":
            self.note.configure(text="Zugang geprüft: Das Repository ist öffentlich, ein Schlüssel ist nicht nötig.", style="ok.TLabel")
        elif self.access == "key":
            self.note.configure(text="Zugang geprüft: Der Schlüssel funktioniert.", style="ok.TLabel")
        else:
            self.note.configure(text="Kein Zugang. Ist der Schlüssel auf GitHub eingetragen und das Repository richtig geschrieben?", style="missing.TLabel")

    def reboot_env(self):
        env = dict(os.environ)
        if self.password.get():
            _, extra = self.core.install_command(self.password.get())
            env.update({key: value for key, value in extra.items() if key in ("SUDO_ASKPASS", "KIOSK_SUDO_PASSWORD")})
        return env

    def start_work(self):
        self.running = True
        self.next.configure(state="disabled")
        self.back.configure(state="disabled")
        self.bar.start(12)
        # Tk variables may only be read on this thread; the worker gets plain values.
        job = {
            "remove": self.mode.get() == "remove",
            "password": self.password.get() or None,
            "admin": self.admin.get(),
            "cec": self.cec.get(),
            "connect": self.updates.get() and self.access,
            "repository": self.repository.get().strip(),
            "branch": self.branch.get().strip() or "main",
            "access": self.access,
        }
        threading.Thread(target=self.work, args=(job,), daemon=True).start()
        self.root.after(100, self.drain)

    def say(self, line):
        self.messages.put(("line", line))

    def work(self, job):
        try:
            if job["remove"]:
                argv, env = self.core.uninstall_command()
            else:
                self.core.write_config(self.core.config_path(), job["admin"])
                self.say("Einstellungen gespeichert.")
                if job["connect"]:
                    self.say("Verbinde den Kiosk-Ordner mit GitHub…")
                    self.core.connect_checkout(job["repository"], job["branch"], job["access"])
                    self.say("Verbunden.")
                argv, env = self.core.install_command(job["password"], cec=job["cec"])
            process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                       env={**os.environ, **env})
            for line in process.stdout:
                self.say(line.rstrip())
            code = process.wait()
            self.messages.put(("done", code == 0))
        except (OSError, RuntimeError) as err:
            self.say(str(err))
            self.messages.put(("done", False))

    def drain(self):
        try:
            while True:
                kind, value = self.messages.get_nowait()
                if kind == "line":
                    self.log.configure(state="normal")
                    self.log.insert("end", value + "\n")
                    self.log.see("end")
                    self.log.configure(state="disabled")
                else:
                    self.finish(value)
                    return
        except queue.Empty:
            pass
        self.root.after(100, self.drain)

    def finish(self, ok):
        self.running = False
        self.bar.stop()
        if ok:
            self.succeeded = True
            self.step = 5
            self.show()
        else:
            self.say("Das hat nicht geklappt. Die Meldungen oben sagen, woran es lag; danach erneut versuchen.")
            self.drain_once()
            self.next.configure(state="normal", text="Erneut versuchen")
            self.back.configure(state="normal")

    def drain_once(self):
        while not self.messages.empty():
            kind, value = self.messages.get_nowait()
            if kind == "line":
                self.log.configure(state="normal")
                self.log.insert("end", value + "\n")
                self.log.configure(state="disabled")


def main():
    root = tk.Tk()
    SetupApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
