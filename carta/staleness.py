"""Runtime staleness check — detect catalog-vs-spec drift.

A checked-out OKF catalog is a snapshot: if the upstream OpenAPI spec
changes and nobody regenerates the catalog, an agent silently runs against
obsolete instructions. This module compares the ``source_spec_sha`` stamped
into ``index.md`` (by :mod:`carta.openapi_to_okf`) against the SHA-256 of
the spec bytes fetched live from ``source_spec``.

Honest limits
-------------
- Detects drift **catalog-vs-spec**, not **spec-vs-reality**: the spec
  itself may lag the running service. A 'fresh' result means the catalog
  matches the spec, not that the spec matches the world.
- Requires ``source_spec`` to be fetchable (a URL the ``fetcher`` can
  reach). Catalogs without provenance (e.g. hand-written ones) return
  ``'unknown'``.
- Costs one opt-in network call. The default offline behavior of
  :mod:`carta.client` is unchanged; nothing here runs automatically.

CLI::

    python -m carta.staleness <catalog_dir>

Exit codes: 0 fresh|unknown, 1 stale, 2 unreachable.
"""
from __future__ import annotations

import hashlib
import os
import sys


def _default_fetcher(url: str) -> bytes:
    """Fetch ``url`` and return its raw bytes via urllib (stdlib, 20s timeout).

    The import is lazy so ``import carta.staleness`` never touches the
    network stack until a fetch is actually requested.
    """
    from urllib.request import urlopen

    with urlopen(url, timeout=20) as resp:  # noqa: S310 (caller-controlled URL)
        return resp.read()


def _read_index_frontmatter(catalog_dir: str) -> dict:
    """Read ``catalog_dir/index.md`` and return its parsed frontmatter dict.

    Reuses :func:`carta.selector._parse_frontmatter` when available so the
    exact same parser as the rest of the package is applied; falls back to
    a small ``yaml.safe_load`` of the ``---`` block otherwise. Returns ``{}``
    when the file has no frontmatter.
    """
    index_path = os.path.join(catalog_dir, "index.md")
    with open(index_path, "r", encoding="utf-8") as f:
        text = f.read()
    try:
        from carta.selector import _parse_frontmatter

        fm, _body = _parse_frontmatter(text)
        return fm or {}
    except Exception:  # pragma: no cover - defensive fallback
        if text.startswith("---"):
            end = text.find("\n---", 3)
            if end != -1:
                import yaml

                return yaml.safe_load(text[3:end]) or {}
        return {}


def check_catalog(catalog_dir: str, fetcher=None) -> dict:
    """Check whether the catalog at ``catalog_dir`` is fresh vs its spec.

    Returns a dict with a ``status`` key that is one of:

    - ``'fresh'``      — recorded SHA matches the fetched spec's SHA.
    - ``'stale'``      — recorded and fetched SHAs differ (drift detected).
    - ``'unknown'``    — catalog has no ``source_spec`` provenance.
    - ``'unreachable'``— the fetcher raised; ``error`` carries the message.

    ``fetcher`` is an optional ``(url) -> bytes`` callable; defaults to
    :func:`_default_fetcher` (urllib, 20s timeout). Injecting it keeps the
    tests off the network.
    """
    fm = _read_index_frontmatter(catalog_dir)
    source_spec = fm.get("source_spec") or ""
    expected_sha = fm.get("source_spec_sha") or ""
    if not source_spec or not expected_sha:
        return {
            "status": "unknown",
            "reason": "catalog has no source_spec provenance",
        }

    fetch = fetcher or _default_fetcher
    try:
        data = fetch(source_spec)
    except Exception as exc:  # noqa: BLE001 (caller wants the message surfaced)
        return {
            "status": "unreachable",
            "error": str(exc),
            "source_spec": source_spec,
        }

    actual = hashlib.sha256(data).hexdigest()
    if actual == expected_sha:
        return {
            "status": "fresh",
            "source_spec": source_spec,
            "expected_sha": expected_sha,
            "actual_sha": actual,
        }
    return {
        "status": "stale",
        "source_spec": source_spec,
        "expected_sha": expected_sha,
        "actual_sha": actual,
    }


def _print_result(result: dict) -> int:
    """Print a human-readable status line; return the CLI exit code."""
    status = result.get("status")
    if status == "fresh":
        print(f"fresh: catalog matches spec ({result.get('source_spec')})")
        return 0
    if status == "stale":
        print(
            f"stale: catalog drift detected ({result.get('source_spec')}) "
            f"expected={result.get('expected_sha')} actual={result.get('actual_sha')}"
        )
        return 1
    if status == "unreachable":
        print(
            f"unreachable: {result.get('source_spec')} "
            f"error={result.get('error')}"
        )
        return 2
    # unknown (or anything else)
    print(f"unknown: {result.get('reason', 'no provenance')}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m carta.staleness <catalog_dir>")
        return 2
    return _print_result(check_catalog(argv[1]))


if __name__ == "__main__":
    sys.exit(main(sys.argv))