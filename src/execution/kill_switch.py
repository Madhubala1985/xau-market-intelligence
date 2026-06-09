"""Manual kill switch (Task DEMO-001).

A file-based manual halt for supervised demo trading (23_DEMO_TRADING_RUNBOOK.md):
when the kill-switch file exists, the ExecutionGateway refuses to send anything.
The user engages it by creating the file (or calling engage()) and releases it by
deleting the file. File-based so it works from any terminal on the host without
touching the running process:

    PowerShell:  New-Item -ItemType File control\\KILL_SWITCH
    bash:        touch control/KILL_SWITCH

The file may carry a free-text reason; it is never required to. This module
performs no trading and holds no credentials.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Union

DEFAULT_KILL_SWITCH_PATH = "control/KILL_SWITCH"


class KillSwitch:
    """File-based manual halt. Engaged == the file exists."""

    def __init__(self, path: Union[str, Path] = DEFAULT_KILL_SWITCH_PATH) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def engaged(self) -> bool:
        return self._path.exists()

    def engage(self, reason: str = "") -> None:
        """Engage the kill switch (idempotent). Halts all order sending."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).isoformat()
        self._path.write_text(f"engaged_at_utc={stamp}\nreason={reason}\n", encoding="utf-8")

    def release(self) -> None:
        """Release the kill switch (idempotent)."""
        self._path.unlink(missing_ok=True)
