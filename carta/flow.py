"""Declarative agent pipeline (``carta flow``).

A *flow* is a YAML file describing a fixed sequence of agent stages. The
output of each stage is fed forward as context to the next, so each stage's
LLM only performs its own step. Unlike ``send_to_agent`` (fire-and-forget)
and ``carta watch`` (reactive), a flow declares the whole sequence upfront
and passes explicit context between stages.

Stages may declare an optional ``gate`` shell command. After the agent runs,
the gate is executed deterministically (zero LLM tokens). If it exits 0 the
stage is considered verified. If it fails the output is injected into context
as ``{gate_output}`` and the agent is retried up to ``gate_retries`` times
(default 1). This avoids burning a full "tester" LLM agent on something
``pytest`` or a linter can verify for free.

Public API:
    - :func:`load_flow` — parse and validate a ``flow.yaml``.
    - :func:`run_flow` — execute the pipeline stage by stage.
"""
from __future__ import annotations

import hashlib
import json
import os


def _hash_file(path: str) -> str | None:
    """Return the sha256 hex digest of ``path``, or ``None`` if unreadable."""
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


def _hash_tree(target: str) -> dict:
    """Map every file under ``target`` (dir or single file) to its sha256.

    Skips ``__pycache__`` directories and ``.pyc`` files: those are byte-code
    artifacts regenerated on import, so freezing them would make verify_frozen
    raise false-positive tamper failures the moment the tests are imported.
    """
    out: dict = {}
    if os.path.isfile(target):
        h = _hash_file(target)
        if h is not None:
            out[os.path.normpath(target)] = h
        return out
    for root, dirs, names in os.walk(target):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in names:
            if name.endswith(".pyc"):
                continue
            p = os.path.join(root, name)
            h = _hash_file(p)
            if h is not None:
                out[os.path.normpath(p)] = h
    return out


def load_flow(path: str) -> dict:
    """Read and parse a ``flow.yaml``.

    Validates:
    - Has ``id`` (str)
    - Has ``stages`` (list, non-empty)
    - Each stage has ``id``, ``agent`` and ``task`` (all str)

    Raises ``ValueError`` with a clear message when a required field is
    missing. Returns the parsed dict.
    """
    import yaml

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    if not isinstance(data, dict):
        raise ValueError("flow.yaml: top-level must be a mapping")

    if "id" not in data or not isinstance(data["id"], str) or not data["id"]:
        raise ValueError("flow.yaml: missing required field 'id'")

    stages = data.get("stages")
    if not isinstance(stages, list) or len(stages) == 0:
        raise ValueError("flow.yaml: 'stages' must be a non-empty list")

    for i, stage in enumerate(stages):
        if not isinstance(stage, dict):
            raise ValueError(f"flow.yaml: stage #{i} must be a mapping")
        for key in ("id", "agent", "task"):
            if key not in stage or not isinstance(stage[key], str) or not stage[key]:
                raise ValueError(
                    f"flow.yaml: stage #{i} missing required field '{key}'"
                )
        gate = stage.get("gate")
        if gate is not None and not isinstance(gate, str):
            raise ValueError(
                f"flow.yaml: stage #{i} 'gate' must be a string command"
            )
        retries = stage.get("gate_retries")
        if retries is not None and (not isinstance(retries, int) or retries < 0):
            raise ValueError(
                f"flow.yaml: stage #{i} 'gate_retries' must be a non-negative integer"
            )
        freeze = stage.get("freeze")
        if freeze is not None and not isinstance(freeze, str):
            raise ValueError(
                f"flow.yaml: stage #{i} 'freeze' must be a path string"
            )
        verify_frozen = stage.get("verify_frozen")
        if verify_frozen is not None and not isinstance(verify_frozen, bool):
            raise ValueError(
                f"flow.yaml: stage #{i} 'verify_frozen' must be a boolean"
            )
        budget = stage.get("budget")
        if budget is not None:
            if not isinstance(budget, dict):
                raise ValueError(
                    f"flow.yaml: stage #{i} 'budget' must be a mapping of "
                    "metric_max -> integer"
                )
            for bkey, bval in budget.items():
                if not isinstance(bval, int) or bval < 0:
                    raise ValueError(
                        f"flow.yaml: stage #{i} budget '{bkey}' must be a "
                        "non-negative integer"
                    )
        budget_paths = stage.get("budget_paths")
        if budget_paths is not None and not isinstance(budget_paths, str):
            raise ValueError(
                f"flow.yaml: stage #{i} 'budget_paths' must be a path string"
            )
        escalate = stage.get("gate_escalate")
        if escalate is not None and (not isinstance(escalate, str) or not escalate):
            raise ValueError(
                f"flow.yaml: stage #{i} 'gate_escalate' must be an agent-id string"
            )
        escalate_model = stage.get("gate_escalate_model")
        if escalate_model is not None and (
            not isinstance(escalate_model, str) or not escalate_model
        ):
            raise ValueError(
                f"flow.yaml: stage #{i} 'gate_escalate_model' must be a model-name string"
            )
        foreach = stage.get("foreach")
        if foreach is not None and (not isinstance(foreach, str) or not foreach):
            raise ValueError(
                f"flow.yaml: stage #{i} 'foreach' must be a manifest path or "
                "context-key string"
            )
        attest = stage.get("attest")
        if attest is not None and (not isinstance(attest, str) or not attest):
            raise ValueError(
                f"flow.yaml: stage #{i} 'attest' must be a reviewer agent-id string"
            )

    return data


