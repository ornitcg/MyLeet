"""Generates a problem (stub, examples, tests, reference solution) with Claude Code in headless mode."""
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from . import core

CLAUDE_TIMEOUT_SEC = 420
MAX_ATTEMPTS = 2

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "slug": {"type": "string"},
        "function_name": {"type": "string"},
        "signature": {"type": "string"},
        "stub": {"type": "string"},
        "compare": {"type": "string", "enum": ["exact", "unordered", "unordered_nested", "float"]},
        "examples": {
            "type": "array", "minItems": 2, "maxItems": 2,
            "items": {"type": "object", "properties": {
                "args": {"type": "object"}, "expected": {}, "explanation": {"type": "string"}},
                "required": ["args", "expected", "explanation"]},
        },
        "constraints": {"type": "array", "items": {"type": "string"}},
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "tests": {
            "type": "array", "minItems": 8,
            "items": {"type": "object", "properties": {
                "name": {"type": "string"}, "args": {"type": "object"}, "expected": {}},
                "required": ["name", "args", "expected"]},
        },
        "reference_solution": {"type": "string"},
    },
    "required": ["title", "slug", "function_name", "signature", "stub", "compare", "examples",
                 "constraints", "assumptions", "tests", "reference_solution"],
}

PROMPT = """You are generating a coding-practice problem for a local LeetCode-like platform.
The user wrote this problem description:

<description>
{description}
</description>
{title_hint}
Produce the structured output with these rules:
- The solution is ONE top-level Python function (not a class). Pick a clear snake_case
  `function_name` and parameter names. `signature` is just the def line with type hints,
  e.g. "def two_sum(nums: list[int], target: int) -> list[int]:".
- `stub`: complete Python source the user starts from: needed imports, the def line,
  a short English docstring, and body `pass`. Do NOT include any solution logic.
- All inputs/outputs must be JSON values (int, float, str, bool, null, list, dict).
  Represent linked lists / trees / matrices as lists.
- `examples`: exactly 2 small illustrative examples. `args` maps parameter name -> value.
  `explanation`: one or two sentences, in the SAME language as the description.
- `tests`: 12-20 MORE tests (do not repeat the examples): typical cases, edge cases
  (empty input, single element, duplicates, negatives, boundaries, all-equal, etc.),
  and 2-3 larger inputs (up to ~150 elements, written out literally).
  `name`: short English snake_case, e.g. "empty_list", "all_negative".
- `compare`: "exact" by default; "unordered" when the returned list may be in any order;
  "unordered_nested" when both the outer list and each inner list may be in any order;
  "float" when the answer is floating point (tolerance 1e-6).
- `reference_solution`: correct, simple, self-contained Python implementing the same
  function name and signature. Correctness matters more than speed. It is hidden from the user.
- Every expected value must be exactly what a correct solution returns. They are
  automatically verified by running your reference solution.
- `title`: short, in the language of the description. `slug`: short kebab-case English.
- `constraints`: 2-5 short strings (e.g. "1 <= len(nums) <= 10^4") consistent with the tests.
- `assumptions`: interpretations you made where the description was ambiguous or silent
  (e.g. what to return for empty input), in the language of the description. [] if none.
{feedback}"""

FEEDBACK = """
IMPORTANT: a previous attempt was rejected because the expected values disagreed with its own
reference solution on these cases:
{mismatches}
Re-derive the answers carefully from the description, and make sure the reference solution and
every expected value agree.
"""


class GenerationError(Exception):
    pass


def _claude_cmd(schema: dict):
    exe = shutil.which("claude")
    if not exe:
        raise GenerationError("The 'claude' CLI was not found on PATH. Install Claude Code and log in.")
    cmd = [exe, "-p", "--output-format", "json", "--tools", "", "--no-session-persistence",
           "--json-schema", json.dumps(schema)]
    model = os.environ.get("MYLEET_MODEL")
    if model:
        cmd += ["--model", model]
    return cmd


def ask_claude(prompt: str, schema: dict = SCHEMA, timeout: int = CLAUDE_TIMEOUT_SEC) -> dict:
    # Run outside the project so this project's CLAUDE.md (which forbids writing solutions)
    # does not apply to the reference-solution generation.
    with tempfile.TemporaryDirectory() as tmp:
        try:
            proc = subprocess.run(_claude_cmd(schema), input=prompt, capture_output=True, text=True,
                                  encoding="utf-8", cwd=tmp, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise GenerationError("Claude took too long to respond. Try again.")
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise GenerationError(f"Unexpected output from Claude:\n{(proc.stderr or proc.stdout)[-2000:]}")
    if data.get("is_error") or not data.get("structured_output"):
        raise GenerationError(f"Claude returned an error: {data.get('result') or data.get('subtype')}")
    return data["structured_output"]


def _validate(gen: dict):
    """Runs the reference solution on all cases. Returns list of mismatch dicts."""
    cases = [{"name": f"example_{i + 1}", "args": e["args"], "expected": e["expected"]}
             for i, e in enumerate(gen["examples"])] + gen["tests"]
    with tempfile.TemporaryDirectory() as tmp:
        ref = Path(tmp) / "reference.py"
        ref.write_text(gen["reference_solution"], encoding="utf-8")
        res = core.run_tests(ref, cases, gen["function_name"], gen["compare"], timeout=30)
    if res["fatal"]:
        return [{"name": "*", "problem": "reference solution failed to load: " + res["fatal"]}]
    bad = []
    for r in res["results"]:
        if r["status"] != "pass":
            bad.append({"name": r["name"], "args": r["args"], "expected": r["expected"],
                        "reference_returned": r.get("actual"), "error": r.get("error")})
    return bad


def generate(description: str, title: str = "") -> str:
    """Creates a new problem folder and returns its slug."""
    description = description.strip()
    if not description:
        raise GenerationError("Problem description is empty.")
    title_hint = f"\nThe user wants this title: {title.strip()}\n" if title.strip() else ""
    feedback = ""
    for attempt in range(MAX_ATTEMPTS):
        gen = ask_claude(PROMPT.format(description=description, title_hint=title_hint, feedback=feedback))
        if title.strip():
            gen["title"] = title.strip()
        bad = _validate(gen)
        if not bad:
            break
        feedback = FEEDBACK.format(mismatches=json.dumps(bad, ensure_ascii=False, indent=1)[:6000])

    warnings = []
    if bad:
        if any(b["name"] == "*" or b["name"].startswith("example_") for b in bad):
            raise GenerationError("Claude could not produce consistent examples for this problem. "
                                  "Try making the description more precise.")
        dropped = {b["name"] for b in bad}
        gen["tests"] = [t for t in gen["tests"] if t["name"] not in dropped]
        warnings.append(f"{len(dropped)} generated tests were dropped because they disagreed "
                        f"with the reference solution.")
    return core.save_problem(gen, description, warnings, datetime.now().isoformat(timespec="seconds"))
