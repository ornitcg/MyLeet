"""Runs a solution file against a tests file in an isolated subprocess.

Usage: python -I runner.py <solution.py> <tests.json> <function_name> <compare>

Prints one JSON object per line to stdout:
  {"fatal": "<traceback>"}                           -- solution failed to load
  {"i": 0, "status": "pass"|"fail"|"error", ...}     -- one line per test
Lines are flushed immediately so the parent can recover partial results on timeout.
"""
import contextlib
import copy
import importlib.util
import io
import json
import math
import sys
import time
import traceback

FLOAT_TOL = 1e-6


def to_jsonable(value):
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else repr(value)
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, (set, frozenset)):
        items = [to_jsonable(v) for v in value]
        return sorted(items, key=lambda x: json.dumps(x, sort_keys=True))
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    return repr(value)


def _sort_key(x):
    return json.dumps(x, sort_keys=True)


def _float_eq(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(a, b, rel_tol=FLOAT_TOL, abs_tol=FLOAT_TOL)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_float_eq(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_float_eq(a[k], b[k]) for k in a)
    return a == b


def matches(actual, expected, mode):
    """actual/expected are already JSON-normalized."""
    if mode == "float":
        return _float_eq(actual, expected)
    if mode in ("unordered", "unordered_nested") and isinstance(actual, list) and isinstance(expected, list):
        if mode == "unordered_nested":
            norm = lambda lst: sorted(
                (sorted(x, key=_sort_key) if isinstance(x, list) else x for x in lst), key=_sort_key
            )
        else:
            norm = lambda lst: sorted(lst, key=_sort_key)
        return norm(actual) == norm(expected)
    return actual == expected


def user_traceback(tb: str, solution_path: str) -> str:
    """Drop runner/importlib frames: keep only the part that starts in the user's code."""
    idx = tb.find(f'File "{solution_path}"')
    return "Traceback (most recent call last):\n  " + tb[idx:] if idx != -1 else tb


def emit(obj):
    sys.__stdout__.write(json.dumps(obj) + "\n")
    sys.__stdout__.flush()


def main():
    solution_path, tests_path, func_name, mode = sys.argv[1:5]
    with open(tests_path, encoding="utf-8") as f:
        tests = json.load(f)

    try:
        spec = importlib.util.spec_from_file_location("solution", solution_path)
        module = importlib.util.module_from_spec(spec)
        with contextlib.redirect_stdout(io.StringIO()):
            spec.loader.exec_module(module)
        func = getattr(module, func_name)
    except AttributeError:
        emit({"fatal": f"Function '{func_name}' was not found in the solution."})
        return
    except SyntaxError as e:
        emit({"fatal": "".join(traceback.format_exception_only(e))})
        return
    except BaseException:
        emit({"fatal": user_traceback(traceback.format_exc(), solution_path)})
        return

    for i, test in enumerate(tests):
        out = io.StringIO()
        start = time.perf_counter()
        try:
            with contextlib.redirect_stdout(out):
                result = func(**copy.deepcopy(test["args"]))
            ms = (time.perf_counter() - start) * 1000
            actual = to_jsonable(result)
            ok = matches(actual, to_jsonable(test["expected"]), mode)
            emit({"i": i, "status": "pass" if ok else "fail", "actual": actual,
                  "stdout": out.getvalue()[-4000:], "ms": round(ms, 2)})
        except BaseException:
            tb = traceback.format_exc()
            # Drop runner frames: keep only the part that starts in the user's code.
            marker = f'File "{solution_path}"'
            idx = tb.find(marker)
            if idx != -1:
                tb = "Traceback (most recent call last):\n  " + tb[idx:]
            emit({"i": i, "status": "error", "error": tb[-4000:],
                  "stdout": out.getvalue()[-4000:],
                  "ms": round((time.perf_counter() - start) * 1000, 2)})


if __name__ == "__main__":
    main()
