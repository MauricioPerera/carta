"""Allowlist — which commands and URLs are permitted."""
from __future__ import annotations

import os
import re
import shlex
import warnings
from pathlib import Path

import yaml

# Allowing any of these is equivalent to allowing arbitrary code execution: they
# are interpreters or launchers that run whatever their arguments say
# (`python -c …`, `bash -c …`, `find -exec …`, `sudo …`). A command allowlist
# governs WHICH binary runs, not what that binary does with its arguments, so
# permitting one of these defeats the allowlist by design. We warn at config
# time rather than block — sometimes it's intentional — but the operator should
# know. (Many ordinary tools also have exec escape hatches, e.g.
# `git -c core.pager=…`; this list catches the obvious launchers, not every one.)
_INTERPRETERS = frozenset({
    "python", "python2", "python3", "bash", "sh", "zsh", "ksh", "dash", "fish",
    "perl", "ruby", "node", "nodejs", "deno", "php", "lua", "rscript",
    "env", "xargs", "find", "sudo", "doas", "timeout", "nohup", "nice",
    "setsid", "watch", "ssh", "make", "awk", "gawk", "eval", "exec",
})

# Operators that begin a new command in a shell line. The allowlist must check
# the command AFTER each of these, not just the first token — otherwise
# ``echo ok ; touch evil`` runs ``touch`` even when only ``echo`` is allowed.
_SEPARATORS = {";", "&", "&&", "||", "|", "|&", "(", ")"}
# Redirection operators. A command allowlist governs which binaries run, not
# file writes; ``curl ... > /etc/passwd`` clobbers a file without running a new
# command, so redirection is refused outright.
_REDIRECTS = {">", ">>", "<", "<<", ">|", "&>", "&>>", "2>", "2>>", "<<<"}


def _command_heads(command: str) -> "list[str] | None":
    """Return the leading word of every command in a shell line.

    Splits on control operators (``;`` ``&&`` ``||`` ``|`` ``&`` ``(`` ``)`` and
    newlines) with quote awareness via :mod:`shlex`, so chained commands are all
    surfaced. Returns ``None`` if the line cannot be parsed (unbalanced quotes)
    or if a redirection operator is present — both fail closed at the call site.
    """
    heads: list[str] = []
    for line in command.split("\n"):
        if not line.strip():
            continue
        try:
            lex = shlex.shlex(line, posix=True, punctuation_chars=True)
            lex.whitespace_split = True
            tokens = list(lex)
        except ValueError:
            return None
        expect_head = True
        for tok in tokens:
            if tok in _REDIRECTS:
                return None  # redirection not sanctioned by a command allowlist
            if tok in _SEPARATORS:
                expect_head = True
                continue
            if expect_head:
                heads.append(tok)
                expect_head = False
    return heads


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

        risky = self.interpreter_commands()
        if risky:
            warnings.warn(
                "allowlist permits interpreter/launcher command(s) "
                f"{sorted(risky)} — these run arbitrary code (e.g. "
                "`python -c …`, `bash -c …`), so the command allowlist does not "
                "constrain what they do. Allow only non-interpreter binaries for "
                "the allowlist to be a meaningful boundary.",
                stacklevel=2,
            )

    def interpreter_commands(self) -> set:
        """Allowed commands that are interpreters/launchers (arbitrary exec)."""
        if not self.allowed_commands:
            return set()
        return {
            c for c in self.allowed_commands
            if os.path.basename(c).lower() in _INTERPRETERS
        }

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
        """True only if EVERY command in the line is in allowed_commands.

        Validates each command in a chain/pipe/multi-line script — not just the
        first token — and refuses shell redirection. ``allowed_commands`` None
        => everything permitted; an empty list => everything refused.
        """
        if self.allowed_commands is None:
            return True, "allowlist disabled: everything permitted"
        heads = _command_heads(command)
        if heads is None:
            return False, (
                "command refused: unparseable or contains shell redirection"
            )
        if not heads:
            return False, "empty command"
        for head in heads:
            name = os.path.basename(head.strip("'\""))
            if name not in self.allowed_commands:
                return False, f"command '{name}' is NOT in the allowlist"
        return True, f"all {len(heads)} command(s) permitted"

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