def run_flow(
    flow: dict,
    specs_dir: str,
    initial_input: str = "",
    base_url: str | None = None,
    on_stage: "callable | None" = None,
    on_attest: "callable | None" = None,
) -> dict:
    """Execute the pipeline stage by stage.

    Parameters
    ----------
    flow:
        Parsed dict from :func:`load_flow`.
    specs_dir:
        Directory with agent-specs (to find ``<agent>.yaml``).
    initial_input:
        Value of the ``{input}`` variable in the first stage.
    base_url:
        Override the model base URL. If ``None``, uses
        ``flow.get("base_url", "http://localhost:1234/v1")``.
    on_stage:
        Optional ``callback(stage_id, status, data)`` where ``status`` is
        one of ``"start"``, ``"done"``, ``"error"``.
    """
    from .agent import CartaAgent
    from .agent_yaml import load_agent_yaml

    # CLI --base-url and flow-level base_url are kept for explicit overrides.
    # When neither is set, each stage uses its own agent-spec's base_url so
    # carta init's configuration is the single source of truth.
    _flow_base_url = base_url if base_url is not None else flow.get("base_url")

    context: dict = {"input": initial_input}
    results: list = []
    # sha256 of every file locked by a prior stage's `freeze:`. The CCDD oracle:
    # once a strong model authors property-tests, a small implementer stage with
    # `verify_frozen: true` cannot weaken them — any byte change fails the gate.
    frozen: dict = {}

    for stage in flow["stages"]:
        stage_id = stage["id"]
        gate_cmd_tmpl = stage.get("gate")
        gate_retries = int(stage.get("gate_retries", 1))
        output_key = stage.get("output_key")
        freeze_target = stage.get("freeze")
        verify_frozen = bool(stage.get("verify_frozen", False))
        budget = stage.get("budget")
        budget_paths = stage.get("budget_paths", "src")
        escalate_model = stage.get("gate_escalate_model")
        escalate_agent = stage.get("gate_escalate")
        foreach = stage.get("foreach")
        attest_agent = stage.get("attest")

        # Locate + load the stage's agent spec (shared across foreach items).
        spec_path = os.path.join(specs_dir, stage["agent"] + ".yaml")
        if not os.path.isfile(spec_path):
            raise FileNotFoundError(
                f"flow stage {stage_id!r}: agent spec not found: {spec_path}"
            )
        config = load_agent_yaml(spec_path)

        def _interp(tmpl, extra=None):
            ctx = dict(context, **(extra or {}))
            try:
                return tmpl.format_map(ctx)
            except KeyError as _e:
                raise ValueError(
                    f"Stage {stage_id!r}: task references undefined variable {_e}. "
                    f"Available variables: {list(ctx.keys())}"
                ) from _e
            except (ValueError, IndexError) as _e:
                raise ValueError(
                    f"Stage {stage_id!r}: task template error — {_e}. "
                    "Hint: literal braces must be escaped as {{{{ and }}}}."
                ) from _e

        def _run_agent(cfg, the_task, model_override=None):
            """Build a CartaAgent from ``cfg`` and run ``the_task``.

            ``model_override`` swaps only the model name (for gate escalation),
            keeping the agent's role, OKF context and CCDD permissions intact.
            """
            stage_base_url = _flow_base_url or cfg.model["base_url"]
            ag = CartaAgent(
                catalogs=cfg.knowledge,
                model=model_override or cfg.model["name"],
                base_url=stage_base_url,
                timeout=cfg.model.get("timeout", 60),
                api_key=cfg.model.get("api_key") or "",
            )
            try:
                return ag.run(the_task, max_steps=cfg.model.get("max_steps", 8))
            except Exception as exc:
                if on_stage is not None:
                    on_stage(stage_id, "error", {"error": str(exc)})
                raise

        def _attest(target):
            """Adversarial oracle review (CCDD R6 analog).

            An INDEPENDENT model (``attest_agent``, ideally not the author)
            reads the spec and each authored test under ``target`` and judges
            whether the assertions are FAITHFUL to the spec — not merely whether
            they run. Returns ``(ok, reasons)``. An inconclusive verdict is
            treated as failure: never freeze an unreviewed oracle.
            """
            # Human attestation (CCDD R6, deterministic): a person approves the
            # oracle before it is frozen. Converges where LLM-vs-LLM review is
            # fuzzy; the trade-off is it pauses unattended runs.
            if attest_agent == "human":
                files = sorted(_hash_tree(target).keys())
                if on_stage is not None:
                    on_stage(stage_id, "attest", {"agent": "human", "target": target})
                approved = (on_attest or _console_attest)(
                    stage_id, initial_input, target, files
                )
                if approved:
                    if on_stage is not None:
                        on_stage(stage_id, "attest_pass", {"agent": "human"})
                    return True, "human approved the oracle"
                if on_stage is not None:
                    on_stage(stage_id, "attest_fail", {
                        "agent": "human", "output": "human rejected the oracle"})
                return False, "human rejected the oracle — revise the tests"

            att_path = os.path.join(specs_dir, attest_agent + ".yaml")
            if not os.path.isfile(att_path):
                raise FileNotFoundError(
                    f"flow stage {stage_id!r}: attest agent spec not found: {att_path}"
                )
            att_config = load_agent_yaml(att_path)
            if on_stage is not None:
                on_stage(stage_id, "attest", {"agent": attest_agent, "target": target})
            att_task = (
                "You are an ADVERSARIAL oracle reviewer. You judge a frozen test "
                "suite on TWO axes: fidelity and coverage.\n\n"
                f"1. Use read_file with path='{initial_input}' to read the spec.\n"
                f"2. Use list_dir on '{target}' and read_file on each test file there.\n"
                "3. FIDELITY — for EACH test, decide whether its assertions are "
                "faithful to the spec. A test that asserts a value the spec "
                "contradicts is a FAILURE (cite file, assertion, spec clause).\n"
                "4. COVERAGE — enumerate every normative requirement in the spec "
                "(each metric, rule, function, invariant the spec mandates). If "
                "ANY required component has NO corresponding test, that is a "
                "FAILURE — list exactly what is missing. A faithful but INCOMPLETE "
                "suite must FAIL.\n\n"
                "End your reply with EXACTLY one final line:\n"
                "  ATTEST: PASS   (every test is faithful AND the spec is fully covered)\n"
                "  ATTEST: FAIL   (a test contradicts the spec, or coverage is incomplete)"
            )
            result = _run_agent(att_config, att_task)
            answer = (result.get("answer") or "").strip()
            up = answer.upper()
            if "ATTEST: PASS" in up and "ATTEST: FAIL" not in up:
                if on_stage is not None:
                    on_stage(stage_id, "attest_pass", {"agent": attest_agent})
                return True, answer
            reasons = answer if "ATTEST: FAIL" in up else (
                "attestation inconclusive (no ATTEST verdict):\n" + answer
            )
            if on_stage is not None:
                on_stage(stage_id, "attest_fail", {
                    "agent": attest_agent, "output": reasons[:200]})
            return False, reasons

        def _execute_unit(task_text, gate_cmd, item_label=None):
            """Run the gated retry loop + escalation for ONE atomic task.

            Returns ``(answer, result, gate_passed, gate_output)``. This is the
            CCDD unit of work: a single contract delegated to the small model,
            iterated against its deterministic gate, escalated once if needed.
            """
            has_gate = (
                gate_cmd is not None
                or budget is not None
                or (verify_frozen and bool(frozen))
                or bool(attest_agent)
            )

            def _verify():
                ok, out = _verify_stage(
                    gate_cmd=gate_cmd,
                    verify_frozen=verify_frozen,
                    frozen=frozen,
                    budget=budget,
                    budget_paths=budget_paths,
                )
                # Oracle attestation (the CCDD R6 analog): once the deterministic
                # checks pass, a second, independent model reviews the authored
                # tests against the spec. A test that RUNS but asserts something
                # the spec contradicts is caught here — compileall/pytest can't.
                if ok and attest_agent:
                    a_ok, a_reasons = _attest(freeze_target or budget_paths)
                    if not a_ok:
                        return False, "ORACLE ATTESTATION FAILED:\n" + a_reasons
                return ok, out

            gate_passed = not has_gate
            gate_output = ""
            result = None
            answer = ""

            for attempt in range(gate_retries + 1):
                if attempt > 0:
                    retry_task = (
                        task_text
                        + f"\n\nGATE FAILED (attempt {attempt}/{gate_retries}):\n"
                        + gate_output
                        + "\nFix the issues and rewrite the file."
                    )
                else:
                    retry_task = task_text

                result = _run_agent(config, retry_task)
                answer = result.get("answer") or ""
                if output_key:
                    context[output_key] = answer

                if not has_gate:
                    break

                ok, gate_output = _verify()
                if ok:
                    gate_passed = True
                    if on_stage is not None:
                        on_stage(stage_id, "gate_pass", {
                            "output": gate_output[:200],
                            "attempt": attempt + 1, "item": item_label})
                    break

                context["gate_output"] = gate_output
                if on_stage is not None:
                    on_stage(stage_id, "gate_fail", {
                        "output": gate_output[:200],
                        "attempt": attempt + 1, "item": item_label})

            # Escalation: spend the strong model only when the gate proves the
            # cheap one could not pass.
            if has_gate and not gate_passed and (escalate_model or escalate_agent):
                if escalate_agent:
                    esc_path = os.path.join(specs_dir, escalate_agent + ".yaml")
                    if not os.path.isfile(esc_path):
                        raise FileNotFoundError(
                            f"flow stage {stage_id!r}: gate_escalate agent spec "
                            f"not found: {esc_path}"
                        )
                    esc_config = load_agent_yaml(esc_path)
                    esc_label = escalate_agent
                else:
                    esc_config = config
                    esc_label = f"{stage['agent']} @ {escalate_model}"
                if on_stage is not None:
                    on_stage(stage_id, "escalate", {"agent": esc_label, "item": item_label})
                esc_task = (
                    task_text
                    + "\n\nA weaker model exhausted its attempts. Last gate failure:\n"
                    + gate_output
                    + "\nFix the remaining issues and rewrite the file(s)."
                )
                result = _run_agent(esc_config, esc_task, model_override=escalate_model)
                answer = result.get("answer") or ""
                if output_key:
                    context[output_key] = answer
                ok, gate_output = _verify()
                if ok:
                    gate_passed = True
                    if on_stage is not None:
                        on_stage(stage_id, "gate_pass", {
                            "output": gate_output[:200],
                            "attempt": "escalated", "item": item_label})
                else:
                    context["gate_output"] = gate_output
                    if on_stage is not None:
                        on_stage(stage_id, "gate_fail", {
                            "output": gate_output[:200],
                            "attempt": "escalated", "item": item_label})

            return answer, result, gate_passed, gate_output

        stage_has_gate = (
            gate_cmd_tmpl is not None
            or budget is not None
            or (verify_frozen and bool(frozen))
            or bool(attest_agent)
        )

        if foreach:
            # CCDD decomposition: fan out one gated unit per manifest item.
            items = _load_manifest(foreach, context)
            if on_stage is not None:
                on_stage(stage_id, "foreach", {"count": len(items), "source": foreach})
            units = []
            gate_passed = True
            for idx, item in enumerate(items):
                label = item.get("name") if isinstance(item, dict) else str(item)
                u_task = _interp(stage["task"], {"item": item})
                u_gate = _interp(gate_cmd_tmpl, {"item": item}) if gate_cmd_tmpl else None
                if on_stage is not None:
                    on_stage(stage_id, "start", {
                        "task": f"[{idx + 1}/{len(items)}] {label}"})
                ans, res, passed, out = _execute_unit(u_task, u_gate, item_label=label)
                units.append({"item": item, "answer": ans,
                              "gate_passed": passed, "output": out})
                gate_passed = gate_passed and passed
            n_pass = sum(1 for u in units if u["gate_passed"])
            answer = f"{n_pass}/{len(units)} units passed gate"
            gate_output = "\n".join(
                f"FAIL {u['item'].get('name', i) if isinstance(u['item'], dict) else i}: "
                f"{u['output'][:120]}"
                for i, u in enumerate(units) if not u["gate_passed"]
            )
            result = {"steps": []}
            stage_record = {
                "stage_id": stage_id, "agent": stage["agent"],
                "task": f"foreach {foreach} ({len(units)} units)",
                "answer": answer, "steps": [], "units": units,
            }
            if stage_has_gate:
                stage_record["gate"] = {"passed": gate_passed, "output": gate_output}
        else:
            task_text = _interp(stage["task"])
            if on_stage is not None:
                on_stage(stage_id, "start", {"task": task_text[:120]})
            answer, result, gate_passed, gate_output = _execute_unit(
                task_text, gate_cmd_tmpl
            )
            stage_record = {
                "stage_id": stage_id, "agent": stage["agent"],
                "task": task_text, "answer": answer,
                "steps": result.get("steps", []) if result else [],
            }
            if stage_has_gate:
                stage_record["gate"] = {"passed": gate_passed, "output": gate_output}

        # Freeze outputs (only when the gate passed) so later stages can't alter
        # them. Skipping a failed-gate freeze keeps the downstream gate winnable.
        if freeze_target and gate_passed:
            frozen.update(_hash_tree(freeze_target))
            if on_stage is not None:
                on_stage(stage_id, "freeze", {
                    "target": freeze_target, "files": len(_hash_tree(freeze_target))})
            stage_record["frozen"] = sorted(_hash_tree(freeze_target).keys())
        elif freeze_target and not gate_passed:
            stage_record["frozen"] = []
            if on_stage is not None:
                on_stage(stage_id, "freeze_skipped", {
                    "target": freeze_target, "reason": "stage gate did not pass"})

        if on_stage is not None:
            on_stage(stage_id, "done", {
                "answer": answer[:120],
                "steps": len(result.get("steps", []) if result else [])})

        results.append(stage_record)

    return {
        "flow_id": flow["id"],
        "stages_run": len(results),
        "context": context,
        "results": results,
        "final_answer": results[-1]["answer"] if results else "",
    }


