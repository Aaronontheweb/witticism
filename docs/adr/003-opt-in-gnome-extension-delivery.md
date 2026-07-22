# ADR-003: Opt-In Delivery of the GNOME Shell Extension

**Status:** Accepted

**Date:** 2026-07-21

## Context

ADR-002 introduced an optional GNOME Shell extension so that GNOME Wayland sessions without the GlobalShortcuts portal (GNOME 46 and 47) could still capture a held hotkey. The initial delivery mechanism was wrong: `install.sh` detected GNOME and silently ran `witticism-platform install-gnome-extension`, which side-loaded the extension into the user's profile and force-enabled it through GNOME's `enabled-extensions` setting.

That approach has several problems:

1. **The installer mutated the desktop shell.** A voice-transcription installer has no business writing to `org.gnome.shell enabled-extensions` or dropping code into `~/.local/share/gnome-shell/extensions` without an explicit, informed decision by the user.
2. **The extension runs inside GNOME Shell.** Its code executes in the compositor process and observes keyboard events. Enabling that automatically, as a side effect of an unrelated install, is not consent.
3. **The logout requirement was hidden.** On Wayland the newly registered extension does not load until the next login. A user who never saw the install happen has no reason to log out, so the "integration" silently does nothing and looks like a bug.
4. **Lifecycle drift under pipx.** Witticism is installed with pipx. A `pipx upgrade` or `pipx uninstall` does not run `install.sh` and does not manage the side-loaded extension, so the shell-level artifact and its enabled-extensions entry drift out of sync with the installed package and can outlive it.

Separately, GNOME 46/47 Wayland users needed a working default that requires no shell extension at all.

## Decision

The GNOME Shell extension is strictly opt-in and is never deployed by the installer.

- **`install.sh` prints guidance only.** When it detects a GNOME Wayland session it explains that hold-to-talk is available via an optional extension and shows the exact command to run. It mutates nothing.
- **The extension is deployed only through an explicit, consented CLI.** `witticism-platform install-gnome-extension` first discloses what the extension is, that it runs inside GNOME Shell and observes keyboard events to detect only the configured shortcuts (forwarding only shortcut identifiers and timestamps, never keystrokes), that it will not activate until the user logs out and back in, and how to remove it. It then requires confirmation: an interactive `y/N` prompt, bypassable with `--yes` for automation. A non-interactive invocation without `--yes` refuses and exits non-zero.
- **Press-to-toggle is the no-setup default.** On GNOME 46/47 Wayland without the portal and without the extension, Witticism registers a standard GNOME custom keyboard shortcut (Settings > Keyboard > Custom Shortcuts) that works with no installation and no logout. Because a custom shortcut delivers only key-press events, the hotkey behaves as press-to-toggle (press once to start recording, press again to stop) rather than hold-to-talk. This is immediately working, and diagnostics point the user at the optional extension for the full hold-to-talk experience. (The original `org.gnome.Shell.GrabAccelerator` fallback proposed here was found to be sender-allowlisted to GNOME's own components since GNOME 41 and unusable by third-party apps; see [ADR-004](004-gnome-keybinding-press-to-toggle.md).)
- **extensions.gnome.org is the preferred long-term channel.** Distributing the extension through the official GNOME Extensions site is the intended future path, so that install, update, and removal are handled by GNOME's own tooling instead of a side-load. Until then, the consented CLI is the only supported install route.

Delivery is the only thing this ADR changes; the adapter contracts, shortcut-identifier-only bridge, and portal token isolation from ADR-002 are unchanged.

## Consequences

Installing Witticism no longer touches the GNOME Shell configuration. GNOME 46/47 Wayland users get a working hotkey immediately in press-to-toggle mode and can knowingly upgrade to hold-to-talk with a single documented, consented command that tells them a logout is required. Users who never opt in never have extension code running in their compositor.

The trade-off is that hold-to-talk is no longer automatic on GNOME 46/47: it is a deliberate extra step. The side-loaded extension still carries the pipx lifecycle-drift caveat until distribution moves to extensions.gnome.org; `witticism-platform doctor` reports installed/running state and a restart-required hint so the drift is at least visible, and `witticism-platform uninstall-gnome-extension` removes it symmetrically.
