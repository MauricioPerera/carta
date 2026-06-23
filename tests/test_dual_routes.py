"""Tests T10 — Dual execution routes (mcp + rest) en OKF."""
from __future__ import annotations

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AGENTS = os.path.join(_REPO_ROOT, "agents")
if _AGENTS not in sys.path:
    sys.path.insert(0, _AGENTS)

from tool_selector import _parse_frontmatter  # noqa: E402

_N8N_TOOLS = os.path.join(_REPO_ROOT, "okf", "n8n", "tools")
_JP = os.path.join(_REPO_ROOT, "okf", "jsonplaceholder")


def _frontmatter(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        text = f.read()
    fm, _body = _parse_frontmatter(text)
    return fm


def _md_files(d: str) -> list[str]:
    return [
        os.path.join(d, n)
        for n in sorted(os.listdir(d))
        if n.endswith(".md")
    ]


def test_n8n_tools_have_route():
    """Every doc under okf/n8n/tools/ has a route field in its frontmatter."""
    files = _md_files(_N8N_TOOLS)
    assert files, "no se encontraron tool docs en okf/n8n/tools"
    missing = []
    bad = []
    for p in files:
        fm = _frontmatter(p)
        r = fm.get("route")
        if "route" not in fm:
            missing.append(os.path.basename(p))
        elif r not in ("mcp", "rest"):
            bad.append((os.path.basename(p), r))
    assert not missing, f"docs missing route field: {missing}"
    assert not bad, f"docs with invalid route: {bad}"
    # The 5 tools marked as mcp must be exactly those.
    mcp = {
        os.path.basename(p)[:-3]
        for p in files
        if _frontmatter(p).get("route") == "mcp"
    }
    expected_mcp = {
        "validate_workflow",
        "search_nodes",
        "get_node_types",
        "get_suggested_nodes",
        "get_sdk_reference",
    }
    assert mcp == expected_mcp, f"tools mcp esperadas {expected_mcp}, got {mcp}"
    print(f"OK test_n8n_tools_have_route: {len(files)} tools, {len(mcp)} mcp + {len(files)-len(mcp)} rest")


def test_jsonplaceholder_all_rest():
    """Every doc under okf/jsonplaceholder/ (index, tools, skills) has route=rest."""
    all_md = []
    for sub in ("", "tools", "skills"):
        d = os.path.join(_JP, sub) if sub else _JP
        if os.path.isdir(d):
            all_md += _md_files(d)
    assert all_md, "no se encontraron docs en okf/jsonplaceholder"
    non_rest = []
    no_route = []
    for p in all_md:
        fm = _frontmatter(p)
        if "route" not in fm:
            no_route.append(os.path.relpath(p, _JP))
        elif fm.get("route") != "rest":
            non_rest.append((os.path.relpath(p, _JP), fm.get("route")))
    assert no_route == [], f"docs sin route: {no_route}"
    assert non_rest == [], f"docs with route != rest: {non_rest}"
    print(f"OK test_jsonplaceholder_all_rest: {len(all_md)} docs todos route=rest")


def test_okf_sha_different_providers():
    """compute_dir_sha('okf/n8n') != compute_dir_sha('okf/jsonplaceholder')."""
    from postal import compute_dir_sha
    sha_n8n = compute_dir_sha(os.path.join(_REPO_ROOT, "okf", "n8n"))
    sha_jp = compute_dir_sha(os.path.join(_REPO_ROOT, "okf", "jsonplaceholder"))
    assert sha_n8n != sha_jp, f"dos proveedores distintos comparten sha: {sha_n8n}"
    print(f"OK test_okf_sha_different_providers: n8n={sha_n8n[:12]} jp={sha_jp[:12]}")


if __name__ == "__main__":
    test_n8n_tools_have_route()
    test_jsonplaceholder_all_rest()
    test_okf_sha_different_providers()
    print("\nTODOS LOS TESTS OK")