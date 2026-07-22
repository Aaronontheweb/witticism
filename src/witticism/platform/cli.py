import argparse
import ast
import json
import os
import platform
import shutil
import subprocess
import sys
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


# ---------------------------------------------------------------------------
# Opt-in GNOME Shell extension lifecycle (see docs/adr/003).
# ---------------------------------------------------------------------------

def _print_extension_disclosure():
    print("This will install the optional Witticism GNOME Shell extension.")
    print("")
    print("What it is and what it does:")
    print("  - It is a GNOME Shell extension installed into your user profile at")
    print(f"      ~/.local/share/gnome-shell/extensions/{EXTENSION_UUID}")
    print("  - It runs inside the GNOME Shell process and observes keyboard")
    print("    events only to detect the shortcuts you have configured.")
    print("  - It forwards ONLY the matched shortcut identifiers and timestamps")
    print("    to Witticism; your keystrokes are never stored or forwarded.")
    print("  - On Wayland it will NOT activate until you log out and back in.")
    print("")
    print("Why you might want it: it enables true hold-to-talk on GNOME Wayland")
    print("sessions that do not expose the GlobalShortcuts portal. Without it the")
    print("hotkey still works, in press-to-toggle mode.")
    print("")
    print("To remove it later, run:")
    print("  witticism-platform uninstall-gnome-extension")
    print("")


def _confirm(assume_yes):
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        print("Refusing to install without confirmation.")
        print("Re-run with --yes (or -y) to install non-interactively.")
        return False
    reply = input(f"Install the {EXTENSION_UUID} extension now? [y/N] ").strip().lower()
    if reply in ("y", "yes"):
        return True
    print("Aborted. No changes were made.")
    return False


def install_extension(assume_yes=False):
    _print_extension_disclosure()
    if not _confirm(assume_yes):
        return 1

    source = resources.files("witticism.platform").joinpath("gnome_shell_extension")
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
    print(f"Installed the extension files for {EXTENSION_UUID}.")

    result = subprocess.run(["gnome-extensions", "enable", EXTENSION_UUID], capture_output=True, text=True, check=False)
    if result.returncode:
        # The running Shell could not enable a freshly side-loaded extension
        # (typical on Wayland before the first relogin). Pre-enable it via
        # gsettings so GNOME loads it on the next login.
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
            print("Pre-enabled it in GNOME's enabled-extensions list for the next login.")
        else:
            print("It was already present in GNOME's enabled-extensions list.")
        print("")
        print("Almost done: log out and back in once to load the extension.")
        print("Until then, the hotkey keeps working in press-to-toggle mode.")
        return 0

    print("Enabled the extension in the running GNOME Shell.")
    print("")
    print("On Wayland you must still log out and back in once before it loads.")
    return 0


def _remove_from_enabled_extensions():
    """Mirror of install's pre-enable fallback: drop the UUID from
    org.gnome.shell enabled-extensions. `gnome-extensions disable` only works
    for extensions the running Shell has loaded, so an extension that was
    pre-enabled but never loaded (Wayland before relogin) leaves a stale
    entry behind unless it is removed here."""
    current = subprocess.run(
        ["gsettings", "get", "org.gnome.shell", "enabled-extensions"],
        capture_output=True,
        text=True,
        check=False,
    )
    if current.returncode:
        return False
    try:
        enabled = ast.literal_eval(current.stdout.strip())
    except (SyntaxError, ValueError):
        return False
    if EXTENSION_UUID not in enabled:
        return False
    enabled = [uuid for uuid in enabled if uuid != EXTENSION_UUID]
    removed = subprocess.run(
        ["gsettings", "set", "org.gnome.shell", "enabled-extensions", repr(enabled)],
        capture_output=True,
        text=True,
        check=False,
    )
    return removed.returncode == 0


def uninstall_extension():
    print(f"Removing the Witticism GNOME Shell extension ({EXTENSION_UUID}).")
    disabled = subprocess.run(
        ["gnome-extensions", "disable", EXTENSION_UUID], capture_output=True, text=True, check=False
    )
    if disabled.returncode == 0:
        print("Disabled it in the running GNOME Shell.")
    if _remove_from_enabled_extensions():
        print("Removed it from GNOME's enabled-extensions list.")
    target = _extension_target()
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
        print("Removed the installed extension files.")
    else:
        print("No installed extension files were found.")
    print("")
    print("Log out and back in once to fully unload it from GNOME Shell.")
    return 0


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

def _safe_portal_interfaces():
    try:
        return portal_interfaces()
    except Exception:
        return set()


