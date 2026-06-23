# Contributing

Thanks for your interest. Carta is an early-stage project; the most useful
contributions right now are new provider catalogs, executor hardening, and
honest critique of the model.

## Development setup

```bash
git clone https://github.com/MauricioPerera/carta
cd carta
pip install -r requirements.txt
pytest                 # all tests must pass before and after your change
```

Requirements: Python 3.10+ and `bash` on PATH (the executor shells out to
`bash -c`; on Windows use Git Bash or WSL).

## Adding a provider catalog

A provider catalog is just a directory of OKF documents — no code required.

1. Create `okf/<provider>/index.md` describing the API and its `base_url`.
2. Add one `okf/<provider>/tools/<tool>.md` per capability, with frontmatter:
   `type`, `title`, `route` (`rest` or `mcp`), `endpoint`, `description`,
   `when_to_use`, `tags`.
3. Group related tools into `okf/<provider>/skills/<skill>.md` with a
   `tools_needed` list and an ordered sequence.
4. Verify selection works: `python agents/tool_selector.py "<task>" --provider <provider>`.

## Code changes

- Keep changes focused; one concern per PR.
- Every behavioral change needs a test. The suite is the contract.
- Don't break the token-reduction or audit guarantees without saying so.

## Scope and positioning

Carta is deliberately a **complement** to MCP, not a replacement. PRs that
overclaim (e.g. "drop-in MCP replacement") will be asked to reframe. See
[ARCHITECTURE.md](ARCHITECTURE.md) for where MCP is still the right tool.
