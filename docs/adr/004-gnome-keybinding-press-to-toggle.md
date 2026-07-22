# ADR-004: GNOME Custom-Keybinding Press-to-Toggle and Consent-Gated Auto-Paste

**Status:** Accepted

**Date:** 2026-07-21

## Context

ADR-002 established the platform adapter contracts. Two of its choices for GNOME
Wayland (sessions without the GlobalShortcuts portal, i.e. GNOME 46/47) did not
survive contact with a real target machine.

### The `org.gnome.Shell.GrabAccelerator` fallback cannot work

ADR-002/ADR-003 made the no-setup shortcut default an
`org.gnome.Shell.GrabAccelerator`-based grab. Live testing on GNOME Shell 46
(Ubuntu, Wayland) showed this can never work for a third-party app: since GNOME
Shell 41, `org.gnome.Shell.GrabAccelerator` is guarded behind a D-Bus sender
allowlist of GNOME's own components. The method is still visible in
introspection, so it looks callable, but every call from outside that allowlist
is rejected. From the app it surfaced as:

> `[PLATFORM_ADAPTER] GNOME Shell GrabAccelerator failed: GrabAccelerator is not allowed`

A direct `gdbus` call returns `Access denied`. There is no flag or permission a
third-party app can request to be added to the allowlist; the API is simply not
available to us on any GNOME >= 41.

### The startup Remote Desktop permission dialog is unacceptable UX

ADR-002 delivered Wayland auto-paste by opening a keyboard-only Remote Desktop
portal session at startup. On GNOME that pops the system "Remote Desktop"
permission dialog. That dialog was implemented and then **rejected by the
project owner**: a dictation app cold-popping GNOME's bare, unattributed "Allow
remote interaction" dialog the moment it launches is scary and confusing,
regardless of the fact that the request is technically keyboard-only and
sanctioned by the portal. The problem is choreography, not capability - a
zero-context system prompt at startup reads like malware, not a feature.

## Decision

### 1. Register a standard GNOME custom keyboard shortcut for press-to-toggle

Replace the GrabAccelerator fallback with `GnomeKeybindingShortcutAdapter`. On
GNOME Wayland without the GlobalShortcuts portal and without the optional
extension, Witticism registers an ordinary **GNOME custom keyboard shortcut** -
exactly the kind a user creates by hand in **Settings > Keyboard > Custom
Shortcuts**. The shortcut's command asks Witticism, over its own session-bus
name (`com.stannardlabs.Witticism`, method
`com.stannardlabs.Witticism.Control.TriggerShortcut`), to trigger the bound
action. It is registered through `gsettings` on the standard
`org.gnome.settings-daemon.plugins.media-keys` schema.

This is deliberately **not** OS-level integration and injects no code into the
compositor. The entry is visible and editable in GNOME Settings, requires no
logout, and is removed when Witticism exits. It is registered automatically at
adapter start because binding the configured hotkey is the app's core,
advertised function - the same reason a hotkey app configures a hotkey. This
contrasts with the GNOME Shell **extension** of ADR-003, which runs code inside
the compositor, observes keyboard events, and therefore remains strictly opt-in.

A custom shortcut only ever delivers a key-press (never a release), so this
backend is press-to-toggle: press once to start recording, press again to stop.
The optional GNOME Shell extension remains the upgrade path to true
hold-to-talk.

The adapter preserves every existing user keybinding when appending or removing
its own entries. If the current `custom-keybindings` list is non-empty and
cannot be parsed, it refuses to modify it rather than risk clobbering the user's
shortcuts. Leftover `witticism-*` entries from a crashed run are cleaned up at
the next start.

### 2. Keep auto-paste, but strictly consent-gate it behind in-app priming

Auto-paste via the Remote Desktop portal is retained but is **off by default**
and never touches the portal - no probe, no session, no dialog - until the user
explicitly opts in. Clipboard-first is now the **designed** Wayland output:
transcripts are copied to the clipboard for a plain `Ctrl+V`, with no permission
prompt at any point unless the user asks for more.

Consent is captured through an in-app priming dialog modeled on the
permission-priming pattern (an app-branded screen that explains what will happen
before the OS prompt appears; cf. Handy's PR #689). Witticism's own dialog
explains what auto-paste does and warns that GNOME will show a system
confirmation titled "Remote Desktop" that actually comes from Witticism and
covers keyboard input only. It is offered **at most once**, automatically, right
after the first successful transcription (the value moment - the user's text
just landed on the clipboard), never at startup; and it is always reachable
manually from the tray ("Enable automatic paste..."). Only if the user opts in
does Witticism start the portal session - the single place GNOME's dialog may
appear.

Consent state (`output.autopaste`: `unset` | `granted` | `declined`) is
persisted. A granted session is restored silently at startup using the persisted
restore token; if that token is gone or revoked, Witticism falls back to
clipboard and asks the user to re-enable from the tray, rather than silently
re-popping the system dialog. The opaque restore token remains isolated,
0600 state and never appears in diagnostics or logs.

## Consequences

- GNOME 46/47 Wayland gets a working press-to-toggle hotkey out of the box, with
  no install and no logout, using a mechanism the user can see and edit in GNOME
  Settings.
- `gnome-settings-daemon` must be running for the custom shortcut to fire (it is,
  in every standard GNOME session). Each press spawns a short-lived `gdbus`
  call, adding roughly tens of milliseconds of latency per activation - fine for
  toggle semantics.
- A crash can leave `witticism-*` custom-keybinding entries behind; they are
  cleaned at the next start and removed on a clean exit.
- Wayland users see **no** permission prompt unless they deliberately enable
  auto-paste. Auto-paste, when enabled, works exactly as before (persisted
  restore token, keyboard-only, `Ctrl+V` injection).
- The alternative of deleting auto-paste entirely was considered and rejected:
  the capability is valuable; only its unsolicited startup choreography was the
  problem.

This ADR supersedes the GrabAccelerator fallback and the startup Remote Desktop
session described in ADR-002; the adapter contracts, shortcut-identifier-only
extension bridge, and portal token isolation from ADR-002 are otherwise
unchanged.
