"""
AlertSink is the seam for real delivery later (Slack/email/PagerDuty) --
LogAlertSink is the only implementation for now. Same "seam real, delivery
mechanism deferred" pattern as ExternalPositionSource/MarkPriceSource.
Fired by LiveRunner only on a False->True halt transition (edge-triggered),
never on every cycle while already halted.
"""

from __future__ import annotations
import logging
from typing import Optional, Protocol


class AlertSink(Protocol):
    def send(self, message: str) -> None: ...


class LogAlertSink:
    def __init__(self, logger_: Optional[logging.Logger] = None):
        self._logger = logger_ or logging.getLogger("bot.orchestration.alerts")

    def send(self, message: str) -> None:
        self._logger.critical(message)
