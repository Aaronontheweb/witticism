# Platform Input and Output Adapters

This document is the maintained runtime contract for desktop integration. ADR-002 records why the contract exists; [ADR-004](adr/004-gnome-keybinding-press-to-toggle.md) records the GNOME custom-keybinding press-to-toggle default and the consent-gated auto-paste that this document reflects.

## Support matrix

| Platform / session | Shortcut backend | Capability tier | Text delivery | Release status |
|---|---|---|---|---|
| Windows | pynput Win32 | hold-to-talk | pynput typing | Supported |
| Linux X11 | pynput Xorg | hold-to-talk | pynput typing | Supported |
| Wayland with GlobalShortcuts portal (KDE, GNOME 48+) | XDG GlobalShortcuts | hold-to-talk | Clipboard (optional consent-gated portal paste) | Supported |
| GNOME 46/47 Wayland, extension installed and running | Witticism GNOME Shell extension | hold-to-talk | Clipboard (optional consent-gated portal paste) | Supported |
| GNOME 46/47 Wayland, no extension | Standard GNOME custom keyboard shortcut | press-to-toggle | Clipboard (optional consent-gated portal paste) | Supported |
| Other Wayland without the portal | none | unavailable (tray/manual only) | Clipboard only | Degraded |
| macOS | none | unavailable | Clipboard only | Unsupported |

The three capability tiers are **hold-to-talk** (hold the hotkey to record, release to stop), **press-to-toggle (fallback)** (press once to start, press again to stop), and **unavailable** (no global shortcut; tray and manual controls only). The press-to-toggle fallback is press-to-toggle by necessity: a GNOME custom keyboard shortcut delivers only a key-press and never a release, so a held-key model is impossible. It is the no-setup default on GNOME 46/47 Wayland; the optional extension upgrades those sessions to hold-to-talk.

On Wayland, text delivery is clipboard-first by design: transcripts are copied for a plain `Ctrl+V`, with no permission prompt. Automatic paste through the Remote Desktop portal is available but strictly opt-in - it is never probed or started, and GNOME's permission dialog never appears, until the user enables it (see [ADR-004](adr/004-gnome-keybinding-press-to-toggle.md)).

Wayland intentionally prevents ordinary applications from monitoring or synthesizing arbitrary keyboard input. Witticism must never run its Xorg adapter under Wayland and claim success.

## Contracts

`ShortcutAdapter` owns platform registration and emits normalized `ShortcutEvent` values. It must emit at most one activation and one deactivation per physical hold, propagate the underlying key to the focused application, update bindings atomically, release active holds during shutdown, and never invoke transcription itself.

`TextOutputAdapter` owns delivery only. X11 and Windows retain direct typing. Wayland copies the complete transcript to the clipboard by default; only after the user consents does it request keyboard-only Remote Desktop portal access to inject Ctrl+V. It must release synthetic modifiers in a `finally` path. Failure, denial, and the unconsented default all keep output on the clipboard.

`HotkeyManager` owns PTT state, debounce, toggle mode, and application callbacks. Platform behavior must not leak into this state machine.

Adapter states are `unavailable`, `requires_action`, `starting`, `ready`, `degraded`, `failed`, and `stopped`. Only `starting`, `ready`, and `degraded` are usable. A non-usable adapter must provide a recovery action suitable for the UI and diagnostics.

## Selection

Shortcut backend, in order:

1. Windows selects pynput (hold-to-talk).
2. Linux outside Wayland (X11) selects pynput (hold-to-talk).
3. Wayland with `org.freedesktop.portal.GlobalShortcuts` (KDE, GNOME 48+) selects the portal (hold-to-talk).
4. GNOME Wayland without that portal (e.g. GNOME 46/47):
   - if the optional Witticism GNOME Shell extension (`witticism@stannardlabs.com`) is installed and running, select it (hold-to-talk);
   - otherwise register a standard GNOME custom keyboard shortcut (press-to-toggle).
5. Other Wayland sessions without the portal expose no shortcut backend; the tray and manual controls remain available.
6. Shortcut and output selection are independent.

Text output:

1. Windows and X11 select pynput typing.
2. Wayland is clipboard-first by design: transcripts are copied to the clipboard for a manual `Ctrl+V`. Automatic paste (Ctrl+V through a keyboard-only Remote Desktop portal session with a persisted restore token) is **off by default** and consent-gated; see "Auto-paste consent" below. It is never probed or started until the user opts in.
3. The `output.mode: "clipboard"` configuration forces clipboard on all platforms.

Display and portal detection must occur before importing pynput. Dynamic binding changes are forwarded to the active adapter. Portal shortcut changes establish a replacement session because the portal permits binding once per session.

## GNOME bridge and the custom-keybinding fallback

On GNOME Wayland without the GlobalShortcuts portal, two backends are possible.