def _probe_shortcut():
    try:
        status = create_shortcut_adapter().probe()
        return status.backend, status.state.value, status.recovery_action
    except Exception:
        return "none", "unavailable", "Shortcut backend could not be probed"


def _probe_output():
    try:
        return create_text_output_adapter().status.backend
    except Exception:
        return "clipboard"


def _probe_extension():
    installed = False
    loaded = False
    try:
        installed = (_extension_target() / "metadata.json").exists()
    except Exception:
        installed = False
    try:
        if shutil.which("gnome-extensions"):
            info = subprocess.run(
                ["gnome-extensions", "info", EXTENSION_UUID],
                capture_output=True,
                text=True,
                check=False,
            )
            loaded = info.returncode == 0
    except Exception:
        loaded = False
    return installed, loaded


def _restore_grant_present():
    try:
        return (Path(platformdirs.user_state_dir("witticism")) / "wayland-portal.json").exists()
    except Exception:
        return False


def _autopaste_consent():
    """Read the saved automatic typing consent state ("unset"/"granted"/"declined").

    Reads only our own config value; the opaque portal restore token lives in a
    separate 0600 state file and is never read or reported here.
    """
    try:
        path = Path(platformdirs.user_config_dir("witticism")) / "config.json"
        if not path.exists():
            return "unset"
        data = json.loads(path.read_text())
        value = data.get("output", {}).get("autopaste", "unset")
        return value if value in ("unset", "granted", "declined") else "unset"
    except Exception:
        return "unset"


