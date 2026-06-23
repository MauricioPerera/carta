"""SharedFilesystem — tempdir persisted across exec calls."""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path


class SharedFilesystem:
    """Working directory that persists across Bash.exec invocations."""

    def __init__(self, base_dir: str | None = None):
        self._owns_dir = base_dir is None
        if base_dir is None:
            self._base = Path(tempfile.mkdtemp(prefix="okf_bash_"))
        else:
            self._base = Path(base_dir).resolve()
            self._base.mkdir(parents=True, exist_ok=True)

    def path(self, relative: str) -> str:
        """Absolute path within the filesystem for a given relative path."""
        # Normalize '..' to prevent escaping the base_dir.
        rel = Path(relative)
        if rel.is_absolute():
            raise ValueError(f"absolute path not allowed: {relative}")
        return str((self._base / rel).resolve())

    def exists(self, relative: str) -> bool:
        return Path(self.path(relative)).exists()

    def read(self, relative: str) -> str:
        p = Path(self.path(relative))
        return p.read_text(encoding="utf-8")

    def write(self, relative: str, content: str) -> None:
        p = Path(self.path(relative))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    def cleanup(self) -> None:
        """Removes the tempdir only if it was created internally."""
        if self._owns_dir and self._base.exists():
            shutil.rmtree(self._base, ignore_errors=True)
            self._owns_dir = False

    @property
    def base_dir(self) -> str:
        return str(self._base)