"""OpenAPI -> OKF catalog generator.

Reads an OpenAPI 3.0 spec (JSON or YAML) and emits an OKF catalog of
``route: rest`` tool docs (one per operation) plus an ``index.md``.

The output frontmatter is serialized in the same style as the hand-written
catalogs under ``okf/`` (single-quoted strings, inline ``[a, b]`` lists) so
the generated docs are indistinguishable from manual ones and consumable
directly by :mod:`agents.tool_selector`.

CLI::

    python carta/openapi_to_okf.py <spec.json|yaml> <out_dir>
"""
from __future__ import annotations

import json
import os
import re
import sys

# PyYAML is a declared runtime dependency (requirements.txt). The import is
# kept inside load_spec so ``import carta.openapi_to_okf`` does not hard-fail
# in environments where YAML support is the only missing piece.


# --------------------------------------------------------------------------- IO
def load_spec(path: str) -> dict:
    """Load an OpenAPI spec from a JSON or YAML file.

    Picks the parser by extension: ``.json`` uses the stdlib, ``.yaml``/``.yml``
    use PyYAML.
    """
    ext = os.path.splitext(path)[1].lower()
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    if ext == ".json":
        return json.loads(raw)
    if ext in (".yaml", ".yml"):
        import yaml  # declared dependency

        return yaml.safe_load(raw)
    # Fall back: try JSON then YAML.
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        import yaml

        return yaml.safe_load(raw)


# -------------------------------------------------------------- serialization
def _sq(value: str) -> str:
    """Wrap a string in single quotes, doubling any embedded single quote."""
    return "'" + str(value).replace("'", "''") + "'"


def _dump_fm(pairs: list[tuple[str, object]]) -> str:
    """Serialize an ordered list of (key, value) pairs as YAML frontmatter.

    Strings -> single-quoted; lists -> inline ``['a', 'b']``; everything else
    (ints, bools, None) via ``str()``. Matches the style of ``okf/*/tools/*.md``.
    """
    lines = []
    for key, value in pairs:
        if value is None:
            lines.append(f"{key}: ''")
        elif isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
        elif isinstance(value, list):
            if not value:
                lines.append(f"{key}: []")
            else:
                inner = ", ".join(_sq(v) for v in value)
                lines.append(f"{key}: [{inner}]")
        elif isinstance(value, (int, float)):
            lines.append(f"{key}: {value}")
        else:
            lines.append(f"{key}: {_sq(value)}")
    return "\n".join(lines)


# --------------------------------------------------------------- helpers
def _slug(path: str) -> str:
    """Slugify a path into a safe tool-name fragment.

    Strips a leading ``/``, replaces ``/{...}`` segments and any non
    alphanumeric run with ``_``.
    """
    s = path.lstrip("/")
    s = re.sub(r"\{[^}]*\}", "_", s)
    s = re.sub(r"[^0-9a-zA-Z]+", "_", s)
    s = s.strip("_")
    return s or "root"


def _tool_name(method: str, path: str, operation: dict) -> str:
    op_id = operation.get("operationId")
    if op_id:
        return re.sub(r"[^0-9a-zA-Z_]+", "_", str(op_id)).strip("_") or f"{method}_{_slug(path)}"
    return f"{method}_{_slug(path)}"


def _base_url(spec: dict) -> str:
    servers = spec.get("servers") or []
    if servers and isinstance(servers[0], dict):
        return servers[0].get("url", "") or ""
    return ""


def _resolve_ref(spec: dict, ref: str) -> dict:
    """Resolve a local ``$ref`` (``#/components/schemas/Foo``) against ``spec``."""
    if not isinstance(ref, str) or not ref.startswith("#/"):
        return {}
    node: object = spec
    for part in ref.lstrip("#/").split("/"):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return {}
    return node if isinstance(node, dict) else {}


def _json_body_schema(operation: dict, spec: dict) -> dict | None:
    """Return the application/json request body schema, resolving ``$ref``."""
    rb = operation.get("requestBody")
    if not isinstance(rb, dict):
        return None
    content = rb.get("content") or {}
    media = content.get("application/json")
    if not isinstance(media, dict):
        # Fall back to the first media type if application/json is absent.
        if not content:
            return None
        media = next(iter(content.values()))
        if not isinstance(media, dict):
            return None
    schema = media.get("schema")
    if not isinstance(schema, dict):
        return None
    if "$ref" in schema:
        schema = _resolve_ref(spec, schema["$ref"])
    return schema or None


def _placeholder(prop_schema: dict) -> str:
    """A simple placeholder value for a property type (for curl examples)."""
    t = prop_schema.get("type")
    if t == "integer":
        return "1"
    if t == "number":
        return "1.0"
    if t == "boolean":
        return "true"
    if t == "array":
        return "[]"
    if t == "object":
        return "{}"
    return "value"


