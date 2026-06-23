"""T8: OKF Tool Selector.

Given the text of a task, returns only the relevant OKF docs
(2-5 docs, ~500-1500 tokens) to inject into an agent's prompt.
"""
import os
import re
import sys
import yaml


def _parse_frontmatter(text):
    """Extract YAML frontmatter and body from a .md. Returns (fm_dict, body_str)."""
    if text.startswith('---'):
        end = text.find('\n---', 3)
        if end != -1:
            fm_raw = text[3:end].strip()
            body = text[end + 4:].strip()
            try:
                fm = yaml.safe_load(fm_raw) or {}
            except yaml.YAMLError:
                fm = {}
            return fm, body
    return {}, text


def load_okf_index(okf_path='okf/n8n'):
    """Read all .md files from skills/ and tools/.

    Returns {'skills': [...], 'tools': [...]} with path, frontmatter and
    full content per doc.
    """
    index = {'skills': [], 'tools': []}
    base = okf_path
    for kind, subdir in (('skills', 'skills'), ('tools', 'tools')):
        d = os.path.join(base, subdir)
        if not os.path.isdir(d):
            continue
        for fname in sorted(os.listdir(d)):
            if not fname.endswith('.md'):
                continue
            path = os.path.join(d, fname)
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            fm, _body = _parse_frontmatter(content)
            index[kind].append({
                'path': path,
                'name': fname[:-3],
                'frontmatter': fm,
                'content': content,
            })
    return index


def _tokenize(text):
    """Tokenize by spaces/punctuation, case-insensitive."""
    if not text:
        return []
    return [t for t in re.split(r'[\s\W_]+', text.lower()) if t]


def score_doc(doc, query):
    """Simple relevance scoring of a doc against the query.

    +3 if a query word is in title
    +2 if in description or when_to_use
    +1 if in tags
    +2 if in the doc content
    """
    q_tokens = set(_tokenize(query))
    if not q_tokens:
        return 0.0
    fm = doc.get('frontmatter', {}) or {}
    title = str(fm.get('title', '') or '')
    desc = str(fm.get('description', '') or '')
    when_to_use = str(fm.get('when_to_use', '') or '')
    tags = fm.get('tags', []) or []
    tags_text = ' '.join(str(t) for t in tags)
    content = doc.get('content', '') or ''

    title_tokens = set(_tokenize(title))
    desc_tokens = set(_tokenize(desc))
    when_tokens = set(_tokenize(when_to_use))
    tag_tokens = set(_tokenize(tags_text))
    content_tokens = set(_tokenize(content))

    score = 0.0
    score += 3.0 * len(q_tokens & title_tokens)
    score += 2.0 * len(q_tokens & desc_tokens)
    score += 2.0 * len(q_tokens & when_tokens)
    score += 1.0 * len(q_tokens & tag_tokens)
    score += 2.0 * len(q_tokens & content_tokens)
    return score


def select_tools(query, okf_path='okf/n8n', max_docs=5):
    """Select relevant docs.

    1. Scores skills, takes the highest-scoring skill.
    2. Reads tools_needed from that skill and loads those tool docs.
    3. Returns docs ordered by relevance (skill first, then tools).
    4. Fallback: if no skill has score>0, top-3 tools by score.
    """
    index = load_okf_index(okf_path)

    scored_skills = [(score_doc(s, query), s) for s in index['skills']]
    scored_skills = [(sc, s) for sc, s in scored_skills if sc > 0]
    scored_skills.sort(key=lambda x: x[0], reverse=True)

    if not scored_skills:
        # Fallback: top-3 tools by direct score
        scored_tools = [(score_doc(t, query), t) for t in index['tools']]
        scored_tools.sort(key=lambda x: x[0], reverse=True)
        top = scored_tools[:3]
        return [t for _sc, t in top]

    best_skill = scored_skills[0][1]
    fm = best_skill.get('frontmatter', {}) or {}
    tools_needed = fm.get('tools_needed', []) or []

    tools_by_name = {t['name']: t for t in index['tools']}
    selected_tools = []
    for tn in tools_needed:
        if tn in tools_by_name:
            selected_tools.append(tools_by_name[tn])

    # Sort tools by descending score; skill stays first.
    selected_tools.sort(key=lambda t: score_doc(t, query), reverse=True)

    result = [best_skill] + selected_tools
    return result[:max_docs]


def count_tokens(text):
    """Approximation: len(text) // 4."""
    return len(text) // 4


def _doc_header(doc):
    fm = doc.get('frontmatter', {}) or {}
    return f"# === {doc['path']} (title: {fm.get('title', doc['name'])}) ==="


def format_context(selected_docs):
    """Concatenate the selected docs into a string ready to inject.

    Includes a separator between docs and a header with totals and tokens.
    """
    parts = []
    for doc in selected_docs:
        parts.append(_doc_header(doc))
        parts.append(doc.get('content', ''))
    body = '\n\n---\n\n'.join(parts)
    n_sel = len(selected_docs)
    # Total docs counted: skills+tools loaded in the global index.
    # Here we only know the selected ones; M = total is passed via count.
    tokens = count_tokens(body)
    header = f"# OKF context: {n_sel} selected docs (~{tokens} tokens)"
    return f"{header}\n\n{body}"


def _all_docs_count(okf_path='okf/n8n'):
    idx = load_okf_index(okf_path)
    return len(idx['skills']) + len(idx['tools'])


def _parse_provider(argv):
    """Extract --provider <name> from argv. Returns (query, okf_path).

    Usage: python -m carta.selector "<query>" [--provider <name>]
    --provider jsonplaceholder → okf/jsonplaceholder
    default (no flag) → okf/n8n
    """
    query = None
    provider = 'n8n'
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == '--provider':
            if i + 1 < len(argv):
                provider = argv[i + 1]
                i += 2
                continue
            else:
                print("error: --provider requires a value")
                sys.exit(2)
        elif a.startswith('--provider='):
            provider = a.split('=', 1)[1]
        else:
            query = a
        i += 1
    okf_path = f'okf/{provider}'
    return query, okf_path, provider


def main():
    query, okf_path, provider = _parse_provider(sys.argv)
    if not query:
        print('usage: python -m carta.selector "<query>" [--provider <name>]')
        sys.exit(1)
    selected = select_tools(query, okf_path=okf_path)
    context = format_context(selected)
    tokens_sel = count_tokens(context)

    # Baseline: all docs concatenated.
    idx = load_okf_index(okf_path)
    all_docs = idx['skills'] + idx['tools']
    baseline = format_context(all_docs)
    tokens_base = count_tokens(baseline)
    pct = (tokens_sel / tokens_base * 100.0) if tokens_base else 0.0

    print(f"Query: {query}")
    print(f"Provider: {provider} ({okf_path})")
    print(f"Selected docs ({len(selected)}/{len(all_docs)}):")
    for d in selected:
        print(f"  - {d['path']}")
    print(f"Selected tokens: {tokens_sel}")
    print(f"Baseline tokens: {tokens_base}")
    print(f"Reduction:       {pct:.1f}% of baseline")


if __name__ == '__main__':
    main()