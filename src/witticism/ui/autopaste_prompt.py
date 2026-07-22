"""In-app priming for Wayland auto-paste consent.

The decision logic lives in :class:`AutopasteConsent`, a plain-Python state
machine with no Qt or D-Bus references, so it is fully unit-testable without
PyQt5. The Qt dialog (:func:`show_priming_dialog`) imports PyQt5 lazily, so this
module is importable in headless / test environments.

The flow is modeled on an in-app permission-priming screen: Witticism explains,
in its own branded dialog, what auto-paste does and that GNOME will show a
system confirmation next. Only if the user opts in do we start the portal
session (the single place GNOME's dialog may appear). Clipboard-first remains
the default until the user consents; see docs/adr/004.
"""

import logging

from witticism.platform.input_output import (
    AUTOPASTE_DECLINED,
    AUTOPASTE_GRANTED,
    AUTOPASTE_UNSET,
)

logger = logging.getLogger(__name__)

PRIMING_TITLE = "Enable automatic paste?"
PRIMING_BODY = (
    "Witticism can insert dictated text directly into the active app. "
    "If you enable this, GNOME will show a system confirmation next "
    "(it is titled \"Remote Desktop\" - the request comes from Witticism and "
    "covers keyboard input only). You can change this anytime from the tray menu."
)
PRIMING_ENABLE = "Enable automatic paste"
PRIMING_NOT_NOW = "Not now"


class AutopasteConsent:
    """Plain-Python state machine for the Wayland auto-paste consent flow.

    All state is read from / written to a config manager (dot-keys
    ``output.autopaste`` and ``output.autopaste_prompted``). It holds no Qt or
    D-Bus references so it can be driven directly in tests.

    ``supported`` is True only where auto-paste is actually available (the
    Wayland Remote Desktop output adapter); elsewhere the feature is never
    offered.
    """

    def __init__(self, config_manager, supported=False):
        self.config = config_manager
        self.supported = bool(supported)

    def state(self):
        if self.config is None:
            return AUTOPASTE_UNSET
        return self.config.get("output.autopaste", AUTOPASTE_UNSET)

    def is_granted(self):
        return self.state() == AUTOPASTE_GRANTED

    def already_prompted(self):
        if self.config is None:
            return False
        return bool(self.config.get("output.autopaste_prompted", False))

    def can_offer(self):
        """Whether offering auto-paste is meaningful at all right now.

        True on a supported (Wayland) session when consent has not been granted;
        drives visibility of the manual "Enable automatic paste..." tray item.
        """
        return self.supported and self.state() != AUTOPASTE_GRANTED

    def should_auto_prompt(self):
        """Whether to show the priming dialog automatically.

        Only on a supported session, only while consent is still unset, and only
        if it has never been shown before. "Declined" and "granted" both stop it.
        """
        return (
            self.supported
            and self.state() == AUTOPASTE_UNSET
            and not self.already_prompted()
        )

    def mark_prompted(self):
        if self.config is not None:
            self.config.set("output.autopaste_prompted", True)

    def decline(self):
        """User chose "Not now": remember it and never auto-prompt again."""
        self.mark_prompted()
        if self.config is not None:
            self.config.set("output.autopaste", AUTOPASTE_DECLINED)

    def grant(self):
        """Portal consent succeeded: persist the granted state."""
        self.mark_prompted()
        if self.config is not None:
            self.config.set("output.autopaste", AUTOPASTE_GRANTED)


def show_priming_dialog(parent=None):
    """Show the in-app priming dialog and return True if the user opted in.

    PyQt5 is imported lazily so this module stays importable without Qt.
    """
    from PyQt5.QtWidgets import QMessageBox

    box = QMessageBox(parent)
    box.setWindowTitle("Witticism")
    box.setIcon(QMessageBox.Question)
    box.setText(PRIMING_TITLE)
    box.setInformativeText(PRIMING_BODY)
    enable_button = box.addButton(PRIMING_ENABLE, QMessageBox.AcceptRole)
    box.addButton(PRIMING_NOT_NOW, QMessageBox.RejectRole)
    box.setDefaultButton(enable_button)
    box.exec_()
    return box.clickedButton() is enable_button
