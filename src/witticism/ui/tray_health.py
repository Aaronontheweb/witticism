"""Pure decision logic for the tray icon's health tier.

The tray icon must visibly reflect platform-integration health: a silently
broken automatic-typing session (or an unusable hotkey) is as bad as a model
load failure, so it must change the icon, not just show a transient toast.

This module holds only the decision (no Qt), so the precedence/trigger/clear
matrix is unit-testable without PyQt5. The Qt side renders the returned tier.

Precedence (high -> low):
    ERROR (real errors: CUDA/GPU, model load) - rendered by existing code
  > RECORDING (live indicator) - must keep flashing, masks degraded
  > DEGRADED (platform integration broken)
  > NORMAL (idle)

DEGRADED triggers:
  - the hotkey adapter is not usable (FAILED/UNAVAILABLE), or
  - automatic typing was granted but is now broken (mid-session revocation or a
    startup token-restore failure), unless the user has since declined.

Explicitly NOT degraded: clipboard-only because consent is unset/declined (the
designed default the user chose) and the press-to-toggle fallback (working, a
lesser tier already covered by its own notification).
"""

from enum import Enum

HOTKEY_REASON = "hotkey unavailable"
AUTOTYPE_REASON = "automatic typing stopped working (open menu to re-enable)"


class TrayHealth(Enum):
    NORMAL = "normal"
    DEGRADED = "degraded"
    RECORDING = "recording"
    ERROR = "error"


def compute_tray_health(hotkey_usable, autopaste_state, autopaste_broken, error_active, recording):
    """Return ``(TrayHealth, reason_or_None)`` for the current state.

    ``autopaste_state`` is the consent state ("unset"/"granted"/"declined");
    ``autopaste_broken`` is the sticky "was working, now isn't" flag. A user who
    declined after a revocation has chosen the clipboard default, so that clears
    the degraded state even if the broken flag lingers.
    """
    if error_active:
        return TrayHealth.ERROR, None
    if recording:
        return TrayHealth.RECORDING, None
    if not hotkey_usable:
        return TrayHealth.DEGRADED, HOTKEY_REASON
    if autopaste_broken and autopaste_state != "declined":
        return TrayHealth.DEGRADED, AUTOTYPE_REASON
    return TrayHealth.NORMAL, None
