# Platform Input and Output Adapters

This document is the maintained runtime contract for desktop integration. ADR-002 records why the contract exists.

## Support matrix

| Platform / session | Shortcut backend | Capability tier | Text delivery | Release status |
|---|---|---|---|---|
| Windows | pynput Win32 | hold-to-talk | pynput typing | Supported |
| Linux X11 | pynput Xorg | hold-to-talk | pynput typing | Supported |
| Wayland with GlobalShortcuts portal (KDE, GNOME 48+) | XDG GlobalShortcuts | hold-to-talk | Clipboard plus Remote Desktop portal paste | Supported |
| GNOME 46/47 Wayland, extension installed and running | Witticism GNOME Shell extension | hold-to-talk | Clipboard plus Remote Desktop portal paste | Supported |
| GNOME 46/47 Wayland, no extension | `org.gnome.Shell.GrabAccelerator` fallback | press-to-toggle | Clipboard plus Remote Desktop portal paste | Supported (degraded) |
| Other Wayland without the portal | none | unavailable (tray/manual only) | Clipboard only | Degraded |
| macOS | none | unavailable | Clipboard only | Unsupported |

The three capability tiers are **hold-to-talk** (hold the hotkey to record, release to stop), **press-to-toggle (fallback)** (press once to start, press again to stop), and **unavailable** (no global shortcut; tray and manual controls only). The `GrabAccelerator` fallback is press-to-toggle by necessity: that API delivers only an activation event and never a key release, so a held-key model is impossible. It is the no-setup default on GNOME 46/47 Wayland; the optional extension upgrades those sessions to hold-to-talk.

Wayland intentionally prevents ordinary applications from monitoring or synthesizing arbitrary keyboard input. Witticism must never run its Xorg adapter under Wayland and claim success.

## Contracts

`ShortcutAdapter` owns platform registration and emits normalized `ShortcutEvent` values. It must emit at most one activation and one deactivation per physical hold, propagate the underlying key to the focused application, update bindings atomically, release active holds during shutdown, and never invoke transcription itself.

`TextOutputAdapter` owns delivery only. X11 and Windows retain direct typing. Wayland copies the complete transcript to the clipboard and requests keyboard-only Remote Desktop portal access to inject Ctrl+V. It must release synthetic modifiers in a `finally` path. Failure degrades to clipboard output.

`HotkeyManager` owns PTT state, debounce, toggle mode, and application callbacks. Platform behavior must not leak into this state machine.

Adapter states are `unavailable`, `requires_action`, `starting`, `ready`, `degraded`, `failed`, and `stopped`. Only `starting`, `ready`, and `degraded` are usable. A non-usable adapter must provide a recovery action suitable for the UI and diagnostics.

## Selection

Shortcut backend, in order:

1. Windows selects pynput (hold-to-talk).
2. Linux outside Wayland (X11) selects pynput (hold-to-talk).
3. Wayland with `org.freedesktop.portal.GlobalShortcuts` (KDE, GNOME 48+) selects the portal (hold-to-talk).
4. GNOME Wayland without that portal (e.g. GNOME 46/47):
   - if the optional Witticism GNOME Shell extension (`witticism@stannardlabs.com`) is installed and running, select it (hold-to-talk);
   - otherwise select the `org.gnome.Shell.GrabAccelerator` fallback (press-to-toggle).
5. Other Wayland sessions without the portal expose no shortcut backend; the tray and manual controls remain available.
6. Shortcut and output selection are independent.

Text output:

1. Windows and X11 select pynput typing.
2. Wayland selects clipboard plus Ctrl+V paste through a keyboard-only Remote Desktop portal session with a persisted restore token; denial, revocation, or a locked session degrades to clipboard-only.
3. The `output.mode: "clipboard"` configuration forces clipboard-only on all platforms.

Display and portal detection must occur before importing pynput. Dynamic binding changes are forwarded to the active adapter. Portal shortcut changes establish a replacement session because the portal permits binding once per session.

## GNOME bridge and the GrabAccelerator fallback

On GNOME Wayland without the GlobalShortcuts portal, two backends are possible.

The **`org.gnome.Shell.GrabAccelerator` fallback** is the no-setup default. It grabs the configured accelerator through GNOME Shell's built-in D-Bus method and needs no installation, but the API reports only accelerator activations, so the hotkey works as press-to-toggle rather than hold-to-talk.

The **optional GNOME Shell extension** upgrades those sessions to hold-to-talk. It owns `com.stannardlabs.Witticism.Shell` and accepts configuration only from the owner of `com.stannardlabs.Witticism`. It emits configured shortcut identifiers and timestamps, never raw keys. It observes without consuming events, ignores input while locked, suppresses repeats, and disconnects all Shell signals when disabled.

The initial extension artifact supports GNOME Shell 46 and 47. Each additional Shell major version must be added only after release qualification because extensions run inside GNOME Shell.

### Delivery (opt-in)

Deploying the extension is governed by [ADR-003](adr/003-opt-in-gnome-extension-delivery.md) and is strictly opt-in. `install.sh` never installs or enables it; on a GNOME Wayland session it prints guidance only. The extension is deployed exclusively through `witticism-platform install-gnome-extension`, which first discloses what the extension is and does, then requires explicit confirmation (interactive `y/N`, bypassable with `--yes`; a non-interactive run without `--yes` refuses and exits non-zero).

GNOME Wayland does not rescan a newly installed local extension in the running Shell. The install command enables it live where possible and otherwise pre-enables it by writing the UUID to GNOME's `enabled-extensions` setting; either way the user must log out and back in once after the first installation before it loads. Updates to an already registered extension can be enabled normally. `witticism-platform uninstall-gnome-extension` disables and removes it symmetrically. Distribution through extensions.gnome.org is the preferred long-term channel so that GNOME's own tooling manages the lifecycle.

## Portal permissions and state

Remote Desktop requests keyboard access only: no screen, pointer, touchscreen, or portal clipboard access. The first authorization uses persistent mode. Its opaque, single-use restore token is stored separately from user configuration with mode 0600 and atomically rotated. Tokens must never appear in logs, diagnostics, configuration exports, or issues.

If authorization is denied, revoked, or disconnected, transcription continues and remains on the clipboard. The transcript intentionally remains there after auto-paste; delayed clipboard restoration is unreliable across toolkits.

GNOME inhibits new Remote Desktop sessions while the desktop is locked. If Witticism starts in that state, automatic paste remains degraded until the session is unlocked and Witticism is restarted; shortcut capture remains independent.

## Adding an adapter

Implement the relevant contract, keep imports lazy, add selection without changing higher-level PTT semantics, provide actionable probe status, add shared contract tests, document permissions, and add the platform to release qualification. An adapter may not be marked supported using mocks alone.

## Diagnostics

`witticism-platform doctor` reports session type, desktop, portal capabilities (GlobalShortcuts and RemoteDesktop), the selected shortcut backend and its capability tier (hold-to-talk, press-to-toggle (fallback), or unavailable), the selected output backend (portal paste, typing, or clipboard-only), the extension installed/running state, and whether a portal restore grant exists. When a session is degraded it also prints a "how to improve" line, such as the opt-in extension install hint with its logout caveat on GNOME.

Output defaults to human-readable text; `--json` emits the machine-readable report. `doctor` degrades gracefully when D-Bus is unreachable, reporting whatever it can rather than crashing. It must not report usernames, hostnames, hardware, devices, paths, tokens, transcripts, environment dumps, or raw logs.