# --------------------------------------------------------------- generation
def generate(spec: dict, out_dir: str, timestamp: str = "2026-01-01T00:00:00Z") -> dict:
    """Generate an OKF catalog from an OpenAPI spec.

    Creates ``out_dir/tools/<toolname>.md`` per operation and
    ``out_dir/index.md``. Returns ``{'tools': [names], 'index': path,
    'out_dir': out_dir}``.
    """
    base_url = _base_url(spec)
    tools_dir = os.path.join(out_dir, "tools")
    os.makedirs(tools_dir, exist_ok=True)

    tool_names: list[str] = []
    index_entries: list[dict] = []

    paths = spec.get("paths") or {}
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method in ("get", "post", "put", "patch", "delete"):
            operation = path_item.get(method)
            if not isinstance(operation, dict):
                continue
            name = _tool_name(method, path, operation)
            tool_names.append(name)
            _write_tool_md(tools_dir, name, method, path, operation, spec, base_url, timestamp)
            index_entries.append({
                "name": name,
                "endpoint": f"{method.upper()} {base_url}{path}",
                "summary": _description(operation, method, path),
            })

    index_path = _write_index_md(out_dir, spec, base_url, index_entries, timestamp)
    return {"tools": tool_names, "index": index_path, "out_dir": out_dir}


def _description(operation: dict, method: str, path: str) -> str:
    return (
        operation.get("summary")
        or operation.get("description")
        or f"{method} {path}"
    )


def _when_to_use(operation: dict, method: str, path: str) -> str:
    return operation.get("description") or operation.get("summary") or ""


def _write_tool_md(
    tools_dir: str,
    name: str,
    method: str,
    path: str,
    operation: dict,
    spec: dict,
    base_url: str,
    timestamp: str,
) -> None:
    method_upper = method.upper()
    endpoint = f"{method_upper} {base_url}{path}"
    description = _description(operation, method, path)
    when_to_use = _when_to_use(operation, method, path)
    tags = operation.get("tags") or []

    fm = _dump_fm([
        ("type", "REST Tool"),
        ("title", name),
        ("route", "rest"),
        ("endpoint", endpoint),
        ("description", description),
        ("when_to_use", when_to_use),
        ("tags", list(tags)),
        ("timestamp", timestamp),
    ])

    # ---- Parameters section
    param_lines: list[str] = []
    for p in operation.get("parameters") or []:
        if not isinstance(p, dict):
            continue
        pname = p.get("name", "?")
        pin = p.get("in", "?")
        required = p.get("required", False)
        pdesc = p.get("description", "")
        req = "required" if required else "optional"
        line = f"- {pname} ({pin}, {req})"
        if pdesc:
            line += f": {pdesc}"
        param_lines.append(line)

    body_schema = _json_body_schema(operation, spec)
    body_props: list[tuple[str, dict]] = []
    if body_schema:
        props = body_schema.get("properties") or {}
        if isinstance(props, dict):
            for pname, pschema in props.items():
                body_props.append((pname, pschema if isinstance(pschema, dict) else {}))
            for pname, pschema in body_props:
                t = pschema.get("type", "string")
                pdesc = pschema.get("description", "")
                line = f"- {pname}: {t}"
                if pdesc:
                    line += f" — {pdesc}"
                param_lines.append(line)

    # ---- Example section (curl)
    url = f"{base_url}{path}"
    curl_parts = [f"curl -X {method_upper} {url}"]
    has_body = bool(body_props)
    if has_body:
        curl_parts.append("-H 'Content-Type: application/json'")
        body_obj = ", ".join(
            f'"{pname}":{_placeholder(pschema)}' for pname, pschema in body_props
        )
        curl_parts.append(f"-d '{{{body_obj}}}'")
    curl = " \\\n  ".join(curl_parts)

    body = []
    body.append(f"# {name}")
    body.append("")
    body.append("## Parameters")
    if param_lines:
        body.extend(param_lines)
    else:
        body.append("- (none)")
    body.append("")
    body.append("## Example")
    body.append("```")
    body.append(curl)
    body.append("```")
    body.append("")

    content = f"---\n{fm}\n---\n" + "\n".join(body)
    with open(os.path.join(tools_dir, f"{name}.md"), "w", encoding="utf-8") as f:
        f.write(content)


def _write_index_md(
    out_dir: str,
    spec: dict,
    base_url: str,
    entries: list[dict],
    timestamp: str,
) -> str:
    info = spec.get("info") or {}
    title = info.get("title", "Generated API")
    description = info.get("description", "")

    fm = _dump_fm([
        ("type", "API Index"),
        ("title", title),
        ("description", description),
        ("base_url", base_url),
        ("route", "rest"),
        ("tags", ["rest", "generated"]),
        ("timestamp", timestamp),
    ])

    lines = [f"# {title}", ""]
    if description:
        lines.append(description)
        lines.append("")
    lines.append(f"## Tools ({len(entries)})")
    lines.append("")
    for e in entries:
        lines.append(f"- [{e['name']}](tools/{e['name']}.md) — {e['endpoint']}")
    lines.append("")

    content = f"---\n{fm}\n---\n" + "\n".join(lines)
    index_path = os.path.join(out_dir, "index.md")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(content)
    return index_path


# ----------------------------------------------------------------------- CLI
def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: python carta/openapi_to_okf.py <spec.json|yaml> <out_dir>")
        return 2
    spec_path, out_dir = argv[1], argv[2]
    spec = load_spec(spec_path)
    result = generate(spec, out_dir)
    print(f"generated {len(result['tools'])} tools -> {result['out_dir']}/tools/")
    print(f"index: {result['index']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))