def _keybinding_registered():
    """Whether Witticism's own GNOME custom keybinding entries are present.

    Checks only for the presence of our ``witticism-`` entries; it never reads
    or reports the names or paths of any other custom keybinding, so no private
    user shortcut data leaks into diagnostics.
    """
    try:
        result = subprocess.run(
            ["gsettings", "get", "org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return False
        return "witticism-" in (result.stdout or "")
    except Exception:
        return False


def _keyboard_repeat_enabled():
    """Whether GNOME key auto-repeat is on (the custom-keybinding backend needs
    it to infer hold-to-talk). Defaults to True when it cannot be determined."""
    try:
        result = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.peripherals.keyboard", "repeat"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return True
        return "false" not in (result.stdout or "").strip().lower()
    except Exception:
        return True


def _shortcut_capability(backend, state, extension_loaded, keyboard_repeat=True):
    """Map a shortcut backend to its user-facing capability tier."""
    b = (backend or "").lower()
    if state == "unavailable" or b in ("", "none"):
        return "unavailable"
    if b == "gnome-media-keys" or "media-keys" in b or "keybinding" in b:
        # The custom-keybinding backend infers hold-to-talk from the key-repeat
        # stream; without key repeat it can only do press-to-toggle.
        return "hold-to-talk" if keyboard_repeat else "press-to-toggle (fallback)"
    if b == "gnome-shell-extension":
        # The extension only delivers hold-to-talk once it is actually loaded in
        # the running Shell, which requires a fresh login after installation.
        return "hold-to-talk" if extension_loaded else "press-to-toggle (fallback)"
    if "pynput" in b or "global-shortcuts" in b or "portal" in b:
        return "hold-to-talk"
    return "press-to-toggle (fallback)"


def _output_capability(backend, autopaste_consent="unset", token_present=False):
    """User-facing output tier.

    "portal typing" is reported only when automatic typing has been granted AND
    a restore token exists (so it would actually work). Clipboard-first is the
    designed Wayland default, not a degradation.
    """
    b = (backend or "").lower()
    if "pynput" in b:
        return "typing"
    if "remote-desktop" in b and autopaste_consent == "granted" and token_present:
        return "portal typing"
    return "clipboard"


def _how_to_improve(report):
    tier = report["shortcut_capability"]
    desktop = report["desktop"].lower()
    if tier == "press-to-toggle (fallback)" and "gnome" in desktop:
        if report["gnome_extension_installed"] and not report["gnome_extension_loaded"]:
            return (
                "The optional GNOME Shell extension is installed but not active yet. "
                "Log out and back in once to switch to hold-to-talk."
            )
        return (
            "For hold-to-talk, optionally run: witticism-platform install-gnome-extension "
            "(installs a GNOME Shell extension; requires logging out and back in)."
        )
    if tier == "unavailable":
        return report.get("shortcut_recovery") or (
            "This session cannot capture global shortcuts. Use an X11 session or the tray controls."
        )
    if (
        report["output_capability"] == "clipboard"
        and report["display_protocol"].lower() == "wayland"
        and report.get("autopaste_consent") in ("unset", "declined")
    ):
        return (
            "Transcripts are copied to the clipboard. You can optionally enable automatic typing "
            "(a one-time GNOME permission) from the Witticism tray menu."
        )
    return None


def _render_doctor_text(report):
    def yn(value):
        return "yes" if value else "no"

    lines = [
        "Witticism platform diagnostics",
        "",
        f"  Session type:            {report['display_protocol']}",
        f"  Desktop:                 {report['desktop']}",
        f"  GlobalShortcuts portal:  {yn(report['global_shortcuts_portal'])}",
        f"  RemoteDesktop portal:    {yn(report['remote_desktop_portal'])}",
        f"  Shortcut backend:        {report['shortcut_adapter']} ({report['shortcut_capability']})",
        f"  Output backend:          {report['output_adapter']} ({report['output_capability']})",
        f"  Automatic typing:        {report['autopaste_consent']}",
        f"  GNOME extension:         installed={yn(report['gnome_extension_installed'])} "
        f"running={yn(report['gnome_extension_loaded'])}",
        f"  Portal restore grant:    {yn(report['portal_restore_permission_present'])}",
    ]
    if "gnome" in report["desktop"].lower():
        lines.append(
            f"  GNOME keybinding:        registered={yn(report['keybinding_registered'])} "
            f"key-repeat={yn(report['keyboard_repeat_enabled'])}"
        )
    if report.get("how_to_improve"):
        lines += ["", f"  How to improve: {report['how_to_improve']}"]
    return "\n".join(lines)


def doctor(as_json=False):
    interfaces = _safe_portal_interfaces()
    shortcut_backend, shortcut_state, shortcut_recovery = _probe_shortcut()
    output_backend = _probe_output()
    extension_installed, extension_loaded = _probe_extension()

    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "unknown")
    is_gnome = "gnome" in desktop.lower()
    autopaste_consent = _autopaste_consent()
    restore_grant = _restore_grant_present()
    keyboard_repeat = _keyboard_repeat_enabled() if is_gnome else True

    capability = _shortcut_capability(shortcut_backend, shortcut_state, extension_loaded, keyboard_repeat)
    if shortcut_backend == "gnome-shell-extension" and not extension_loaded:
        shortcut_state = "requires_action"
        shortcut_recovery = "Log out and back in" if extension_installed else "Run: witticism-platform install-gnome-extension"

    report = {
        "schema_version": 1,
        "operating_system": platform.system(),
        "display_protocol": os.environ.get("XDG_SESSION_TYPE", "unknown"),
        "desktop": desktop,
        "global_shortcuts_portal": GLOBAL_SHORTCUTS in interfaces,
        "remote_desktop_portal": REMOTE_DESKTOP in interfaces,
        "shortcut_adapter": shortcut_backend,
        "shortcut_state": shortcut_state,
        "shortcut_recovery": shortcut_recovery,
        "shortcut_capability": capability,
        "keybinding_registered": _keybinding_registered() if is_gnome else False,
        "keyboard_repeat_enabled": keyboard_repeat,
        "output_adapter": output_backend,
        "output_capability": _output_capability(output_backend, autopaste_consent, restore_grant),
        "autopaste_consent": autopaste_consent,
        "gnome_extension_installed": extension_installed,
        "gnome_extension_loaded": extension_loaded,
        "gnome_extension_restart_required": extension_installed and not extension_loaded,
        "portal_restore_permission_present": restore_grant,
    }
    report["how_to_improve"] = _how_to_improve(report)

    if as_json:
        print(json.dumps(report, indent=2))
    else:
        print(_render_doctor_text(report))
    return 0


def main():
    parser = argparse.ArgumentParser(description="Witticism platform integration tools")
    commands = parser.add_subparsers(dest="command", required=True)

    doctor_parser = commands.add_parser("doctor", help="Report platform integration status")
    doctor_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    install_parser = commands.add_parser(
        "install-gnome-extension", help="Install the optional GNOME Shell extension (opt-in)"
    )
    install_parser.add_argument(
        "-y", "--yes", action="store_true", help="Skip the interactive confirmation prompt"
    )

    commands.add_parser("uninstall-gnome-extension", help="Remove the GNOME Shell extension")

    args = parser.parse_args()
    if args.command == "doctor":
        return doctor(as_json=args.json)
    if args.command == "install-gnome-extension":
        return install_extension(assume_yes=args.yes)
    return uninstall_extension()


if __name__ == "__main__":
    raise SystemExit(main())
