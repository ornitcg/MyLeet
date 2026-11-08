"""Problem storage and test execution."""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROBLEMS_DIR = ROOT / "problems"
RUNNER = Path(__file__).resolve().parent / "runner.py"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}$")
RUN_TIMEOUT_SEC = 10


def problem_dir(slug: str) -> Path:
    if not SLUG_RE.match(slug):
        raise ValueError("invalid slug")
    return PROBLEMS_DIR / slug


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def list_problems():
    PROBLEMS_DIR.mkdir(exist_ok=True)
    items = []
    for d in PROBLEMS_DIR.iterdir():
        meta = d / "problem.json"
        if d.is_dir() and meta.exists():
            p = _read_json(meta)
            items.append({"slug": d.name, "title": p["title"], "solved": p.get("solved", False),
                          "created": p.get("created", "")})
    items.sort(key=lambda x: x["created"], reverse=True)
    return items


def load_problem(slug: str):
    d = problem_dir(slug)
    p = _read_json(d / "problem.json")
    sol = d / "solution.py"
    p["code"] = sol.read_text(encoding="utf-8") if sol.exists() else p["stub"]
    p["test_count"] = len(_read_json(d / "tests.json"))
    p["slug"] = slug
    return p


def save_code(slug: str, code: str):
    (problem_dir(slug) / "solution.py").write_text(code, encoding="utf-8")


def save_problem(gen: dict, description: str, warnings: list, created: str) -> str:
    PROBLEMS_DIR.mkdir(exist_ok=True)
    base = re.sub(r"[^a-z0-9-]+", "-", gen["slug"].lower()).strip("-")[:60] or "problem"
    slug, n = base, 2
    while (PROBLEMS_DIR / slug).exists():
        slug, n = f"{base}-{n}", n + 1
    d = PROBLEMS_DIR / slug
    d.mkdir()
    _write_json(d / "problem.json", {
        "title": gen["title"],
        "description": description,
        "function_name": gen["function_name"],
        "signature": gen["signature"],
        "stub": gen["stub"],
        "compare": gen["compare"],
        "examples": gen["examples"],
        "constraints": gen.get("constraints", []),
        "assumptions": gen.get("assumptions", []),
        "warnings": warnings,
        "created": created,
        "solved": False,
    })
    tests = [{"name": f"example_{i + 1}", "args": e["args"], "expected": e["expected"]}
             for i, e in enumerate(gen["examples"])]
    tests += [{"name": t["name"], "args": t["args"], "expected": t["expected"]} for t in gen["tests"]]
    _write_json(d / "tests.json", tests)
    (d / "reference.py").write_text(gen["reference_solution"], encoding="utf-8")
    (d / "solution.py").write_text(gen["stub"], encoding="utf-8")
    return slug


def run_tests(solution_path: Path, tests: list, function_name: str, compare: str,
              timeout: float = RUN_TIMEOUT_SEC):
    """Returns {"fatal": str|None, "results": [...]} with one result per test."""
    with tempfile.TemporaryDirectory() as tmp:
        tests_file = Path(tmp) / "tests.json"
        _write_json(tests_file, tests)
        proc = subprocess.Popen(
            [sys.executable, "-I", str(RUNNER), str(solution_path), str(tests_file), function_name, compare],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=tmp, text=True, encoding="utf-8",
        )
        timed_out = False
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
            timed_out = True

    by_index, fatal = {}, None
    for line in out.splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "fatal" in obj:
            fatal = obj["fatal"]
        else:
            by_index[obj["i"]] = obj
    if not fatal and not by_index and not timed_out and proc.returncode != 0:
        fatal = err[-4000:] or f"Process exited with code {proc.returncode}"

    results, tle_marked = [], False
    for i, t in enumerate(tests):
        r = by_index.get(i)
        if r is None:
            if fatal:
                status, extra = "error", {}
            elif timed_out and not tle_marked:
                status, extra = "timeout", {"error": f"Time Limit Exceeded ({timeout:g}s)"}
                tle_marked = True
            else:
                status, extra = "skipped", {}
            r = {"status": status, **extra}
        r.update(name=t["name"], args=t["args"], expected=t["expected"])
        r.pop("i", None)
        results.append(r)
    return {"fatal": fatal, "results": results}


def run_user_code(slug: str, code: str, scope: str):
    d = problem_dir(slug)
    save_code(slug, code)
    p = _read_json(d / "problem.json")
    tests = _read_json(d / "tests.json")
    if scope == "examples":
        tests = tests[: len(p["examples"])]
    res = run_tests(d / "solution.py", tests, p["function_name"], p["compare"])
    passed = sum(r["status"] == "pass" for r in res["results"])
    res.update(passed=passed, total=len(tests), scope=scope)
    if scope == "all" and passed == len(tests) and not p.get("solved"):
        p["solved"] = True
        _write_json(d / "problem.json", p)
    return res