The **standard GNOME custom keyboard shortcut** is the no-setup default. Witticism registers an ordinary custom shortcut on the `org.gnome.settings-daemon.plugins.media-keys` schema - exactly the kind a user creates by hand in Settings > Keyboard > Custom Shortcuts - whose command asks Witticism, over its own session-bus name (`com.stannardlabs.Witticism`, method `com.stannardlabs.Witticism.Control.TriggerShortcut`), to trigger the bound action. It needs no installation and no logout, is visible and editable in GNOME Settings, injects no code into the compositor, and is removed when Witticism exits. Because a custom shortcut delivers only key-press events, the hotkey works as press-to-toggle rather than hold-to-talk. It preserves every existing user keybinding, refuses to modify an unparseable non-empty list rather than risk clobbering user shortcuts, and cleans up leftover `witticism-*` entries from a crashed run at the next start.

This replaced an earlier `org.gnome.Shell.GrabAccelerator` fallback, which is unusable: that method is sender-allowlisted to GNOME's own components since GNOME 41 and denies third-party callers (see [ADR-004](adr/004-gnome-keybinding-press-to-toggle.md)).

The **optional GNOME Shell extension** upgrades those sessions to hold-to-talk. It owns `com.stannardlabs.Witticism.Shell` and accepts configuration only from the owner of `com.stannardlabs.Witticism`. It emits configured shortcut identifiers and timestamps, never raw keys. It observes without consuming events, ignores input while locked, suppresses repeats, and disconnects all Shell signals when disabled.

The initial extension artifact supports GNOME Shell 46 and 47. Each additional Shell major version must be added only after release qualification because extensions run inside GNOME Shell.

### Delivery (opt-in)

Deploying the extension is governed by [ADR-003](adr/003-opt-in-gnome-extension-delivery.md) and is strictly opt-in. `install.sh` never installs or enables it; on a GNOME Wayland session it prints guidance only. The extension is deployed exclusively through `witticism-platform install-gnome-extension`, which first discloses what the extension is and does, then requires explicit confirmation (interactive `y/N`, bypassable with `--yes`; a non-interactive run without `--yes` refuses and exits non-zero).

GNOME Wayland does not rescan a newly installed local extension in the running Shell. The install command enables it live where possible and otherwise pre-enables it by writing the UUID to GNOME's `enabled-extensions` setting; either way the user must log out and back in once after the first installation before it loads. Updates to an already registered extension can be enabled normally. `witticism-platform uninstall-gnome-extension` disables and removes it symmetrically. Distribution through extensions.gnome.org is the preferred long-term channel so that GNOME's own tooling manages the lifecycle.

## Auto-paste consent

Automatic paste is off by default and strictly opt-in. Until the user consents, the Remote Desktop portal is never touched (no probe, no session, no dialog) and output is clipboard-only. Consent is captured through an in-app priming dialog - Witticism's own branded window that explains what will happen and warns that GNOME will show a system confirmation titled "Remote Desktop" that actually comes from Witticism and covers keyboard input only. The dialog is offered at most once, automatically, right after the first successful transcription (never at startup), and is always reachable manually from the tray ("Enable automatic paste..."). Only when the user opts in does Witticism start the portal session - the single place GNOME's dialog may appear.

Consent state (`output.autopaste`: `unset` | `granted` | `declined`) is persisted, guarded by a one-time `output.autopaste_prompted` flag. See [ADR-004](adr/004-gnome-keybinding-press-to-toggle.md).

## Portal permissions and state

Remote Desktop requests keyboard access only: no screen, pointer, touchscreen, or portal clipboard access. When the user grants auto-paste, authorization uses persistent mode. Its opaque, single-use restore token is stored separately from user configuration with mode 0600 and atomically rotated. Tokens must never appear in logs, diagnostics, configuration exports, or issues.

A granted session is restored silently at startup from the saved token. If that token is gone or revoked, Witticism does not silently re-pop the system dialog; it falls back to clipboard and asks the user to re-enable auto-paste from the tray. If authorization is denied or disconnected, transcription continues and remains on the clipboard. The transcript intentionally remains on the clipboard after auto-paste; delayed clipboard restoration is unreliable across toolkits.

GNOME inhibits new Remote Desktop sessions while the desktop is locked. If a granted session cannot be restored, automatic paste remains degraded until the session is unlocked and re-enabled; shortcut capture remains independent.

## Adding an adapter

Implement the relevant contract, keep imports lazy, add selection without changing higher-level PTT semantics, provide actionable probe status, add shared contract tests, document permissions, and add the platform to release qualification. An adapter may not be marked supported using mocks alone.

## Diagnostics

`witticism-platform doctor` reports session type, desktop, portal capabilities (GlobalShortcuts and RemoteDesktop), the selected shortcut backend and its capability tier (hold-to-talk, press-to-toggle (fallback), or unavailable), whether Witticism's own GNOME custom keybinding is currently registered, the selected output backend and its tier (portal paste, typing, or clipboard), the auto-paste consent state (unset/granted/declined), the extension installed/running state, and whether a portal restore grant exists. When a session can be improved it also prints a "how to improve" line, such as the opt-in extension install hint with its logout caveat on GNOME, or the optional auto-paste hint on Wayland.

Output defaults to human-readable text; `--json` emits the machine-readable report. `doctor` degrades gracefully when D-Bus is unreachable, reporting whatever it can rather than crashing. It must not report usernames, hostnames, hardware, devices, paths, tokens, transcripts, environment dumps, or raw logs. The keybinding-registered check reports only the presence of Witticism's own entries; it never reveals the names or paths of any other custom keyboard shortcut.
