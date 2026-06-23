"""Tests for the selection eval harness (offline, no network)."""
import hashlib

from carta.scorers import bm25_rank, keyword_rank, make_embedding_rank
from carta.eval.run_eval import load_labels, run_eval


def test_eval_runs_offline():
    """keyword + bm25 over the real labels: sane metrics, no network."""
    scorers = {'keyword': keyword_rank, 'bm25': bm25_rank}
    res = run_eval(scorers)
    assert set(res.keys()) == {'keyword', 'bm25'}
    n = len(load_labels())
    for name, m in res.items():
        assert m['n'] == n
        assert 0.0 <= m['recall'] <= 1.0
        assert 0.0 <= m['hit_rate'] <= 1.0


def test_eval_embedding_mock():
    """Deterministic mock embed_fn: embedding scorer runs without network."""
    def mock_embed(texts):
        out = []
        for t in texts:
            h = hashlib.sha256(t.encode('utf-8')).digest()
            # 8 floats per text, deterministic and non-zero in general.
            vec = [(b / 255.0) - 0.5 for b in h[:8]]
            out.append(vec)
        return out

    rank = make_embedding_rank(mock_embed)
    scorers = {'keyword': keyword_rank, 'bm25': bm25_rank, 'embedding': rank}
    res = run_eval(scorers)
    assert 'embedding' in res
    n = len(load_labels())
    assert res['embedding']['n'] == n
    assert 0.0 <= res['embedding']['recall'] <= 1.0
    assert 0.0 <= res['embedding']['hit_rate'] <= 1.0