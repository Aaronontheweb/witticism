# ADR-004: GNOME Custom-Keybinding Press-to-Toggle and Consent-Gated Automatic Typing

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

ADR-002 delivered Wayland automatic typing by opening a keyboard-only Remote Desktop
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

### 2. Keep automatic typing, but strictly consent-gate it behind in-app priming

Automatic typing via the Remote Desktop portal is retained but is **off by default**
and never touches the portal - no probe, no session, no dialog - until the user
explicitly opts in. Clipboard-first is now the **designed** Wayland output:
transcripts are copied to the clipboard for a plain `Ctrl+V`, with no permission
prompt at any point unless the user asks for more.

Consent is captured through an in-app priming dialog modeled on the
permission-priming pattern (an app-branded screen that explains what will happen
before the OS prompt appears; cf. Handy's PR #689). Witticism's own dialog
explains what automatic typing does and warns that GNOME will show a system
confirmation titled "Remote Desktop" that actually comes from Witticism and
covers keyboard input only. It is offered **at most once**, automatically, right
after the first successful transcription (the value moment - the user's text
just landed on the clipboard), never at startup; and it is always reachable
manually from the tray ("Enable automatic typing..."). Only if the user opts in
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
  automatic typing. Automatic typing, when enabled, works exactly as before (persisted
  restore token, keyboard-only, keysym typing).
- The alternative of deleting automatic typing entirely was considered and rejected:
  the capability is valuable; only its unsolicited startup choreography was the
  problem.

This ADR supersedes the GrabAccelerator fallback and the startup Remote Desktop
session described in ADR-002; the adapter contracts, shortcut-identifier-only
extension bridge, and portal token isolation from ADR-002 are otherwise
unchanged.

## Addendum: hold-to-talk via key-repeat inference

Live testing revealed that gnome-settings-daemon fires the custom-shortcut
command on **every key auto-repeat** while the key is held, not just once. On
the target machine (repeat delay 500ms, interval 30ms, from
`org.gnome.desktop.peripherals.keyboard`), holding F9 produced a stream of
`TriggerShortcut` calls that flipped recording on and off every ~270-480ms
through the press-to-toggle debounce - a blocker, because users hold F9 out of
push-to-talk muscle memory.

The same behavior is the fix. The repeat stream is a release detector: a tap is
a single event; a hold is one event, a ~`delay` gap, then events every
~`interval` until release. So the keybinding adapter now **synthesizes true
hold-to-talk** on GNOME 46/47:

- At start it reads `repeat`, `delay`, and `repeat-interval` from
  `org.gnome.desktop.peripherals.keyboard` (defaults: repeat=true, delay=500ms,
  interval=30ms).
- **When key repeat is enabled** (the normal case) it advertises
  `supports_hold = True`. A per-binding tracker emits ACTIVATED on the first
  event of a stream, swallows the repeats, and emits DEACTIVATED once the stream
  goes quiet: it arms a `delay + 4*interval + 100ms` timer on the first event
  (long enough to bridge the first-repeat gap, which equals `delay`) and re-arms
  a `4*interval + 100ms` timer on each subsequent event. A held key therefore
  produces one ACTIVATED at press and one DEACTIVATED ~`4*interval + 100ms`
  after release. Tap (ACTIVATE) bindings such as mode-switch emit ACTIVATED once
  per stream and swallow the repeats. The tracker runs entirely on the async
  runtime loop, so all state stays single-threaded.
- **When key repeat is disabled** (rare) no repeats occur, so it keeps
  `supports_hold = False` and press-to-toggle via the hotkey manager.

Trade-offs, stated honestly: release is detected ~`4*interval + 100ms` after the
key is let go (~220ms with defaults); a hold shorter than `delay` cannot be
distinguished from a tap and reads as a brief push-to-talk burst (the same
effective UX as tapping the old X11 PTT key); and each repeat spawns a
short-lived `gdbus` process on the gnome-settings-daemon side (unavoidable,
cheap). The optional GNOME Shell extension remains the path to exact,
repeat-independent release timing, and the only hold-to-talk path for users who
disable key repeat.

## Addendum: mid-session automatic typing revocation

Live testing also found that turning automatic typing off from GNOME's system
remote-desktop indicator closed our portal session silently - the adapter did
not notice, so automatic typing died and never re-prompted. The adapter now subscribes
to the portal session's `org.freedesktop.portal.Session.Closed` signal. On
closure it drops to clipboard (DEGRADED), clears the dead session, resets
`output.autopaste` to `unset`, and deletes the restore token, so re-enabling
runs the full priming + portal flow again and the tray's "Enable automatic
typing..." offer reappears (the tray re-evaluates that item's visibility each
time the menu opens). A typing injection that fails because the session
vanished just before its `Closed` signal arrives degrades the same way without
raising; the transcript is copied to the clipboard before typing is attempted, so
it is never lost.

## Addendum: automatic typing instead of a Ctrl+V paste chord

Live testing found that synthesizing a Ctrl+V chord to "paste" the transcript
fails exactly where the owner dictates most - terminals. Terminals paste on
Ctrl+Shift+V, and a bare Ctrl+V inside a shell (or tmux) is quoted-insert:
nothing appears and the next keystroke is swallowed. The X11 path never had this
problem because it *types* characters, which works everywhere.

So after consent is granted, the Remote Desktop portal path now types the
transcript itself instead of pasting: for each character it sends an X11 keysym
press then release via `NotifyKeyboardKeysym`. Printable ASCII (0x20-0x7E) maps
to its own codepoint; any other codepoint uses the Unicode keysym range
(0x01000000 + codepoint); newline maps to Return and tab to Tab. Keysyms carry
case and symbols, so no shift/modifier is synthesized. The clipboard copy still
happens first as a safety net (the user can Ctrl+Shift+V manually if anything
fails), and the fire-and-forget structure, failure-degrades-to-clipboard path,
and Session.Closed handling are unchanged.

The consent and permission model is untouched - same keyboard-only session, same
portal dialog, same restore token. Only what happens after "granted" changed.
The feature is now honestly named **automatic typing** throughout the UI and
diagnostics (this is literally what the OS request grants). The config key
remains `output.autopaste` for historical reasons; renaming it would churn users'
saved consent for no benefit.

## Addendum: tray health indicator for degraded platform integration

A silently broken automatic-typing session (or an unusable hotkey) is as bad as
a model-load failure, so it must change the tray icon, not just show a transient
toast. A **degraded** health tier sits below real errors and above normal: it
badges the idle icon amber and annotates the tooltip and Status row with a short
reason. It triggers when the hotkey adapter is not usable (at startup or after a
rebind) or when automatic typing was granted but is now broken (revocation or a
startup token-restore failure). It explicitly does not trigger for the designed
clipboard default (consent unset/declined) or the working press-to-toggle
fallback. Precedence, high to low: real errors (CUDA/GPU, model load) > the live
recording indicator > degraded > normal idle, so a recording still flashes and
the badge returns when idle. The decision lives in a pure, Qt-free helper
(`compute_tray_health`) so the trigger/clear/precedence matrix is unit-testable
without PyQt5.
