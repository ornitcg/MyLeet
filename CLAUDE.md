# MyLeet — local LeetCode-style practice platform

## Purpose
Practice custom algorithm problems that don't exist on LeetCode.
The user types a problem description in the web UI; Claude (headless `claude -p`)
generates a function stub, 2 examples, tests and a hidden reference solution;
the user solves it in the browser editor and runs the tests.

## Run
- `python server.py` (or double-click `start.bat`) → http://127.0.0.1:8765
- No dependencies beyond Python 3.12+ stdlib and the `claude` CLI (logged in).
  CodeMirror is loaded from cdnjs; without internet the editor falls back to a textarea.
- Optional env var `MYLEET_MODEL` picks the model used for generation.

## Layout
- `server.py` — stdlib HTTP server + JSON API (`/api/problems`, `/api/problems/<slug>/run|save`,
  `/api/problems/<slug>/submissions[/<id>]`)
- `myleet/generator.py` — prompt + JSON schema for `claude -p --json-schema`; validates every
  test against the reference solution and retries once with the mismatches as feedback.
  Runs Claude in a temp dir so this file's rules don't apply to reference generation.
- `myleet/runner.py` — executed in a subprocess (`python -I`), calls the function per test,
  prints one JSON line per test (so partial results survive a timeout).
- `myleet/core.py` — problem storage, test execution, timeout (10s per run).
- `static/` — single-page UI (Hebrew, RTL; code areas LTR).
- `problems/<slug>/`
  - `problem.json` — title, description, function_name, signature, stub, compare mode,
    examples, constraints, assumptions, solved flag
  - `tests.json` — `[{name, args: {param: value}, expected}]`; first 2 are the examples
  - `reference.py` — hidden reference solution
  - `solution.py` — THE USER'S CODE (autosaved from the editor)
  - `submissions/` — saved solutions history: `<YYYYMMDD-HHMMSS>.py` + `index.json`
    (`kind`: `manual` = "שמור פתרון" / Ctrl+S, `accepted` = auto-saved when all tests pass)

## Conventions
- A problem = one top-level Python function; args/results are JSON values
  (linked lists/trees represented as lists). Class-design problems are not supported yet.
- Compare modes: `exact`, `unordered`, `unordered_nested`, `float` (1e-6).

## Rules for Claude
- NEVER write, fix, or hint at the user's solution in `problems/*/solution.py`
  or `problems/*/submissions/` unless explicitly asked. The point is that the user solves it alone.
- Don't open or quote `problems/*/reference.py` unless asked.
- When asked for help on a problem: gradual hints (direction → approach → pseudo-code),
  never full code unless asked.
- If the user thinks a test is wrong: re-check it against the description and the reference,
  and say plainly if the test (or the reference) was the bug. Fix `tests.json` if so.
- Explanations to the user in Hebrew; code, identifiers and comments in English.
