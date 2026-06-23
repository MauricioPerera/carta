"""Sandbox — runs a bash command with timeout and truncates output."""
from __future__ import annotations

import os
import shutil
import subprocess


def _resolve_bash() -> str:
    """Resolves the bash binary (SHELL or PATH); falls back to 'bash'."""
    shell = os.environ.get("SHELL")
    if shell and os.path.exists(shell):
        return shell
    found = shutil.which("bash")
    if found:
        return found
    return "bash"


class Sandbox:
    """Runs bash commands with a time limit and an output limit."""

    def __init__(self, timeout: int = 30, max_output: int = 65536):
        self.timeout = timeout
        self.max_output = max_output
        self._bash = _resolve_bash()

    def run(self, command: str, env: dict | None, cwd: str) -> dict:
        """Runs command with bash -c, captures stdout/stderr, and applies timeout.

        Returns {stdout, stderr, exit_code, timed_out}.
        """
        try:
            proc = subprocess.run(
                [self._bash, "-c", command],
                env=env,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            timed_out = False
            exit_code = proc.returncode
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
        except subprocess.TimeoutExpired as e:
            timed_out = True
            exit_code = 124
            stdout = (e.stdout or "") if isinstance(e.stdout, str) else ""
            stderr = (e.stderr or "") if isinstance(e.stderr, str) else ""
            stderr = (stderr + f"\nTIMEOUT after {self.timeout}s").strip()

        return {
            "stdout": self._truncate(stdout),
            "stderr": self._truncate(stderr),
            "exit_code": exit_code,
            "timed_out": timed_out,
        }

    def _truncate(self, text: str) -> str:
        if len(text) > self.max_output:
            return text[: self.max_output]
        return text