# Platform Input and Output Adapters

This document is the maintained runtime contract for desktop integration. ADR-002 records why the contract exists.

## Support matrix

| Platform | Shortcut capture | Text delivery | Release status |
|---|---|---|---|
| Windows | pynput Win32 | pynput typing | Supported |
| Linux X11 | pynput Xorg | pynput typing | Supported |
| Wayland with Global Shortcuts portal | XDG Global Shortcuts | Clipboard plus Remote Desktop portal paste | Supported |
| GNOME Shell 46 Wayland | Witticism Shell extension | Clipboard plus Remote Desktop portal paste | Supported |
| macOS | None | None | Unsupported |

Wayland intentionally prevents ordinary applications from monitoring or synthesizing arbitrary keyboard input. Witticism must never run its Xorg adapter under Wayland and claim success.

## Contracts

`ShortcutAdapter` owns platform registration and emits normalized `ShortcutEvent` values. It must emit at most one activation and one deactivation per physical hold, propagate the underlying key to the focused application, update bindings atomically, release active holds during shutdown, and never invoke transcription itself.

`TextOutputAdapter` owns delivery only. X11 and Windows retain direct typing. Wayland copies the complete transcript to the clipboard and requests keyboard-only Remote Desktop portal access to inject Ctrl+V. It must release synthetic modifiers in a `finally` path. Failure degrades to clipboard output.

`HotkeyManager` owns PTT state, debounce, toggle mode, and application callbacks. Platform behavior must not leak into this state machine.

Adapter states are `unavailable`, `requires_action`, `starting`, `ready`, `degraded`, `failed`, and `stopped`. Only `starting`, `ready`, and `degraded` are usable. A non-usable adapter must provide a recovery action suitable for the UI and diagnostics.

## Selection

1. Windows selects pynput Win32.
2. Linux outside Wayland selects pynput Xorg.
3. Wayland prefers `org.freedesktop.portal.GlobalShortcuts`.
4. GNOME Wayland without that portal selects `witticism@stannardlabs.com`.
5. Other Wayland sessions without the portal fail visibly.
6. Shortcut and output selection are independent.

Display and portal detection must occur before importing pynput. Dynamic binding changes are forwarded to the active adapter. Portal shortcut changes establish a replacement session because the portal permits binding once per session.

## GNOME bridge

The extension owns `com.stannardlabs.Witticism.Shell` and accepts configuration only from the owner of `com.stannardlabs.Witticism`. It emits configured shortcut identifiers and timestamps, never raw keys. It observes without consuming events, ignores input while locked, suppresses repeats, and disconnects all Shell signals when disabled.

The initial extension artifact supports GNOME Shell 46. Each additional Shell major version must be added only after release qualification because extensions run inside GNOME Shell.

GNOME Wayland does not rescan a newly installed local extension in the running Shell. The installer writes the UUID to GNOME's enabled-extension setting, and the user must log out and back in once after the first installation. Updates to an already registered extension can be enabled normally.

## Portal permissions and state

Remote Desktop requests keyboard access only: no screen, pointer, touchscreen, or portal clipboard access. The first authorization uses persistent mode. Its opaque, single-use restore token is stored separately from user configuration with mode 0600 and atomically rotated. Tokens must never appear in logs, diagnostics, configuration exports, or issues.

If authorization is denied, revoked, or disconnected, transcription continues and remains on the clipboard. The transcript intentionally remains there after auto-paste; delayed clipboard restoration is unreliable across toolkits.

GNOME inhibits new Remote Desktop sessions while the desktop is locked. If Witticism starts in that state, automatic paste remains degraded until the session is unlocked and Witticism is restarted; shortcut capture remains independent.

## Adding an adapter

Implement the relevant contract, keep imports lazy, add selection without changing higher-level PTT semantics, provide actionable probe status, add shared contract tests, document permissions, and add the platform to release qualification. An adapter may not be marked supported using mocks alone.

## Diagnostics

`witticism-platform doctor` reports protocol, desktop, portal capabilities, selected adapters, extension state, and whether a restore grant exists. It must not report usernames, hostnames, hardware, devices, paths, tokens, transcripts, environment dumps, or raw logs.
