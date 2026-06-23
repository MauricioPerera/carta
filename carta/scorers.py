"""T18: Pluggable scorers for the OKF selector.

A *scorer* is any callable with the signature::

    rank(query: str, docs: list[dict]) -> list[float]

returning one score per doc, in the same order as ``docs``. The default
keyword scorer (:func:`keyword_rank`) is an exact reimplementation of
:func:`carta.selector.score_doc` applied over a list, so swapping it in
preserves the historical behaviour of :func:`carta.selector.select_tools`.

Additional scorers:

* :func:`bm25_rank` — classic Okapi BM25 (k1=1.5, b=0.75), stdlib only.
* :func:`make_embedding_rank` — builds a cosine-similarity ranker over an
  injected embedding function, with per-document caching keyed by
  :func:`carta.selector.doc_sha` so unchanged docs are never re-embedded.
* :func:`openai_embed_fn` — an ``embed_fn`` backed by a local OpenAI-compatible
  ``/embeddings`` endpoint, via ``urllib`` (lazy, no hard dependency).
"""
import json
import math
import os
import re

from .selector import doc_sha, score_doc, _tokenize


# ---------------------------------------------------------------------------
# Shared doc text
# ---------------------------------------------------------------------------

def _doc_text(doc):
    """Concatenate the searchable text of a doc.

    Mirrors the fields ``score_doc`` looks at (title / description /
    when_to_use / tags / content) so BM25 and the embedding ranker operate
    over the same surface as the keyword scorer.
    """
    fm = doc.get('frontmatter', {}) or {}
    parts = [
        str(fm.get('title', '') or ''),
        str(fm.get('description', '') or ''),
        str(fm.get('when_to_use', '') or ''),
    ]
    tags = fm.get('tags', []) or []
    parts.append(' '.join(str(t) for t in tags))
    parts.append(doc.get('content', '') or '')
    return '\n'.join(parts)


# ---------------------------------------------------------------------------
# Keyword scorer (default, exact replica of score_doc)
# ---------------------------------------------------------------------------

def keyword_rank(query, docs):
    """Return ``score_doc(doc, query)`` for each doc, preserving order.

    This is the default scorer: it reuses :func:`carta.selector.score_doc`
    verbatim, so the historical keyword behaviour is unchanged when a
    caller swaps ``scorer=keyword_rank`` into :func:`select_tools`.
    """
    return [float(score_doc(d, query)) for d in docs]


# ---------------------------------------------------------------------------
# BM25 scorer (stdlib only)
# ---------------------------------------------------------------------------

def _bm25_idf(n_docs, df):
    """Lucene-style smoothed BM25 idf (always non-negative)."""
    return math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))


def bm25_rank(query, docs, k1=1.5, b=0.75):
    """Okapi BM25 (k1=1.5, b=0.75) over ``_doc_text`` of each doc.

    Tokenization is lowercase split on non-alphanumeric runs (same rule as
    :func:`carta.selector._tokenize`). Pure stdlib, deterministic.
    """
    n_docs = len(docs)
    if n_docs == 0:
        return []

    q_tokens = _tokenize(query)
    if not q_tokens:
        return [0.0] * n_docs

    tokenized = [_tokenize(_doc_text(d)) for d in docs]
    doc_lens = [len(toks) for toks in tokenized]
    avgdl = (sum(doc_lens) / n_docs) if n_docs else 0.0

    # Document frequency per unique query term.
    q_terms = set(q_tokens)
    df = {}
    for term in q_terms:
        df[term] = sum(1 for toks in tokenized if term in set(toks))

    idf = {term: _bm25_idf(n_docs, df[term]) for term in q_terms}

    # Term frequency per doc.
    tfs = []
    for toks in tokenized:
        counts = {}
        for t in toks:
            counts[t] = counts.get(t, 0) + 1
        tfs.append(counts)

    scores = []
    for i in range(n_docs):
        s = 0.0
        tf_i = tfs[i]
        dl = doc_lens[i] or 0
        denom_norm = (1.0 - b + b * (dl / avgdl)) if avgdl else (1.0 - b)
        for term in q_terms:
            f = tf_i.get(term, 0)
            if not f:
                continue
            num = f * (k1 + 1.0)
            den = f + k1 * denom_norm
            s += idf[term] * (num / den if den else 0.0)
        scores.append(float(s))
    return scores


