"""route: local — native file I/O handlers (zero deps, stdlib only).

Each handler returns a dict ``{"ok": bool, ...}`` so the agent loop can feed
the result back into the next turn as an observation. No external CLI is
required: these are pure-Python stdlib operations usable when the Claude Code
CLI is unavailable.
"""
from __future__ import annotations

import os
import shlex
import subprocess


def local_read_file(path: str) -> dict:
    """Read a file's contents.

    Returns ``{"ok": True, "content": str, "path": str}`` or
    ``{"ok": False, "error": str, "path": str}`` if it is missing or unreadable.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as exc:
        return {"ok": False, "error": str(exc), "path": path}
    return {"ok": True, "content": content, "path": path}


def local_write_file(path: str, content: str, mkdir: bool = True) -> dict:
    """Write ``content`` to ``path``, creating intermediate dirs when ``mkdir``.

    Returns ``{"ok": True, "path": str, "bytes": int}`` or
    ``{"ok": False, "error": str, "path": str}``.
    """
    try:
        if mkdir:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            n = f.write(content)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "path": path}
    return {"ok": True, "path": path, "bytes": n}


def local_append_file(path: str, content: str) -> dict:
    """Append ``content`` to ``path``, creating it if missing.

    Returns ``{"ok": True, "path": str, "bytes_appended": int}`` or
    ``{"ok": False, "error": str, "path": str}``.
    """
    try:
        with open(path, "a", encoding="utf-8") as f:
            n = f.write(content)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "path": path}
    return {"ok": True, "path": path, "bytes_appended": n}


def local_list_dir(path: str) -> dict:
    """List entries (names only) in a directory.

    Returns ``{"ok": True, "path": str, "entries": list[str]}`` or
    ``{"ok": False, "error": str}``.
    """
    try:
        entries = sorted(os.listdir(path))
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "path": path, "entries": entries}


def _split_command(command: str) -> list[str]:
    """Split a command string into argv, correctly on both POSIX and Windows.

    POSIX-mode :func:`shlex.split` treats backslashes as escape characters, so
    on Windows a path like ``C:\\Python\\python.exe`` is mangled to
    ``C:Pythonpython.exe`` and the process is not found. On Windows we split in
    non-POSIX mode (which preserves backslashes) and then strip the surrounding
    quotes that non-POSIX mode leaves on quoted tokens.
    """
    if os.name == "nt":
        tokens = shlex.split(command, posix=False)
        out: list[str] = []
        for t in tokens:
            if len(t) >= 2 and t[0] == t[-1] and t[0] in ('"', "'"):
                t = t[1:-1]
            out.append(t)
        return out
    return shlex.split(command)


def local_run_command(command, cwd: str | None = None, timeout: int = 30) -> dict:
    """Run a command in a subprocess (``shell=False``).

    ``command`` may be a string (split with :func:`_split_command`, which is
    backslash-safe on Windows) or a list. Returns
    ``{"ok": True, "stdout": str, "stderr": str, "returncode": int}`` on exit
    code 0, otherwise ``{"ok": False, "error": str, "returncode": int}`` (with
    stdout/stderr included). Transport/timeout failures yield
    ``{"ok": False, "error": str, "returncode": None}``.
    """
    try:
        if isinstance(command, str):
            argv = _split_command(command)
        else:
            argv = list(command)
        proc = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            # Decode as UTF-8 with replacement: the default locale codec
            # (cp1252 on Windows) crashes the subprocess reader thread on the
            # non-cp1252 bytes that LLM-generated test output routinely contains.
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {"ok": False, "error": str(exc), "returncode": None}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "returncode": None}
    result = {
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "returncode": proc.returncode,
    }
    if proc.returncode == 0:
        return {"ok": True, **result}
    return {"ok": False, "error": f"exit code {proc.returncode}", **result}