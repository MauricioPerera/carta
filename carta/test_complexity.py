"""Tests for carta.complexity — deterministic AST budget checks."""
from __future__ import annotations

import textwrap

from carta.complexity import analyze_source, check_budget


def test_simple_function_low_metrics():
    src = "def f(x):\n    return x + 1\n"
    [fn] = analyze_source(src)
    assert fn["name"] == "f"
    assert fn["cyclomatic"] == 1
    assert fn["nesting"] == 0
    assert fn["params"] == 1
    assert fn["lines"] == 2


def test_cyclomatic_counts_branches():
    src = textwrap.dedent(
        """
        def f(x):
            if x > 0:
                return 1
            elif x < 0:
                return -1
            for i in range(x):
                pass
            return 0
        """
    )
    [fn] = analyze_source(src)
    # base 1 + if + elif(if) + for = 4
    assert fn["cyclomatic"] == 4


def test_boolop_adds_branches():
    src = "def f(a, b, c):\n    return a and b and c\n"
    [fn] = analyze_source(src)
    # base 1 + (3 operands - 1) = 3
    assert fn["cyclomatic"] == 3


def test_nesting_depth():
    src = textwrap.dedent(
        """
        def f(x):
            if x:
                for i in x:
                    while i:
                        pass
        """
    )
    [fn] = analyze_source(src)
    assert fn["nesting"] == 3


def test_param_count_all_kinds():
    src = "def f(a, b, /, c, *args, d, **kwargs):\n    pass\n"
    [fn] = analyze_source(src)
    # a,b (posonly) + c (pos) + d (kwonly) + *args + **kwargs = 6
    assert fn["params"] == 6


def test_check_budget_pass(tmp_path):
    (tmp_path / "m.py").write_text("def f(x):\n    return x\n", encoding="utf-8")
    violations = check_budget(str(tmp_path), {"cyclomatic_max": 5, "lines_max": 10})
    assert violations == []


def test_check_budget_violation(tmp_path):
    src = textwrap.dedent(
        """
        def big(a, b, c, d, e, f, g):
            return a
        """
    )
    (tmp_path / "m.py").write_text(src, encoding="utf-8")
    violations = check_budget(str(tmp_path), {"params_max": 4})
    assert len(violations) == 1
    assert "params=7 > params_max=4" in violations[0]
    assert "big()" in violations[0]


def test_check_budget_reports_syntax_error(tmp_path):
    (tmp_path / "broken.py").write_text("def f(:\n", encoding="utf-8")
    violations = check_budget(str(tmp_path), {"cyclomatic_max": 5})
    assert len(violations) == 1
    assert "SYNTAX ERROR" in violations[0]


def test_check_budget_single_file(tmp_path):
    p = tmp_path / "one.py"
    p.write_text("def f(a, b, c, d, e):\n    pass\n", encoding="utf-8")
    violations = check_budget(str(p), {"params_max": 3})
    assert len(violations) == 1


def test_check_budget_ignores_non_py(tmp_path):
    (tmp_path / "readme.txt").write_text("not python", encoding="utf-8")
    violations = check_budget(str(tmp_path), {"cyclomatic_max": 1})
    assert violations == []
