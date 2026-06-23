"""T18: tests for pluggable scorers (pytest, no network)."""
import os

from carta.scorers import (
    keyword_rank,
    bm25_rank,
    make_embedding_rank,
    cosine,
)
from carta.selector import select_tools, load_okf_index, doc_sha

OKF = os.path.join(os.path.dirname(__file__), '..', 'okf', 'n8n')


def _names(docs):
    return [d['name'] for d in docs]


def test_keyword_rank_matches_default():
    idx = load_okf_index(OKF)
    docs = idx['skills'] + idx['tools']
    create_doc = next(d for d in docs if d['name'] == 'create-workflow')
    scores = keyword_rank('create workflow webhook', docs)
    # Same length and order.
    assert len(scores) == len(docs)
    # The create-workflow doc scores > 0.
    i = docs.index(create_doc)
    assert scores[i] > 0, f"create-workflow scored {scores[i]}"
    print("OK test_keyword_rank_matches_default: create-workflow ->", scores[i])


def test_bm25_ranks_relevant_high():
    idx = load_okf_index(OKF)
    docs = idx['skills'] + idx['tools']
    scores = bm25_rank('create workflow', docs)
    ranked = sorted(zip(scores, docs), key=lambda x: x[0], reverse=True)
    top3_names = [d['name'] for _s, d in ranked[:3]]
    assert ('create-workflow' in top3_names
            or 'create_workflow_from_code' in top3_names), \
        f"relevant doc not in top-3: {top3_names}"
    print("OK test_bm25_ranks_relevant_high: top-3 ->", top3_names)


def test_embedding_rank_with_mock():
    """Deterministic mock embed_fn; no network."""
    def mock_embed(texts):
        out = []
        for t in texts:
            t_low = t.lower()
            out.append([
                float(t_low.count('create')),
                float(t_low.count('webhook')),
                float(len(t) % 7),
            ])
        return out

    rank = make_embedding_rank(mock_embed)
    idx = load_okf_index(OKF)
    docs = idx['skills'] + idx['tools']
    scores = rank('create', docs)
    assert len(scores) == len(docs)
    # The doc whose text contains the most 'create' should rank highest for
    # a query that is literally 'create'.
    ranked = sorted(zip(scores, docs), key=lambda x: x[0], reverse=True)
    top = ranked[0][1]
    # Count 'create' occurrences in the top doc's searchable text.
    from carta.scorers import _doc_text
    top_count = _doc_text(top).lower().count('create')
    # At least one doc scored > 0 and the winner contains 'create'.
    assert ranked[0][0] > 0
    assert top_count > 0, f"top doc {top['name']} has no 'create'"
    print("OK test_embedding_rank_with_mock: top ->", top['name'], ranked[0][0])


def test_embedding_cache_by_doc_sha(tmp_path):
    """Second run re-embeds only the query; a changed doc is re-embedded."""
    calls = {'n': 0, 'texts': 0}

    def counting_embed(texts):
        calls['n'] += 1
        calls['texts'] += len(texts)
        out = []
        for t in texts:
            t_low = t.lower()
            out.append([
                float(t_low.count('create')),
                float(t_low.count('webhook')),
                float(len(t) % 7),
            ])
        return out

    # Build a tiny in-memory catalog so we can mutate one doc's content.
    base_skills = load_okf_index(OKF)['skills'][:3]
    docs = [dict(d) for d in base_skills]  # copy; keep original path

    cache = {}
    rank = make_embedding_rank(counting_embed, cache=cache)

    before = (calls['n'], calls['texts'])
    rank('create', docs)
    first_run = calls['texts'] - before[1]  # query + all docs (none cached)

    # Cache should now hold one vector per doc (3 docs).
    assert len(cache) == 3, f"cache should have 3 entries, got {len(cache)}"

    before = (calls['n'], calls['texts'])
    rank('create', docs)
    second_run = calls['texts'] - before[1]
    # Only the query is embedded on the second run.
    assert second_run == 1, f"second run embedded {second_run} texts, expected 1"

    # Mutate one doc's content (in-memory) AND point its path at a tmp file
    # so doc_sha changes — that doc must be re-embedded.
    changed = dict(docs[0])
    tmp = tmp_path / 'changed.md'
    tmp.write_text('brand new content about create workflows', encoding='utf-8')
    changed['path'] = str(tmp)
    changed['content'] = tmp.read_text(encoding='utf-8')
    new_docs = [changed] + docs[1:]

    old_sha = list(cache.keys())
    before = (calls['n'], calls['texts'])
    rank('create', new_docs)
    third_run = calls['texts'] - before[1]
    # query + the one changed doc.
    assert third_run == 2, f"third run embedded {third_run} texts, expected 2"
    # A new cache key appeared (the changed doc's sha).
    assert any(k not in old_sha for k in cache.keys())
    print("OK test_embedding_cache_by_doc_sha: "
          f"runs={first_run},{second_run},{third_run}")


def test_select_tools_with_scorer():
    docs = select_tools('create workflow webhook',
                        okf_path=OKF, scorer=bm25_rank)
    assert docs, "no docs returned"
    assert 'create-workflow' in _names(docs), \
        f"missing create-workflow: {_names(docs)}"
    print("OK test_select_tools_with_scorer:", _names(docs))


if __name__ == '__main__':
    test_keyword_rank_matches_default()
    test_bm25_ranks_relevant_high()
    test_embedding_rank_with_mock()
    import tempfile
    d = tempfile.mkdtemp()
    test_embedding_cache_by_doc_sha(type('P', (), {'__truediv__': lambda self, x: os.path.join(d, x)})())
    test_select_tools_with_scorer()
    print("\nALL SCORER TESTS OK")