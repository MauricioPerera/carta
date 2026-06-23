"""Tests for carta.openapi_to_okf — OpenAPI -> OKF catalog generation.

No network. Builds a minimal OpenAPI 3.0 spec inline and checks the generated
docs are valid and consumable by the existing tool_selector.
"""
import os

import pytest
import yaml

from carta.openapi_to_okf import generate, load_spec  # noqa: E402
from carta.selector import load_okf_index, select_tools  # noqa: E402


def _spec() -> dict:
    """Minimal OpenAPI 3.0 spec with two operations under /items."""
    return {
        "openapi": "3.0.0",
        "info": {
            "title": "Demo API",
            "description": "A tiny demo REST API.",
            "version": "1.0.0",
        },
        "servers": [{"url": "https://api.demo.com"}],
        "paths": {
            "/items": {
                "get": {
                    "operationId": "listItems",
                    "summary": "List all items",
                    "tags": ["items"],
                    "parameters": [
                        {
                            "name": "limit",
                            "in": "query",
                            "required": False,
                            "description": "max items to return",
                            "schema": {"type": "integer"},
                        }
                    ],
                },
                "post": {
                    "operationId": "createItem",
                    "summary": "Create an item",
                    "tags": ["items"],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "qty": {"type": "integer"},
                                    },
                                }
                            }
                        }
                    },
                },
            }
        },
    }


def _parse_frontmatter(text: str) -> dict:
    assert text.startswith("---"), "missing frontmatter opener"
    end = text.find("\n---", 3)
    assert end != -1, "missing frontmatter closer"
    return yaml.safe_load(text[3:end]) or {}


def test_generate_creates_docs(tmp_path):
    result = generate(_spec(), str(tmp_path), timestamp="2026-06-22T00:00:00Z")
    assert set(result["tools"]) == {"listItems", "createItem"}
    assert os.path.exists(os.path.join(tmp_path, "tools", "listItems.md"))
    assert os.path.exists(os.path.join(tmp_path, "tools", "createItem.md"))
    assert os.path.exists(result["index"])
    assert os.path.basename(result["index"]) == "index.md"


def test_frontmatter_valid(tmp_path):
    generate(_spec(), str(tmp_path))
    for name in ("listItems", "createItem"):
        path = os.path.join(tmp_path, "tools", f"{name}.md")
        with open(path, "r", encoding="utf-8") as f:
            fm = _parse_frontmatter(f.read())
        assert fm["type"] == "REST Tool"
        assert fm["route"] == "rest"
        assert fm["title"] == name

    with open(os.path.join(tmp_path, "tools", "createItem.md"), "r", encoding="utf-8") as f:
        fm = _parse_frontmatter(f.read())
    assert fm["endpoint"].startswith("POST https://api.demo.com/items")
    assert fm["tags"] == ["items"]

    # index.md frontmatter
    with open(os.path.join(tmp_path, "index.md"), "r", encoding="utf-8") as f:
        idx_fm = _parse_frontmatter(f.read())
    assert idx_fm["type"] == "API Index"
    assert idx_fm["title"] == "Demo API"
    assert idx_fm["base_url"] == "https://api.demo.com"
    assert idx_fm["route"] == "rest"


def test_consumable_by_selector(tmp_path):
    """The generator's output must be consumable by tool_selector (e2e)."""
    generate(_spec(), str(tmp_path))
    idx = load_okf_index(str(tmp_path))
    tool_names = {t["name"] for t in idx["tools"]}
    assert tool_names == {"listItems", "createItem"}

    selected = select_tools("create item", okf_path=str(tmp_path))
    selected_names = {d["name"] for d in selected}
    assert "createItem" in selected_names


def test_curl_example_has_body(tmp_path):
    generate(_spec(), str(tmp_path))
    with open(os.path.join(tmp_path, "tools", "createItem.md"), "r", encoding="utf-8") as f:
        text = f.read()
    assert "curl -X POST" in text
    assert "-d" in text
    assert "name" in text
    assert "qty" in text


def test_load_spec_yaml(tmp_path):
    """load_spec reads YAML via PyYAML (declared dependency)."""
    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(
        "openapi: 3.0.0\n"
        "info:\n  title: Y\n  version: '1'\n"
        "paths: {}\n",
        encoding="utf-8",
    )
    spec = load_spec(str(spec_path))
    assert spec["info"]["title"] == "Y"


def test_load_spec_json(tmp_path):
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(
        '{"openapi":"3.0.0","info":{"title":"J","version":"1"},"paths":{}}',
        encoding="utf-8",
    )
    spec = load_spec(str(spec_path))
    assert spec["info"]["title"] == "J"