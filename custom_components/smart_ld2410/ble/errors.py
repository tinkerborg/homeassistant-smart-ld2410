"""Exceptions raised by the BLE transport layer."""

from __future__ import annotations


class CommandError(Exception):
    """A command's ACK reported a non-zero status."""

    def __init__(self, word: int, status: int) -> None:
        """Store the command word and status that failed."""
        self.word = word
        self.status = status
        super().__init__(f"Command 0x{word:04x} failed with status {status}")


class AuthenticationError(CommandError):
    """The bluetooth-password command was rejected by the device."""

    def __init__(self, word: int, status: int) -> None:
        """Store the command word and status, with an auth-specific message."""
        self.word = word
        self.status = status
        Exception.__init__(self, "Password rejected")
