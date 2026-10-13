"""What the graphical installer does, without any window: checks, GitHub access for updates, the
owner configuration and the commands that install or remove the kiosk. Kept free of tkinter, so it
is tested on its own (installer/tests) and on any Python the Pi has."""

import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "mauricekleindienst/kiosk"
SSH_ALIAS = "github-kiosk"
KEY_NAME = "kiosk_deploy"
ADMIN_PORT = 8081
# owner/name; a part may not start with a dot (no "." or ".." tricks).
_REPO = re.compile(r"^(?!\.)[A-Za-z0-9_.-]+/(?!\.)[A-Za-z0-9_.-]+$")
_SSH_BLOCK_START = "# >>> kiosk deploy key >>>"
_SSH_BLOCK_END = "# <<< kiosk deploy key <<<"


def run(args, **kwargs):
    """subprocess.run with captured text output and no prompts; replaced in tests."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", **kwargs.pop("env", {})}
    return subprocess.run(args, capture_output=True, text=True, check=False, env=env, timeout=kwargs.pop("timeout", 120), **kwargs)


@dataclass
class Check:
    label: str
    state: str  # "ok", "warn" (works, but note it) or "missing" (the installer fixes it or cannot go on)
    detail: str


def checks(environ=None, which=shutil.which, runner=run, version=sys.version_info, os_release=Path("/etc/os-release")):
    environ = os.environ if environ is None else environ
    result = []
    name = "Linux"
    try:
        for line in os_release.read_text(encoding="utf-8").splitlines():
            if line.startswith("PRETTY_NAME="):
                name = line.split("=", 1)[1].strip('"')
    except OSError:
        pass
    is_pi_os = "Raspbian" in name or "Raspberry Pi OS" in name or "Debian" in name
    result.append(Check("Betriebssystem", "ok" if is_pi_os else "warn",
                        name if is_pi_os else f"{name}: gedacht ist der Kiosk für Raspberry Pi OS; es kann trotzdem gehen."))
    result.append(Check("Python", "ok" if version >= (3, 11) else "missing",
                        f"{version[0]}.{version[1]}" if version >= (3, 11) else "Python 3.11 oder neuer wird gebraucht (Raspberry Pi OS Bookworm)."))
    chromium = which("chromium") or which("chromium-browser")
    result.append(Check("Chromium", "ok" if chromium else "missing", "vorhanden" if chromium else "wird bei der Installation nachinstalliert"))
    result.append(Check("Git", "ok" if which("git") else "missing",
                        "vorhanden" if which("git") else "wird für automatische Updates gebraucht: sudo apt install git"))
    session = "Wayland" if environ.get("WAYLAND_DISPLAY") else "X11" if environ.get("DISPLAY") else None
    result.append(Check("Desktop", "ok" if session else "warn",
                        session or "keine Desktop-Sitzung erkannt; der Bildschirm startet nach der Anmeldung am Desktop"))
    sudo_free = runner(["sudo", "-n", "true"]).returncode == 0 if which("sudo") else False
    result.append(Check("Administratorrechte", "ok" if sudo_free else "warn",
                        "ohne Passwort" if sudo_free else "die Installation fragt nach dem Passwort"))
    return result


def needs_sudo_password(runner=run, which=shutil.which):
    return not (which("sudo") and runner(["sudo", "-n", "true"]).returncode == 0)


# Owner configuration (~/.config/kiosk/config.json): only the keys the installer manages change.

def config_path(home=None):
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path(home or Path.home()) / ".config"))
    return base / "kiosk" / "config.json"


def read_config(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_config(path, admin_enabled):
    path = Path(path)
    data = read_config(path)
    if admin_enabled:
        data.pop("adminPort", None)
    else:
        data["adminPort"] = None
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temp, path)
    return data


# GitHub access for nightly updates.

def valid_repository(text):
    return bool(_REPO.match(text or ""))


def key_path(home=None):
    return Path(home or Path.home()) / ".ssh" / KEY_NAME


def ensure_key(home=None, runner=run, hostname=None):
    """Creates the read-only deploy key once and returns its public half."""
    key = key_path(home)
    if not key.exists():
        key.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        comment = f"kiosk@{hostname or socket.gethostname()}"
        result = runner(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", comment, "-f", str(key)])
        if result.returncode != 0:
            raise RuntimeError(f"Der Schlüssel konnte nicht erzeugt werden: {result.stderr.strip()}")
    write_ssh_config(home)
    return Path(f"{key}.pub").read_text(encoding="utf-8").strip()


def write_ssh_config(home=None):
    """A host alias that uses only the deploy key, so other keys on the Pi are not affected."""
    config = Path(home or Path.home()) / ".ssh" / "config"
    text = config.read_text(encoding="utf-8") if config.exists() else ""
    block = (f"{_SSH_BLOCK_START}\nHost {SSH_ALIAS}\n  HostName github.com\n  User git\n"
             f"  IdentityFile {key_path(home)}\n  IdentitiesOnly yes\n  StrictHostKeyChecking accept-new\n{_SSH_BLOCK_END}\n")
    if _SSH_BLOCK_START in text:
        text = re.sub(re.escape(_SSH_BLOCK_START) + r".*?" + re.escape(_SSH_BLOCK_END) + r"\n?", block, text, flags=re.S)
    else:
        text = (text.rstrip("\n") + "\n\n" if text.strip() else "") + block
    config.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    config.write_text(text, encoding="utf-8")
    config.chmod(stat.S_IRUSR | stat.S_IWUSR)


def remote_url(repository, mode):
    return f"https://github.com/{repository}.git" if mode == "public" else f"git@{SSH_ALIAS}:{repository}.git"


def test_access(repository, runner=run):
    """'public' when anyone can read the repository, 'key' when the deploy key works, else None."""
    if runner(["git", "ls-remote", "--heads", remote_url(repository, "public")], timeout=30).returncode == 0:
        return "public"
    ssh = {"GIT_SSH_COMMAND": "ssh -o BatchMode=yes -o ConnectTimeout=10"}
    if runner(["git", "ls-remote", "--heads", remote_url(repository, "key")], env=ssh, timeout=30).returncode == 0:
        return "key"
    return None


def current_branch(root=ROOT, runner=run):
    result = runner(["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"])
    branch = result.stdout.strip() if result.returncode == 0 else ""
    return branch if branch and branch != "HEAD" else "main"


def connect_checkout(repository, branch, mode, root=ROOT, runner=run):
    """Makes the kiosk folder a git checkout that follows `branch`, so update.sh can fast-forward.
    A folder from a ZIP becomes a checkout of the same branch."""
    url = remote_url(repository, mode)
    git = ["git", "-C", str(root)]
    steps = []
    if runner([*git, "rev-parse", "--is-inside-work-tree"]).returncode != 0:
        steps.append([*git, "init", "-q"])
        steps.append([*git, "remote", "add", "origin", url])
    else:
        has_origin = runner([*git, "remote", "get-url", "origin"]).returncode == 0
        steps.append([*git, "remote", "set-url" if has_origin else "add", "origin", url])
    steps.append([*git, "fetch", "-q", "origin", branch])
    # The kiosk folder is a deployment: its files become exactly those of the branch.
    steps.append([*git, "checkout", "-q", "-f", "-B", branch, f"origin/{branch}"])
    steps.append([*git, "branch", "-q", f"--set-upstream-to=origin/{branch}", branch])
    ssh = {"GIT_SSH_COMMAND": "ssh -o BatchMode=yes -o ConnectTimeout=10"}
    for step in steps:
        result = runner(step, env=ssh, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"{' '.join(step[3:])} ist fehlgeschlagen: {result.stderr.strip() or result.stdout.strip()}")


# Install and remove.

def askpass_helper(directory):
    """A helper that hands sudo the password from the environment, so it never sits in a file."""
    helper = Path(directory) / "askpass.sh"
    helper.write_text('#!/bin/sh\nprintf "%s\\n" "$KIOSK_SUDO_PASSWORD"\n', encoding="utf-8")
    helper.chmod(stat.S_IRWXU)
    return helper


def install_command(password=None, cec=False, root=ROOT, temp_dir=None):
    """argv and environment for scripts/install.sh."""
    env = {}
    if cec:
        env["KIOSK_CEC"] = "1"
    if password is not None:
        temp_dir = temp_dir or tempfile.mkdtemp(prefix="kiosk-setup-")
        env.update(KIOSK_SUDO="sudo -A", SUDO_ASKPASS=str(askpass_helper(temp_dir)), KIOSK_SUDO_PASSWORD=password)
    return ["bash", str(root / "scripts" / "install.sh")], env


def uninstall_command(root=ROOT):
    return ["bash", str(root / "scripts" / "uninstall.sh")], {}


def installed(home=None):
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path(home or Path.home()) / ".config"))
    return (base / "systemd" / "user" / "kiosk.service").exists()


def admin_urls(port=ADMIN_PORT, hostname=None):
    name = hostname or socket.gethostname()
    urls = [f"http://{name}.local:{port}"]
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 9))
            urls.insert(0, f"http://{probe.getsockname()[0]}:{port}")
    except OSError:
        pass
    return urls
