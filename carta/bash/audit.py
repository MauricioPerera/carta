"""AuditLog — records each bash execution in .bash_audit/."""
from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


class AuditLog:
    """Persists audit entries per Bash execution."""

    def __init__(self, repo_path: str = ".", enabled: bool = True):
        self.repo_path = Path(repo_path)
        self.enabled = enabled
        self._dir = self.repo_path / ".bash_audit"

    def record(
        self,
        command: str,
        result: dict,
        okf_sha: str | None = None,
        ccdd_sha: str | None = None,
    ) -> dict:
        """Builds and saves an audit entry; returns it."""
        if not self.enabled:
            return {}

        entry_id = uuid.uuid4().hex
        timestamp = datetime.now(timezone.utc).isoformat()
        stdout_preview = (result.get("stdout") or "")[:200]

        entry = {
            "id": entry_id,
            "timestamp_iso": timestamp,
            "command": command,
            "exit_code": result.get("exit_code"),
            "okf_sha": okf_sha,
            "ccdd_sha": ccdd_sha,
            "stdout_preview": stdout_preview,
        }

        self._dir.mkdir(parents=True, exist_ok=True)
        (self._dir / f"{entry_id}.json").write_text(
            json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return entry

    def list_entries(self) -> list[dict]:
        """Lists all entries sorted by timestamp ascending."""
        if not self._dir.exists():
            return []
        entries = []
        for f in self._dir.glob("*.json"):
            try:
                entries.append(json.loads(f.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                continue
        entries.sort(key=lambda e: e.get("timestamp_iso", ""))
        return entries