# ---------------------------------------------------------------------------
# Embedding scorer (injectable embed_fn, per-doc cache keyed by doc_sha)
# ---------------------------------------------------------------------------

def cosine(a, b):
    """Cosine similarity of two equal-length numeric vectors (stdlib)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def _cache_key(doc):
    """Stable per-doc key: ``doc_sha(path)`` when a path exists, else a
    sha of the in-memory content so pathless docs still cache sanely."""
    path = doc.get('path')
    if path:
        try:
            return doc_sha(path)
        except OSError:
            pass
    import hashlib
    return hashlib.sha256((doc.get('content', '') or '').encode('utf-8')).hexdigest()


def _load_cache(cache):
    """Resolve a cache spec into a mutable dict.

    ``None``  -> no caching (returns ``None``).
    ``dict``  -> used in memory, returned as-is.
    ``str``   -> path to a JSON file ``{sha: vector}`` (created on demand).
    """
    if cache is None:
        return None
    if isinstance(cache, dict):
        return cache
    if isinstance(cache, str):
        if os.path.exists(cache):
            try:
                with open(cache, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (OSError, ValueError):
                return {}
        return {}
    return None


def _save_cache(cache_spec, data):
    """Persist ``data`` back to disk only when ``cache_spec`` is a path."""
    if isinstance(cache_spec, str):
        with open(cache_spec, 'w', encoding='utf-8') as f:
            json.dump(data, f)


def make_embedding_rank(embed_fn, cache=None):
    """Build a cosine-similarity ranker over an injected ``embed_fn``.

    ``embed_fn(texts: list[str]) -> list[list[float]]`` is supplied by the
    caller (e.g. :func:`openai_embed_fn` or a mock in tests). The returned
    ``rank(query, docs)``:

    * embeds the query and ``_doc_text`` of every doc,
    * scores each doc by ``cosine_similarity(query_vec, doc_vec)``,
    * caches doc vectors per-doc, keyed by ``doc_sha(doc['path'])`` (so a
      doc whose file did not change is never re-embedded across calls),
    * only sends the *new/changed* docs to ``embed_fn`` in one batch.

    ``cache`` may be ``None`` (no caching), an in-memory ``dict``, or a path
    to a JSON file ``{sha: vector}`` that is loaded on entry and persisted
    after each call.
    """
    def rank(query, docs):
        if not docs:
            return []
        store = _load_cache(cache)

        # Resolve each doc's vector: cache hit, or mark for batch embedding.
        keys = [_cache_key(d) for d in docs]
        vecs = [None] * len(docs)
        missing_idx = []
        missing_texts = []
        for i, key in enumerate(keys):
            if store is not None and key in store:
                vecs[i] = store[key]
                continue
            missing_idx.append(i)
            missing_texts.append(_doc_text(docs[i]))

        # Embed only the new/changed docs (plus the query, never cached).
        if missing_texts:
            new_vecs = embed_fn(missing_texts)
            for idx, vec in zip(missing_idx, new_vecs):
                vecs[idx] = vec
                if store is not None:
                    store[keys[idx]] = vec
        if store is not None:
            _save_cache(cache, store)

        # Query vector is computed every call.
        q_vec = embed_fn([query])[0]

        return [float(cosine(q_vec, v)) for v in vecs]

    return rank


def openai_embed_fn(base_url='http://localhost:1234/v1',
                    model='text-embedding-embeddinggemma-300m',
                    timeout=60.0):
    """Return an ``embed_fn`` backed by an OpenAI-compatible endpoint.

    Uses ``urllib`` (stdlib) lazily, so importing :mod:`carta` never pulls
    in network code. The returned callable POSTs to ``{base_url}/embeddings``
    with ``{"model": model, "input": texts}`` and returns
    ``[data[i].embedding for i in ...]`` in input order.
    """
    def embed_fn(texts):
        if not texts:
            return []
        import json as _json
        import urllib.request as _r
        url = base_url.rstrip('/') + '/embeddings'
        payload = _json.dumps({'model': model, 'input': list(texts)}).encode('utf-8')
        req = _r.Request(url, data=payload, headers={'Content-Type': 'application/json'})
        with _r.urlopen(req, timeout=timeout) as resp:
            raw = _json.loads(resp.read().decode('utf-8'))
        out = [None] * len(texts)
        for item in raw.get('data', []):
            idx = item.get('index')
            if idx is not None and 0 <= idx < len(texts):
                out[idx] = item['embedding']
        return out
    return embed_fn