def _console_attest(stage_id: str, spec: str, target: str, files: list) -> bool:
    """Default human-attestation prompt (CCDD R6) for ``attest: human``.

    Shows the spec path and the to-be-frozen test files, then reads a yes/no
    from stdin. Used only in interactive runs; in unattended runs inject an
    ``on_attest`` callback instead (an unanswered prompt would block).
    """
    print(f"\n[carta flow] HUMAN ATTESTATION — stage {stage_id!r}")
    print(f"  spec:   {spec}")
    print(f"  oracle: {target} ({len(files)} test file(s))")
    for f in files:
        print(f"    - {f}")
    print("  Review the tests against the spec, then approve or reject.")
    try:
        resp = input("  Approve freezing this oracle? [y/N]: ").strip().lower()
    except EOFError:
        return False
    return resp in ("y", "yes")


def _load_manifest(source: str, context: dict) -> list:
    """Resolve a ``foreach`` source to a list of items.

    Three forms, in priority order:
      - ``glob:<pattern>`` — list of file paths matching the glob (sorted).
        Robust decomposition: derive units from the test files actually on disk
        instead of a manifest a model must remember to write.
      - a context key holding a list (produced by a prior stage).
      - a path to a JSON file containing a list (an explicit manifest).
    """
    if source.startswith("glob:"):
        import glob as _glob

        pattern = source[len("glob:"):]
        matches = sorted(_glob.glob(pattern))
        if not matches:
            raise FileNotFoundError(
                f"foreach glob {pattern!r} matched no files"
            )
        return matches
    if source in context and isinstance(context[source], list):
        return context[source]
    if os.path.isfile(source):
        with open(source, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError(
                f"foreach manifest {source!r} must contain a JSON list"
            )
        return data
    raise FileNotFoundError(
        f"foreach source {source!r} not found (no glob/context-key/file match)"
    )


def _verify_stage(
    gate_cmd: "str | None",
    verify_frozen: bool,
    frozen: dict,
    budget: "dict | None",
    budget_paths: str,
) -> "tuple[bool, str]":
    """Run all deterministic checks for a stage. Returns ``(passed, output)``.

    Order (first failure wins, cheapest first):
      1. Frozen-oracle integrity — if ``verify_frozen`` and any locked file's
         sha256 changed, the implementer tampered with the oracle. Hard fail.
      2. Shell gate — run ``gate_cmd``; non-zero exit fails with its output.
      3. Complexity budget — every function under ``budget_paths`` must be
         within ``budget``; violations fail with a readable list.
    """
    # 1. Frozen-oracle integrity.
    if verify_frozen and frozen:
        tampered = [
            path for path, want in frozen.items() if _hash_file(path) != want
        ]
        if tampered:
            return False, (
                "FROZEN ORACLE TAMPERED — these locked test files were modified "
                "or deleted and must be restored byte-for-byte:\n"
                + "\n".join(sorted(tampered))
            )

    # 2. Shell gate.
    if gate_cmd is not None:
        from .local import local_run_command as _run_cmd

        gate_result = _run_cmd(gate_cmd)
        gate_output = (
            (gate_result.get("stdout") or "") + (gate_result.get("stderr") or "")
        ).strip()
        # local_run_command reports the process exit status under "returncode".
        if gate_result.get("returncode") != 0:
            return False, gate_output or gate_result.get("error", "gate failed")

    # 3. Complexity budget.
    if budget:
        from .complexity import check_budget

        violations = check_budget(budget_paths, budget)
        if violations:
            return False, "COMPLEXITY BUDGET EXCEEDED:\n" + "\n".join(violations)

    return True, "ok"