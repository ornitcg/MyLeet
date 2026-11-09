"""Reviews an accepted solution with Claude: complexity, short feedback, and a better approach
described in words only (never code)."""
import re

from . import core
from .generator import GenerationError, ask_claude

REVIEW_TIMEOUT_SEC = 240

SCHEMA = {
    "type": "object",
    "properties": {
        "time_complexity": {"type": "string"},
        "space_complexity": {"type": "string"},
        "feedback": {"type": "string"},
        "has_better_approach": {"type": "boolean"},
        "better_approach": {"type": "string"},
        "better_time_complexity": {"type": "string"},
        "better_space_complexity": {"type": "string"},
    },
    "required": ["time_complexity", "space_complexity", "feedback", "has_better_approach",
                 "better_approach", "better_time_complexity", "better_space_complexity"],
}

PROMPT = """You are reviewing a student's ACCEPTED solution (it passes all tests) to a practice problem.

<problem>
{description}
</problem>
Function signature: {signature}

<student_solution>
{code}
</student_solution>

Return the structured output:
- `time_complexity`, `space_complexity`: Big-O of the student's solution, e.g. "O(n log n)".
- `feedback`: 2-3 short sentences in Hebrew: what is good, and what could be clearer or
  more idiomatic (naming, structure, edge cases). Be encouraging and specific.
- `has_better_approach`: true ONLY if a solution with strictly better time complexity exists,
  or the same time with clearly better space complexity. Otherwise false.
- `better_approach`: if true, 2-4 sentences in Hebrew describing the IDEA of the better
  approach (which technique / data structure, and the key insight). If false, "".
- `better_time_complexity`, `better_space_complexity`: Big-O of that approach, or "" if none.

STRICT RULE: do NOT write any code, pseudo-code, function names with arguments, or code
snippets anywhere. Describe ideas in words only. The student wants to implement it alone.
"""

_CODE_LINE = re.compile(r"^\s*(def |class |for |while |if |elif |else:|return |import |from \S+ import )")


def _strip_code(text: str) -> str:
    """Safety net: remove anything that looks like code even if the model ignored the rule."""
    text = re.sub(r"```.*?(```|$)", "", text, flags=re.S)
    text = re.sub(r"`([^`]{40,})`", "", text)
    lines = [ln for ln in text.splitlines() if not _CODE_LINE.match(ln)]
    return "\n".join(lines).strip()


def review_submission(slug: str, sub_id: str) -> dict:
    """Returns the review for a saved accepted solution, generating and caching it if needed."""
    sub = core.get_submission(slug, sub_id)
    if sub["kind"] != "accepted":
        raise ValueError("Only solutions that passed all tests can be reviewed.")
    if sub.get("review"):
        return sub["review"]
    p = core.load_problem(slug)
    raw = ask_claude(PROMPT.format(description=p["description"], signature=p["signature"],
                                   code=sub["code"]), schema=SCHEMA, timeout=REVIEW_TIMEOUT_SEC)
    review = {k: _strip_code(v) if isinstance(v, str) else v for k, v in raw.items()}
    if review["has_better_approach"] and not review["better_approach"]:
        review["has_better_approach"] = False
    core.set_submission_review(slug, sub_id, review)
    return review


__all__ = ["review_submission", "GenerationError"]
