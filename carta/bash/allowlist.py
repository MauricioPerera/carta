"""Allowlist — which commands and URLs are permitted."""
from __future__ import annotations

import os
import re
from pathlib import Path

import yaml


class Allowlist:
    """Controls permitted commands and URLs for the bash sandbox."""

    def __init__(
        self,
        allowed_commands: list[str] | None = None,
        allowed_urls: list[str] | None = None,
        timeout: int = 30,
    ):
        self.allowed_commands = (
            list(allowed_commands) if allowed_commands is not None else None
        )
        self.allowed_urls = list(allowed_urls) if allowed_urls is not None else []
        self.timeout = timeout

    @classmethod
    def load_from_ccdd(cls, ccdd_path: str) -> "Allowlist":
        """Reads .ccdd/agent-a.yaml and extracts the execution block."""
        path = Path(ccdd_path)
        if path.is_dir():
            path = path / "agent-a.yaml"
        if not path.exists():
            raise FileNotFoundError(f"ccdd config not found: {path}")

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        exec_block = data.get("execution") or {}
        return cls(
            allowed_commands=exec_block.get("allowed_commands"),
            allowed_urls=exec_block.get("allowed_urls") or [],
            timeout=exec_block.get("timeout", 30),
        )

    def check_command(self, command: str) -> tuple[bool, str]:
        """True if the first token is in allowed_commands.

        allowed_commands None => everything permitted.
        """
        if self.allowed_commands is None:
            return True, "allowlist disabled: everything permitted"
        tokens = command.strip().split()
        if not tokens:
            return False, "empty command"
        first = os.path.basename(tokens[0].strip("'\""))
        if first in self.allowed_commands:
            return True, f"command '{first}' permitted"
        return False, f"command '{first}' is NOT in the allowlist"

    def check_url(self, url: str) -> tuple[bool, str]:
        """True if the URL starts with some prefix in allowed_urls.

        allowed_urls empty => everything permitted.
        """
        if not self.allowed_urls:
            return True, "URL allowlist empty: everything permitted"
        for prefix in self.allowed_urls:
            if url.startswith(prefix):
                return True, f"URL matches prefix '{prefix}'"
        return False, f"URL '{url}' does not match any permitted prefix"

    @staticmethod
    def check_injection(command: str) -> tuple[bool, str]:
        """True if the command contains no shell substitution constructs.

        Global guard: blocks $(...) and backtick command substitution.
        """
        if re.search(r'\$\(', command):
            return False, 'command substitution blocked: $(...) detected'
        if re.search(r'`', command):
            return False, 'command substitution blocked: backtick detected'
        return True, 'ok'