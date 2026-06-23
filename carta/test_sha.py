"""Tests T16: per-document SHA and selection SHA."""
import os
import tempfile

from carta.selector import doc_sha, selection_sha, load_okf_index, select_tools

OKF = os.path.join(os.path.dirname(__file__), '..', 'okf', 'n8n')


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def _make_catalog(tmp):
    """Create a tmp catalog with 3 tool docs a, b, c (original content)."""
    tools = os.path.join(tmp, 'tools')
    _write(os.path.join(tools, 'a.md'), '---\ntitle: A\n---\nbody A\n')
    _write(os.path.join(tools, 'b.md'), '---\ntitle: B\n---\nbody B\n')
    _write(os.path.join(tools, 'c.md'), '---\ntitle: C\n---\nbody C\n')


def _load(tmp):
    """Reload the tmp catalog and return {name: doc_dict}."""
    return {d['name']: d for d in load_okf_index(tmp)['tools']}


def test_doc_sha_deterministic():
    a = os.path.join(OKF, 'tools', 'create_workflow_from_code.md')
    b = os.path.join(OKF, 'tools', 'search_nodes.md')
    assert doc_sha(a) == doc_sha(a), "same file twice must match"
    assert doc_sha(a) != doc_sha(b), "different files must differ"
    print("OK test_doc_sha_deterministic")


def test_selection_sha_deterministic():
    with tempfile.TemporaryDirectory() as tmp:
        _make_catalog(tmp)
        docs = _load(tmp)
        list_ab = [docs['a'], docs['b']]
        assert selection_sha(list_ab) == selection_sha(list_ab), \
            "same list must hash equal"
        # Order independence: reversed input yields the same digest.
        assert selection_sha(list_ab) == selection_sha(list(reversed(list_ab))), \
            "digest must be order-independent"
        print("OK test_selection_sha_deterministic")


def test_selection_sha_only_selected():
    with tempfile.TemporaryDirectory() as tmp:
        _make_catalog(tmp)
        docs = _load(tmp)
        a, b, c = docs['a'], docs['b'], docs['c']

        sha_ab = selection_sha([a, b])
        sha_abc = selection_sha([a, b, c])
        assert sha_ab != sha_abc, "subset must differ from superset"

        # Changing c's content must NOT change the hash of [a, b]
        # (proves selection_sha only reads the selected docs).
        _write(os.path.join(tmp, 'tools', 'c.md'), 'completely different body\n')
        docs2 = _load(tmp)
        sha_ab_after_c_change = selection_sha([docs2['a'], docs2['b']])
        assert sha_ab == sha_ab_after_c_change, \
            "selection_sha([a,b]) must not read c"

        # Changing a's content MUST change the hash of [a, b].
        _write(os.path.join(tmp, 'tools', 'a.md'),
               '---\ntitle: A2\n---\nchanged\n')
        docs3 = _load(tmp)
        sha_ab_after_a_change = selection_sha([docs3['a'], docs3['b']])
        assert sha_ab != sha_ab_after_a_change, \
            "changing a selected doc must change the digest"
        print("OK test_selection_sha_only_selected")


def test_selection_sha_subset_smaller_than_full():
    idx = load_okf_index(OKF)
    total_docs = len(idx['skills']) + len(idx['tools'])
    selected = select_tools('create a workflow webhook set field respond',
                            okf_path=OKF)
    assert 0 < len(selected) < total_docs, \
        f"selection {len(selected)} must be < catalog {total_docs}"
    print(f"OK test_selection_sha_subset_smaller_than_full: "
          f"{len(selected)} < {total_docs}")


if __name__ == '__main__':
    test_doc_sha_deterministic()
    test_selection_sha_deterministic()
    test_selection_sha_only_selected()
    test_selection_sha_subset_smaller_than_full()
    print("\nALL TESTS OK")