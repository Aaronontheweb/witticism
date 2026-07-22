import argparse
import ast
import json
import os
import platform
import shutil
import subprocess
import tempfile
import zipfile
from importlib import resources
from pathlib import Path

import platformdirs

from witticism.platform.input_output import (
    GLOBAL_SHORTCUTS,
    REMOTE_DESKTOP,
    create_shortcut_adapter,
    create_text_output_adapter,
    portal_interfaces,
)

EXTENSION_UUID = "witticism@stannardlabs.com"


def _extension_target():
    return Path.home() / ".local/share/gnome-shell/extensions" / EXTENSION_UUID


def install_extension():
    source = resources.files("witticism.platform").joinpath("gnome_shell_extension")
    target = _extension_target()
    with tempfile.TemporaryDirectory(prefix="witticism-extension-") as temporary:
        archive = Path(temporary) / "witticism-gnome-shell.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
            for item in source.iterdir():
                if item.is_file():
                    bundle.write(str(item), item.name)
        installed = subprocess.run(
            ["gnome-extensions", "install", "--force", str(archive)],
            capture_output=True,
            text=True,
            check=False,
        )
    if installed.returncode:
        print("Could not install the GNOME Shell extension: " + installed.stderr.strip())
        return 1
    result = subprocess.run(["gnome-extensions", "enable", EXTENSION_UUID], capture_output=True, text=True, check=False)
    if result.returncode:
        current = subprocess.run(
            ["gsettings", "get", "org.gnome.shell", "enabled-extensions"],
            capture_output=True,
            text=True,
            check=False,
        )
        try:
            enabled = ast.literal_eval(current.stdout.strip()) if current.returncode == 0 else []
        except (SyntaxError, ValueError):
            enabled = []
        if EXTENSION_UUID not in enabled:
            enabled.append(EXTENSION_UUID)
            subprocess.run(
                ["gsettings", "set", "org.gnome.shell", "enabled-extensions", repr(enabled)],
                capture_output=True,
                text=True,
                check=False,
            )
        print("Witticism GNOME Shell integration installed and enabled for the next login.")
        print("Log out and back in once to load the new extension.")
        return 0
    print("Witticism GNOME Shell integration installed and enabled.")
    return 0


def uninstall_extension():
    subprocess.run(["gnome-extensions", "disable", EXTENSION_UUID], capture_output=True, check=False)
    target = _extension_target()
    if target.exists():
        shutil.rmtree(target)
    print("Witticism GNOME Shell integration removed.")
    return 0


def doctor():
    interfaces = portal_interfaces()
    shortcut = create_shortcut_adapter().probe()
    output = create_text_output_adapter()
    extension = subprocess.run(
        ["gnome-extensions", "info", EXTENSION_UUID], capture_output=True, text=True, check=False
    ) if shutil.which("gnome-extensions") else None
    extension_installed = (_extension_target() / "metadata.json").exists()
    extension_loaded = bool(extension and extension.returncode == 0)
    shortcut_state = shortcut.state.value
    shortcut_recovery = shortcut.recovery_action
    if shortcut.backend == "gnome-shell-extension" and not extension_loaded:
        shortcut_state = "requires_action"
        shortcut_recovery = "Log out and back in" if extension_installed else "Run: witticism-platform install-gnome-extension"
    report = {
        "schema_version": 1,
        "operating_system": platform.system(),
        "display_protocol": os.environ.get("XDG_SESSION_TYPE", "unknown"),
        "desktop": os.environ.get("XDG_CURRENT_DESKTOP", "unknown"),
        "global_shortcuts_portal": GLOBAL_SHORTCUTS in interfaces,
        "remote_desktop_portal": REMOTE_DESKTOP in interfaces,
        "shortcut_adapter": shortcut.backend,
        "shortcut_state": shortcut_state,
        "shortcut_recovery": shortcut_recovery,
        "output_adapter": output.status.backend,
        "gnome_extension_installed": extension_installed,
        "gnome_extension_loaded": extension_loaded,
        "gnome_extension_restart_required": extension_installed and not extension_loaded,
        "portal_restore_permission_present": (Path(platformdirs.user_state_dir("witticism")) / "wayland-portal.json").exists(),
    }
    print(json.dumps(report, indent=2))
    return 0


def main():
    parser = argparse.ArgumentParser(description="Witticism platform integration tools")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor")
    commands.add_parser("install-gnome-extension")
    commands.add_parser("uninstall-gnome-extension")
    args = parser.parse_args()
    if args.command == "doctor":
        return doctor()
    if args.command == "install-gnome-extension":
        return install_extension()
    return uninstall_extension()


if __name__ == "__main__":
    raise SystemExit(main())
