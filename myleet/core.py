"""Problem storage and test execution."""
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime
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
    p["submissions"] = list_submissions(slug)
    p["slug"] = slug
    return p


def rename_problem(slug: str, title: str):
    """Changes the display title only; the folder name (slug) stays the same."""
    title = " ".join(title.split())[:120]
    if not title:
        raise ValueError("title is empty")
    meta = problem_dir(slug) / "problem.json"
    p = _read_json(meta)
    p["title"] = title
    _write_json(meta, p)
    return title


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


# ---------- saved solutions (submission history) ----------
SUBMISSION_ID_RE = re.compile(r"^\d{8}-\d{6}(-\d+)?$")


def _submissions_dir(slug: str) -> Path:
    return problem_dir(slug) / "submissions"


def list_submissions(slug: str):
    index = _submissions_dir(slug) / "index.json"
    items = _read_json(index) if index.exists() else []
    return sorted(items, key=lambda s: s["id"], reverse=True)


def get_submission(slug: str, sub_id: str):
    if not SUBMISSION_ID_RE.match(sub_id):
        raise ValueError("invalid submission id")
    entry = next((s for s in list_submissions(slug) if s["id"] == sub_id), None)
    if entry is None:
        raise FileNotFoundError(sub_id)
    code = (_submissions_dir(slug) / f"{sub_id}.py").read_text(encoding="utf-8")
    return {**entry, "code": code}


def add_submission(slug: str, code: str, kind: str, note: str = "", passed=None, total=None):
    """kind: "manual" (saved by the user) or "accepted" (all tests passed)."""
    if not problem_dir(slug).exists():
        raise FileNotFoundError(slug)
    d = _submissions_dir(slug)
    d.mkdir(exist_ok=True)
    now = datetime.now()
    base = now.strftime("%Y%m%d-%H%M%S")
    sub_id, n = base, 2
    while (d / f"{sub_id}.py").exists():
        sub_id, n = f"{base}-{n}", n + 1
    (d / f"{sub_id}.py").write_text(code, encoding="utf-8")
    entry = {"id": sub_id, "created": now.isoformat(timespec="seconds"), "kind": kind,
             "note": note.strip()[:200], "passed": passed, "total": total}
    items = list_submissions(slug)
    items.append(entry)
    _write_json(d / "index.json", sorted(items, key=lambda s: s["id"]))
    return entry


def set_submission_review(slug: str, sub_id: str, review: dict):
    index = _submissions_dir(slug) / "index.json"
    items = _read_json(index)
    for s in items:
        if s["id"] == sub_id:
            s["review"] = review
    _write_json(index, items)


def _latest_accepted(slug: str):
    """Returns (entry, code) of the most recent accepted submission, or (None, None)."""
    for s in list_submissions(slug):
        if s["kind"] == "accepted":
            return s, (_submissions_dir(slug) / f"{s['id']}.py").read_text(encoding="utf-8")
    return None, None


def run_user_code(slug: str, code: str, scope: str):
    d = problem_dir(slug)
    save_code(slug, code)
    p = _read_json(d / "problem.json")
    tests = _read_json(d / "tests.json")
    if scope == "examples":
        tests = tests[: len(p["examples"])]
    res = run_tests(d / "solution.py", tests, p["function_name"], p["compare"])
    passed = sum(r["status"] == "pass" for r in res["results"])
    res.update(passed=passed, total=len(tests), scope=scope, saved_submission=None, accepted_submission=None)
    if scope == "all" and passed == len(tests):
        if not p.get("solved"):
            p["solved"] = True
            _write_json(d / "problem.json", p)
        # Keep every distinct accepted solution; reuse the latest one if the code is identical
        # (so its saved review, if any, is reused too).
        latest, latest_code = _latest_accepted(slug)
        if latest_code == code:
            res["accepted_submission"] = latest
        else:
            entry = add_submission(slug, code, "accepted", passed=passed, total=len(tests))
            res["saved_submission"] = res["accepted_submission"] = entry
    return res
