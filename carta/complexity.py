"""Deterministic complexity-budget checks over Python source (pure ``ast``).

Zero LLM tokens, zero MCP. Used by the ``budget`` field of a ``carta flow``
stage to reject implementations whose functions exceed a complexity budget
(cyclomatic complexity, nesting depth, parameter count, line count).

This is the CCDD "budget" discipline reimplemented natively: the gate measures
the small model's output deterministically and forces a retry (or fails the
stage) when a function is too complex to trust.

Public API:
    - :func:`analyze_source` — per-function metrics for a source string.
    - :func:`check_budget` — list of human-readable budget violations.
"""
from __future__ import annotations

import ast
import os

# Compound statements that add a level of nesting.
_NEST = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.With,
    ast.AsyncWith,
    ast.Try,
)

# Map budget keys to the metric they constrain.
_BUDGET_KEYS = {
    "cyclomatic_max": "cyclomatic",
    "nesting_max": "nesting",
    "params_max": "params",
    "lines_max": "lines",
}


def _cyclomatic(func: ast.AST) -> int:
    """McCabe-style cyclomatic complexity: 1 + number of decision points."""
    count = 1
    for n in ast.walk(func):
        if isinstance(
            n,
            (
                ast.If,
                ast.For,
                ast.AsyncFor,
                ast.While,
                ast.ExceptHandler,
                ast.With,
                ast.AsyncWith,
                ast.Assert,
                ast.comprehension,
                ast.IfExp,
            ),
        ):
            count += 1
        elif isinstance(n, ast.BoolOp):
            # each extra operand in `a and b and c` adds a branch
            count += len(n.values) - 1
    return count


def _max_nesting(func: ast.AST) -> int:
    """Maximum depth of nested control-flow blocks inside the function body."""

    def walk(node: ast.AST, depth: int) -> int:
        best = depth
        for child in ast.iter_child_nodes(node):
            child_depth = depth + 1 if isinstance(child, _NEST) else depth
            best = max(best, walk(child, child_depth))
        return best

    return walk(func, 0)


def _count_params(func: ast.AST) -> int:
    """Total parameter count: positional, positional-only, keyword-only, *args, **kwargs."""
    a = func.args
    total = len(a.args) + len(a.posonlyargs) + len(a.kwonlyargs)
    if a.vararg:
        total += 1
    if a.kwarg:
        total += 1
    return total


def analyze_source(src: str, path: str = "<src>") -> list[dict]:
    """Return per-function metrics for ``src``.

    Each item: ``{name, lineno, cyclomatic, nesting, params, lines}``.
    Raises ``SyntaxError`` if ``src`` does not parse (caller decides policy).
    """
    tree = ast.parse(src, filename=path)
    out: list[dict] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = getattr(node, "end_lineno", None) or node.lineno
            out.append(
                {
                    "name": node.name,
                    "lineno": node.lineno,
                    "cyclomatic": _cyclomatic(node),
                    "nesting": _max_nesting(node),
                    "params": _count_params(node),
                    "lines": end - node.lineno + 1,
                }
            )
    return out


def _gather_py(target: str) -> list[str]:
    """Collect ``.py`` files under ``target`` (a dir) or ``[target]`` (a file)."""
    if os.path.isfile(target):
        return [target] if target.endswith(".py") else []
    files: list[str] = []
    for root, _dirs, names in os.walk(target):
        for name in names:
            if name.endswith(".py"):
                files.append(os.path.join(root, name))
    return sorted(files)


def check_budget(target: str, budget: dict) -> list[str]:
    """Return budget violations for every ``.py`` file under ``target``.

    ``budget`` keys: ``cyclomatic_max``, ``nesting_max``, ``params_max``,
    ``lines_max`` (any subset). Each violation is a ``path:line name: metric``
    string. A file that fails to parse yields a single ``SYNTAX ERROR`` entry.
    Returns an empty list when everything is within budget.
    """
    violations: list[str] = []
    for path in _gather_py(target):
        try:
            with open(path, "r", encoding="utf-8") as f:
                src = f.read()
        except OSError as exc:
            violations.append(f"{path}: cannot read ({exc})")
            continue
        try:
            funcs = analyze_source(src, path)
        except SyntaxError as exc:
            violations.append(f"{path}: SYNTAX ERROR — {exc.msg} (line {exc.lineno})")
            continue
        for fn in funcs:
            for key, metric in _BUDGET_KEYS.items():
                limit = budget.get(key)
                if isinstance(limit, int) and fn[metric] > limit:
                    violations.append(
                        f"{path}:{fn['lineno']} {fn['name']}(): "
                        f"{metric}={fn[metric]} > {key}={limit}"
                    )
    return violations
