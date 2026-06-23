"""T19: Selection eval harness (recall@5, hit-rate).

Runs the OKF selector over a labelled query set and reports, per scorer,
the mean recall@5 and the strict hit-rate (fraction of queries where ALL
expected docs were returned).

Default run is offline: only the keyword and BM25 scorers (no network).
Pass ``--embed`` to add the embedding scorer, backed by
:func:`carta.scorers.openai_embed_fn` (an OpenAI-compatible ``/embeddings``
endpoint). Embedding never runs without that flag.

CLI::

    python -m carta.eval.run_eval [--embed --base-url URL --model NAME]

The labelled set lives next to this module as ``n8n_labels.json``; each
entry is ``{"query": str, "expected": [doc-name, ...]}`` where doc-names
are the OKF doc basenames without ``.md`` (skill or tool names).
"""
import argparse
import json
import os

from ..scorers import (
    bm25_rank,
    keyword_rank,
    make_embedding_rank,
    openai_embed_fn,
)
from ..selector import select_tools

LABELS_PATH = os.path.join(os.path.dirname(__file__), 'n8n_labels.json')


def load_labels(path=None):
    """Load the labelled query set. Returns a list of ``{query, expected}``."""
    if path is None:
        path = LABELS_PATH
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def run_eval(scorers, okf_path='okf/n8n', max_docs=5, labels=None):
    """Evaluate ``scorers`` over the labelled set.

    ``scorers`` is a ``{name: rank_fn}`` map where ``rank_fn`` follows the
    :mod:`carta.scorers` signature ``rank(query, docs) -> list[float]``.

    For each query the selector returns up to ``max_docs`` docs; their
    basenames (without ``.md``) form ``selected``. Per query we record:

    * ``recall``   = |expected ∩ selected| / |expected|
    * ``hit``      = 1 iff expected ⊆ selected (strict)

    Returns ``{name: {"recall": float, "hit_rate": float, "n": int}}``.
    """
    if labels is None:
        labels = load_labels()
    results = {}
    n = len(labels)
    for name, rank_fn in scorers.items():
        recalls = []
        hits = 0
        for entry in labels:
            docs = select_tools(
                entry['query'], okf_path=okf_path,
                max_docs=max_docs, scorer=rank_fn,
            )
            selected = {d['name'] for d in docs}
            expected = set(entry['expected'])
            recall = (len(expected & selected) / len(expected)) if expected else 1.0
            recalls.append(recall)
            if expected and expected.issubset(selected):
                hits += 1
        results[name] = {
            'recall': (sum(recalls) / n) if n else 0.0,
            'hit_rate': (hits / n) if n else 0.0,
            'n': n,
        }
    return results


def build_scorers(embed=False, base_url=None, model=None):
    """Build the scorer map. Offline by default; ``embed`` adds embedding."""
    scorers = {'keyword': keyword_rank, 'bm25': bm25_rank}
    if embed:
        fn = openai_embed_fn(
            base_url=base_url or 'http://localhost:1234/v1',
            model=model or 'text-embedding-embeddinggemma-300m',
        )
        scorers['embedding'] = make_embedding_rank(fn)
    return scorers


def format_table(results):
    """Render the results as a ``scorer | recall@5 | hit-rate`` table."""
    lines = [
        f"{'scorer':<10} | {'recall@5':>8} | {'hit-rate':>8}",
        f"{'-' * 10}-+-{'-' * 8}-+-{'-' * 8}",
    ]
    for name in ('keyword', 'bm25', 'embedding'):
        if name not in results:
            continue
        m = results[name]
        lines.append(
            f"{name:<10} | {m['recall']:>8.3f} | {m['hit_rate']:>8.3f}"
        )
    return '\n'.join(lines)


def verdict_line(results):
    """One-line verdict comparing keyword vs bm25 (and embedding if present)."""
    kw = results.get('keyword', {})
    bm = results.get('bm25', {})
    parts = [f"keyword recall={kw.get('recall', 0.0):.3f} hit={kw.get('hit_rate', 0.0):.3f}",
             f"bm25 recall={bm.get('recall', 0.0):.3f} hit={bm.get('hit_rate', 0.0):.3f}"]
    if 'embedding' in results:
        emb = results['embedding']
        parts.append(f"embedding recall={emb['recall']:.3f} hit={emb['hit_rate']:.3f}")
    winner = max(results, key=lambda k: results[k]['recall'])
    return "Verdict: " + "; ".join(parts) + f" -> best recall: {winner}"


def main(argv=None):
    """CLI entry. Offline by default; ``--embed`` turns on the embedding scorer."""
    parser = argparse.ArgumentParser(prog='carta.eval.run_eval',
                                     description='OKF selection eval (recall@5, hit-rate).')
    parser.add_argument('--embed', action='store_true',
                        help='Add the embedding scorer (uses the network).')
    parser.add_argument('--base-url', default=None,
                        help='OpenAI-compatible /embeddings base URL.')
    parser.add_argument('--model', default=None, help='Embedding model name.')
    parser.add_argument('--okf-path', default='okf/n8n', help='OKF catalog path.')
    parser.add_argument('--max-docs', type=int, default=5, help='k for recall@k.')
    args = parser.parse_args(argv)

    scorers = build_scorers(embed=args.embed, base_url=args.base_url, model=args.model)
    results = run_eval(scorers, okf_path=args.okf_path, max_docs=args.max_docs)
    print(format_table(results))
    print()
    print(verdict_line(results))


if __name__ == '__main__':
    main()