# Green CI, Swallowed Errors: LLM Coding Agents and Exception-Handling Warnings

Artifact for the paper of the same title (anonymous submission, AAAI-27 Workshop on Agentic Software Engineering).
It contains the synthetic tasks, the agents' final code for every episode, the hash-chained call logs, the
observer outputs, the follow-up's detector comparison, the post hoc analyses, and a script that recomputes every
number in the paper.

## Reproduce

```sh
python3 reproduce_tables.py
```

Standard library only (Python >= 3.9), about one minute. It writes `out/*.tex` and prints `MATCH` or `MISMATCH`
for each macro file in `expected/` (the files the paper inputs). A successful run ends with `RESULT: ALL MATCH`
and exits with code 0. Exact sign-flip tests and seeded bootstrap intervals reproduce exactly.

## Contents

| Path | What it is |
|---|---|
| `study-v0.5/src/` | First study: task generator (`generate.mjs`), agent loop and runner (Node.js), study linter |
| `study-v0.5/observer/` | Separately implemented Python observer (re-implements the linter, runs hidden tests) |
| `study-v0.5/results/dataset-test-001/` | The 40 frozen test tasks (modules, visible and hidden tests, planted warnings) |
| `study-v0.5/results/test-*-001/` | Per model: `episodes.jsonl` (final module per episode), `calls.jsonl` (hash-chained model calls) |
| `study-v0.5/results/observer-*/` | Observer outputs (classification of every planted warning; preregistered tests) |
| `v1.1/` | Preregistered follow-up (conditions N, D, R, G), same layout; `docs/` holds the preregistration and addendum |
| `v1.1/src/task-files/contract_check.py` | The contract-guarded CI check |
| `v1.1/tools/` | Detector comparison (`tool_compare.py`), zero-shot LLM judge (`llm_judge.py`) |
| `v1.1/posthoc/` | Post hoc analyses (not preregistered): trivial structural baseline, acceptance rules and mechanism |
| `paper/` | Scripts that render the paper's macros and tables |
| `field-check/` | AgentPack field-check script and aggregate counts (no AgentPack records included) |
| `expected/` | Macro files exactly as used in the paper |

## Re-running more than the tables

- **Observer** (re-classifies episodes, runs hidden tests): `python3 -I study-v0.5/observer/observe.py --help`.
  Hidden tests execute model-written code; run it only inside an isolated container.
- **Detectors** (`v1.1/tools/tool_compare.py`) need ruff 0.17.5, pylint 3.3.9 and scikit-learn 1.6.1; edit `VENV`
  at the top of the file to point at your environment. Semgrep 1.136.0 with the registry packs `p/python`,
  `p/bandit`, `p/r2c-best-practices`; the pinned rule files are not redistributed (Semgrep rules license), their
  SHA-256 sums are in `v1.1/tools/semgrep/SHA256SUMS`.
- **Post hoc analyses**: `python3 -I v1.1/posthoc/trivial_baseline.py --help` and
  `python3 -I v1.1/posthoc/mechanism_acceptance.py NEW_OUT_DIR` (outputs are create-only).
- **Agent runs** need local model servers (LM Studio, Ollama) or a Codex CLI login and are not needed to check the
  paper's numbers.

## Not included

Raw AgentPack data (download it from Hugging Face under its own license), development-run logs, and the
container harness configuration. These are available from the authors on request.

## License

Code: MIT (`LICENSE`). Data and documentation: CC BY 4.0 (`LICENSE-DATA`).
