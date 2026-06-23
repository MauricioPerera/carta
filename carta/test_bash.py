"""Bash adapter tests (just-bash port a Python)."""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

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


def test_define_command(bash):
    bash.define_command("greet", "echo hello ")
    res = bash.exec("greet world")
    assert "hello world" in res["stdout"]
    assert res["exit_code"] == 0