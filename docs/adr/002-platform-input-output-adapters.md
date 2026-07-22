# ADR-002: Platform Input and Output Adapters

**Status:** Accepted

**Date:** 2026-07-21

## Context

Witticism coupled global shortcuts and text injection directly to pynput. That works on Windows and X11, but under Wayland pynput silently selects its Xorg backend through XWayland and cannot observe global keys or inject text into native applications.

Wayland exposes these capabilities through compositor-mediated APIs. Portal support also varies: GNOME Shell 46 provides Remote Desktop but not Global Shortcuts.

## Decision

Use independent `ShortcutAdapter` and `TextOutputAdapter` contracts with automatic, visible capability selection. Preserve pynput on Windows and X11. Prefer XDG Global Shortcuts on Wayland, use a minimal GNOME Shell extension when GNOME lacks that portal, and use keyboard-only Remote Desktop portal access for clipboard-based auto-paste.

The GNOME extension forwards only configured shortcut identifiers. It does not receive transcripts or perform text insertion. Portal restore tokens are isolated, permission-restricted state and are excluded from diagnostics and logs.

The normative lifecycle, support matrix, and adapter-authoring rules live in `docs/platform-adapters.md`.

## Consequences

Witticism no longer silently treats XWayland as global keyboard support. Windows and X11 behavior remains unchanged. Wayland users see compositor permission prompts and receive clipboard fallback when a capability is denied. GNOME support carries a versioned extension maintenance cost, while other desktops can converge on standard portals.
