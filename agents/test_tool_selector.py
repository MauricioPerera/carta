"""Tests T8: Tool Selector OKF."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tool_selector import (
    load_okf_index,
    select_tools,
    score_doc,
    format_context,
    count_tokens,
)

OKF = os.path.join(os.path.dirname(__file__), '..', 'okf', 'n8n')


def _names(docs):
    return [d['name'] for d in docs]


def test_create_workflow():
    docs = select_tools('create workflow email webhook', okf_path=OKF)
    names = _names(docs)
    assert 'create-workflow' in names, f"missing create-workflow: {names}"
    assert 'create_workflow_from_code' in names, f"missing create_workflow_from_code: {names}"
    print("OK test_create_workflow:", names)


def test_find_nodes():
    docs = select_tools('find nodes slack trigger', okf_path=OKF)
    names = _names(docs)
    assert 'find-nodes' in names, f"missing find-nodes: {names}"
    assert 'search_nodes' in names, f"missing search_nodes: {names}"
    print("OK test_find_nodes:", names)


def test_fallback():
    docs = select_tools('xyz123', okf_path=OKF)
    assert len(docs) <= 3, f"fallback should be top-3, got {len(docs)}"
    # Does not crash
    assert isinstance(docs, list)
    print("OK test_fallback:", _names(docs))


def test_token_reduction():
    query = 'create workflow email webhook'
    docs = select_tools(query, okf_path=OKF)
    ctx = format_context(docs)
    tokens_sel = count_tokens(ctx)
    idx = load_okf_index(OKF)
    baseline = format_context(idx['skills'] + idx['tools'])
    tokens_base = count_tokens(baseline)
    assert tokens_sel < tokens_base, f"{tokens_sel} >= {tokens_base}"
    print(f"OK test_token_reduction: {tokens_sel} < {tokens_base}")


def test_load_index():
    idx = load_okf_index(OKF)
    assert len(idx['skills']) == 5, f"expected 5 skills, got {len(idx['skills'])}"
    assert len(idx['tools']) == 25, f"expected 25 tools, got {len(idx['tools'])}"
    print(f"OK test_load_index: {len(idx['skills'])} skills, {len(idx['tools'])} tools")


def test_score_doc_basic():
    idx = load_okf_index(OKF)
    skill = next(d for d in idx['skills'] if d['name'] == 'create-workflow')
    s_match = score_doc(skill, 'create workflow')
    s_nomatch = score_doc(skill, 'xyz123')
    assert s_match > 0
    assert s_nomatch == 0
    print(f"OK test_score_doc_basic: match={s_match}, nomatch={s_nomatch}")


if __name__ == '__main__':
    test_load_index()
    test_score_doc_basic()
    test_create_workflow()
    test_find_nodes()
    test_fallback()
    test_token_reduction()
    print("\nALL TESTS OK")
