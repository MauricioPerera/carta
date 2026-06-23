"""Tests for carta.staleness — runtime catalog-vs-spec drift check.

No network. The fetcher is injected via lambda in every case.
"""
import hashlib
import os

import pytest

from carta import CartaClient
from carta.openapi_to_okf import generate
from carta.staleness import check_catalog

_SPEC_BYTES = b'SPECBYTES'
_SPEC_SHA = hashlib.sha256(_SPEC_BYTES).hexdigest()
_SOURCE_SPEC = 'http://x/spec.json'


def _make_catalog(tmp_path):
    """Generate a tiny catalog stamped with fixed source_spec provenance."""
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "S", "version": "1"},
        "servers": [{"url": "https://api.x.com"}],
        "paths": {
            "/items": {
                "get": {"operationId": "listItems", "summary": "list"},
            }
        },
    }
    out_dir = str(tmp_path / "catalog")
    generate(
        spec,
        out_dir,
        timestamp="2026-06-23T00:00:00Z",
        source_spec=_SOURCE_SPEC,
        source_spec_sha=_SPEC_SHA,
    )
    return out_dir


def test_fresh(tmp_path):
    catalog = _make_catalog(tmp_path)
    res = check_catalog(catalog, fetcher=lambda u: _SPEC_BYTES)
    assert res["status"] == "fresh", res
    assert res["expected_sha"] == _SPEC_SHA
    assert res["actual_sha"] == _SPEC_SHA
    assert res["source_spec"] == _SOURCE_SPEC


def test_stale(tmp_path):
    catalog = _make_catalog(tmp_path)
    res = check_catalog(catalog, fetcher=lambda u: b'CHANGED')
    assert res["status"] == "stale", res
    assert res["expected_sha"] == _SPEC_SHA
    assert res["actual_sha"] != res["expected_sha"]


def test_unknown(tmp_path):
    """A hand-made catalog (okf/n8n) has no source_spec provenance."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    n8n = os.path.join(repo_root, "okf", "n8n")
    res = check_catalog(n8n, fetcher=lambda u: b'whatever')
    assert res["status"] == "unknown", res
    assert "source_spec" in res.get("reason", "")


def test_unreachable(tmp_path):
    catalog = _make_catalog(tmp_path)

    def _boom(url):
        raise OSError("no such host")

    res = check_catalog(catalog, fetcher=_boom)
    assert res["status"] == "unreachable", res
    assert "no such host" in res["error"]
    assert res["source_spec"] == _SOURCE_SPEC


def test_client_check_freshness(tmp_path):
    """CartaClient.check_freshness resolves the catalog and matches check_catalog."""
    catalog = _make_catalog(tmp_path)
    client = CartaClient([catalog])

    fresh = client.check_freshness(fetcher=lambda u: _SPEC_BYTES)
    assert fresh["status"] == "fresh", fresh

    stale = client.check_freshness(fetcher=lambda u: b'CHANGED')
    assert stale["status"] == "stale", stale

    # Same answer as the standalone function over the same dir.
    direct = check_catalog(catalog, fetcher=lambda u: b'CHANGED')
    assert direct == stale


if __name__ == "__main__":
    pytest.main([__file__, "-v"])