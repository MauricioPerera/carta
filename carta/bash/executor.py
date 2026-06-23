"""Bash executor — orchestrates allowlist, sandbox, audit, and persistent shell state."""
from __future__ import annotations

import os
import re

from .audit import AuditLog
from .allowlist import Allowlist
from .filesystem import SharedFilesystem
from .sandbox import Sandbox

_EXPORT_RE = re.compile(
    r"""(?:^|;|\s|\|&&|\|\||\n)\s*export\s+([A-Za-z_][A-Za-z0-9_]*)=(\S+)"""
)


class Bash:
    """Runs bash commands with allowlist, sandbox, audit, and persistent env."""

    def __init__(
        self,
        workdir: SharedFilesystem | None = None,
        allowlist: Allowlist | None = None,
        audit: AuditLog | None = None,
        shared_env: dict | None = None,
        timeout: int = 30,
        max_output: int = 65536,
    ):
        self.workdir = workdir if workdir is not None else SharedFilesystem()
        self.allowlist = allowlist
        self.audit = audit
        self.shared_env: dict[str, str] = dict(shared_env) if shared_env else {}
        self.defined_commands: dict[str, str] = {}
        self.sandbox = Sandbox(timeout=timeout, max_output=max_output)

    def _build_env(self) -> dict:
        """Copies os.environ and applies shared_env on top."""
        env = os.environ.copy()
        env.update({k: str(v) for k, v in self.shared_env.items()})
        return env

    def _build_command(self, command: str) -> str:
        """Prepends bash function definitions for the defined aliases."""
        if not self.defined_commands:
            return command
        prelude_lines = []
        for name, script in self.defined_commands.items():
            body = script.rstrip()
            prelude_lines.append(f"{name}() {{ {body} \"$@\"; }}")
            prelude_lines.append(f"export -f {name}")
        prelude = "\n".join(prelude_lines)
        return f"{prelude}\n{command}"

    def _capture_exports(self, command: str) -> None:
        """Updates shared_env with the command's `export VAR=val` statements."""
        for match in _EXPORT_RE.finditer(command):
            var, val = match.group(1), match.group(2)
            val = val.strip("'\"")
            self.shared_env[var] = val

    def exec(self, command: str, okf_sha: str | None = None, ccdd_sha: str | None = None) -> dict:
        # 1. allowlist
        if self.allowlist is not None:
            ok, motivo = self.allowlist.check_command(command)
            if not ok:
                return {
                    "stdout": "",
                    "stderr": motivo,
                    "exit_code": 1,
                    "blocked": True,
                    "timed_out": False,
                    "audit_id": None,
                }

        # 2. sandbox.run
        full_cmd = self._build_command(command)
        result = self.sandbox.run(
            full_cmd, env=self._build_env(), cwd=self.workdir.path(".")
        )

        # 3. audit
        audit_id = None
        if self.audit is not None:
            entry = self.audit.record(command, result, okf_sha=okf_sha, ccdd_sha=ccdd_sha)
            audit_id = entry.get("id") if entry else None

        # 4. persist the command's exports
        self._capture_exports(command)

        return {
            "stdout": result["stdout"],
            "stderr": result["stderr"],
            "exit_code": result["exit_code"],
            "blocked": False,
            "timed_out": result["timed_out"],
            "audit_id": audit_id,
        }

    def define_command(self, name: str, script: str) -> None:
        """Registers an alias as a bash function; injected before each exec."""
        self.defined_commands[name] = script