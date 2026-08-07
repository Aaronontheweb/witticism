import logging

from witticism.platform.input_output import create_text_output_adapter

logger = logging.getLogger(__name__)


class OutputManager:
    """Routes text through the selected platform adapter."""

    def __init__(self, output_mode: str = "type", config_manager=None, adapter=None):
        self.output_mode = output_mode
        self.config_manager = config_manager
        self.adapter = adapter or create_text_output_adapter(config_manager)
        self.status = self.adapter.start()
        logger.info(
            "OutputManager initialized: mode=%s, backend=%s, state=%s",
            output_mode, self.status.backend, self.status.state.value,
        )

    def autopaste_supported(self) -> bool:
        """Whether the active output adapter can offer consent-gated automatic typing.

        True only for the Wayland Remote Desktop adapter; elsewhere (typing,
        forced clipboard, macOS) the feature is never offered.
        """
        return hasattr(self.adapter, "request_autopaste")

    def set_autopaste_revoked_callback(self, callback) -> None:
        """Register a callback fired when automatic typing is lost mid-session (e.g.
        revoked from the system indicator). No-op if unsupported."""
        if hasattr(self.adapter, "on_revoked"):
            self.adapter.on_revoked = callback

    def request_autopaste(self, on_result=None) -> bool:
        """Ask the adapter to start a portal session (the only place GNOME's
        permission dialog may appear). Returns False if unsupported.

        ``on_result(granted: bool, message)`` is invoked when the portal flow
        resolves (on the adapter's D-Bus runtime thread)."""
        requester = getattr(self.adapter, "request_autopaste", None)
        if requester is None:
            if on_result:
                on_result(False, "Automatic typing is not available here")
            return False
        requester(on_result)
        return True

    def output_text(self, text: str) -> None:
        if not text:
            return
        result = self.adapter.copy_to_clipboard(text) if self.output_mode == "clipboard" else self.adapter.output_text(text)
        if not result.success:
            logger.error("Failed to output text: %s", result.message)
        elif result.message:
            logger.warning("Text output degraded: %s", result.message)

    def type_text(self, text: str) -> None:
        self.output_text(text)

    def copy_to_clipboard(self, text: str) -> None:
        self.adapter.copy_to_clipboard(text)

    def set_output_mode(self, mode: str) -> None:
        self.output_mode = mode
        logger.info("Output mode changed to: %s", mode)

    def cleanup(self) -> None:
        self.adapter.stop()
        logger.info("OutputManager resources released")
