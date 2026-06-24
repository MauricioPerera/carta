"""Tests for T29: route: local — native file I/O handlers in :mod:`carta.local`.

Covers read/write/append/list/run_command plus the parseability of the OKF
docs in ``carta/okf/local/``. Uses ``tmp_path`` for filesystem isolation and
``sys.executable`` for portable subprocess tests.
"""
from __future__ import annotations

import os
import sys

from carta.local import (
    _split_command,
    local_append_file,
    local_list_dir,
    local_read_file,
    local_run_command,
    local_write_file,
)

_OKF_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "okf", "local")


# --------------------------------------------------------------------------- #
# read_file
# --------------------------------------------------------------------------- #
def test_read_file_ok(tmp_path):
    p = tmp_path / "sample.txt"
    p.write_text("hello local", encoding="utf-8")
    r = local_read_file(str(p))
    assert r["ok"] is True
    assert r["content"] == "hello local"
    assert r["path"] == str(p)


def test_read_file_missing(tmp_path):
    r = local_read_file(str(tmp_path / "nope.txt"))
    assert r["ok"] is False
    assert "error" in r


# --------------------------------------------------------------------------- #
# write_file
# --------------------------------------------------------------------------- #
def test_write_file_creates_dirs(tmp_path):
    p = tmp_path / "sub" / "deep" / "out.txt"
    r = local_write_file(str(p), "payload")
    assert r["ok"] is True
    assert p.is_file()
    assert p.read_text(encoding="utf-8") == "payload"


def test_write_file_content(tmp_path):
    p = tmp_path / "out.txt"
    local_write_file(str(p), "abc")
    assert local_read_file(str(p))["content"] == "abc"


# --------------------------------------------------------------------------- #
# append_file
# --------------------------------------------------------------------------- #
def test_append_file(tmp_path):
    p = tmp_path / "log.txt"
    p.write_text("line1\n", encoding="utf-8")
    r = local_append_file(str(p), "line2\n")
    assert r["ok"] is True
    assert p.read_text(encoding="utf-8") == "line1\nline2\n"


def test_append_file_creates(tmp_path):
    p = tmp_path / "new.txt"
    local_append_file(str(p), "first\n")
    assert p.read_text(encoding="utf-8") == "first\n"


# --------------------------------------------------------------------------- #
# list_dir
# --------------------------------------------------------------------------- #
def test_list_dir_ok(tmp_path):
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    (tmp_path / "b.txt").write_text("y", encoding="utf-8")
    r = local_list_dir(str(tmp_path))
    assert r["ok"] is True
    assert set(r["entries"]) == {"a.txt", "b.txt"}


def test_list_dir_missing(tmp_path):
    r = local_list_dir(str(tmp_path / "missing"))
    assert r["ok"] is False


# --------------------------------------------------------------------------- #
# run_command
# --------------------------------------------------------------------------- #
def test_run_command_ok():
    r = local_run_command([sys.executable, "-c", "print('hello')"])
    assert r["ok"] is True
    assert r["returncode"] == 0
    assert "hello" in r["stdout"]


def test_run_command_fail():
    r = local_run_command([sys.executable, "-c", "import sys; sys.exit(1)"])
    assert r["ok"] is False
    assert r["returncode"] == 1


def test_run_command_handles_non_ascii_output():
    """Subprocess output with non-cp1252 bytes must not crash the reader thread.

    Regression: text=True without encoding uses the locale codec (cp1252 on
    Windows), which raised UnicodeDecodeError on LLM-generated output. We force
    UTF-8 with replacement so capture never crashes.
    """
    # Child writes raw UTF-8 bytes for ✓ (U+2713) to stdout. cp1252 decode of
    # byte 0xE2/0x9C/0x93 would crash the reader thread; utf-8 must succeed.
    r = local_run_command(
        [
            sys.executable,
            "-c",
            "import sys; sys.stdout.buffer.write('done \\u2713\\n'.encode('utf-8'))",
        ]
    )
    assert r["ok"] is True, r
    assert "done" in r["stdout"]


def test_split_command_simple():
    assert _split_command("python -m pytest tests/ -q") == [
        "python",
        "-m",
        "pytest",
        "tests/",
        "-q",
    ]


def test_split_command_preserves_backslashes():
    """On Windows, backslash paths must survive splitting (regression guard).

    POSIX-mode shlex would mangle ``C:\\Py\\python.exe`` to ``C:Pypython.exe``.
    """
    parts = _split_command(r"C:\Py\python.exe script.py")
    if os.name == "nt":
        assert parts == [r"C:\Py\python.exe", "script.py"]
    else:
        # POSIX shells legitimately treat backslashes as escapes.
        assert parts[-1] == "script.py"


def test_split_command_strips_quotes_on_windows():
    parts = _split_command('cmd "arg with spaces"')
    assert parts[0] == "cmd"
    assert parts[1] == "arg with spaces"


def test_run_command_string_executable_path_windows():
    """On Windows, a string command with the backslash interpreter path runs.

    Regression guard for WinError 2: passing sys.executable (an absolute path
    with backslashes) inside a string command previously failed because
    POSIX-mode shlex ate the backslashes. POSIX cannot exercise this — backslash
    paths are legitimately escapes there — so the assertion is Windows-only.
    """
    if os.name != "nt":
        return
    r = local_run_command(sys.executable + " -c \"print('ok')\"")
    assert r["ok"] is True, r
    assert "ok" in r["stdout"]


# --------------------------------------------------------------------------- #
# OKF docs
# --------------------------------------------------------------------------- #
def test_local_okf_docs_parseable():
    files = sorted(
        f for f in os.listdir(_OKF_DIR) if f.endswith(".md")
    )
    assert files, f"no .md in {_OKF_DIR}"
    from carta.selector import _parse_frontmatter

    for fname in files:
        with open(os.path.join(_OKF_DIR, fname), "r", encoding="utf-8") as f:
            text = f.read()
        assert text.startswith("---"), f"{fname} missing frontmatter"
        fm, _body = _parse_frontmatter(text)
        assert fm.get("route") == "local", f"{fname} route != local: {fm}"


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])