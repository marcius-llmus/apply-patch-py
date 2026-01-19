import os
import difflib
from pathlib import Path
import shutil

import pytest
from pydantic import BaseModel
from pydantic_ai import Agent, RunContext, Tool

from apply_patch_py import apply_patch as apply_patch_api
from apply_patch_py.utils import (
    get_patch_format_instructions,
    get_patch_format_tool_instructions,
)

from providers import ANTHROPIC_SPEC, GEMINI_SPEC, OPENAI_SPEC


class ApplyPatchResult(BaseModel):
    exit_code: int


def _apply_patch_test_system_prompt() -> str:
    return (
        "You are given a tool to apply patches to a working directory. "
        "Always generate a patch that follows these exact instructions:\n\n"
        f"{get_patch_format_instructions()}\n\n"
        "Call the tool exactly once."
    )


HEAVY_PATCH_PROMPT = '''\
You must produce a single patch that updates exactly one file:

tests/integration/fixture/dirty_script.py

You are also given the EXACT current contents of the file below.
Do not invent or paraphrase any existing lines.
When writing the patch, the removed (-) lines MUST match the file content exactly.

BEGIN_FILE_CONTENT
___FILE_CONTENT___
END_FILE_CONTENT

Make ALL of the following edits in ONE patch. The patch must be minimal and precise, and the resulting file must still import.

### A) Constants / globals (near file top; close hunk #1)
1) Change:
VERSION="0.0.0-dev"
to:
VERSION="0.1.0-int"

2) Immediately after the line:
MAGIC_NUMBER=   42
insert this new constant (preserve the “weird spacing vibe”, don’t “prettify” other lines):
PATCH_TEST_TAG = "integration-heavy"

3) Replace the _WEIRD_UNICODE string to include an extra marker at the end (keep it one line):
- Append exactly:  ::PATCHER::
So the final string value must end with " ::PATCHER::".

### B) Helpers section (close hunk #2)
1) Replace the one-liner function:
def _now_iso()->str: return dt.datetime.now(dt.timezone.utc).isoformat()
with a multi-line version:

def _now_iso() -> str:
    now = dt.datetime.now(dt.timezone.utc)
    return now.isoformat()

2) Fix sloppy_join indentation to 4 spaces but keep the comment line exactly.

3) Add a brand new helper right after normalize_spaces:

def stable_hash(text: str) -> str:
    """Return a deterministic short hash for text (not cryptographic)."""
    return hex(abs(hash(text)) % (1 << 32))[2:].rjust(8, "0")

### C) Big chunk replacement inside compute_something_big (mid-file; big block swap)
Inside compute_something_big, replace the entire body (everything inside the function) with the following new body exactly:

    data: Dict[str, Any] = {}
    data["n"] = n

    safe_n = clamp(n, 0, 500)
    data["fib"] = fibonacci(clamp(n, 0, 30))
    data["primes"] = primes_upto(safe_n)

    values = [float(x) for x in range(safe_n)]
    data["mean"] = mean_or_nan(values)

    # add extra diagnostics to increase content size
    data["min"] = min(values) if values else float("nan")
    data["max"] = max(values) if values else float("nan")
    data["sum"] = sum(values) if values else 0.0

    # repeated-pattern anchors
    data["evens"] = [x for x in range(safe_n) if x % 2 == 0]
    data["odds"] = [x for x in range(safe_n) if x % 2 == 1]

    text = f"n={n} safe_n={safe_n}"
    data["hash"] = stable_hash(text)
    data["meta"] = {"version": VERSION, "tag": PATCH_TEST_TAG}

    return data

Do not change the function signature or decorator.

### D) Big LOREM constant replacement (mid-file; huge block deletion/replace)
Replace the entire triple-quoted LOREM = """ ... """ block with this single line:
LOREM = "LOREM_REMOVED_FOR_TESTING"

### E) Duplication and shadowing section (repeated-content hazard)
1) Rename the class definition line exactly from:
class process:  # noqa: N801 intentionally shadowing
to:
class ProcessCallable:  # noqa: N801 intentionally shadowing

2) Update its __call__ method to return:
return f"ProcessCallable({self.x})"

(Do not rename the two "def process" functions above it.)

### F) Insert a large new block (>20 lines) in “more classes for anchors”
Insert this class immediately before class ReportBuilder:

class PatchTestSentinel:
    def __init__(self, value: str):
        self.value = value
        self.created_at = _now_iso()

    def render(self) -> str:
        return f"[sentinel]{self.value}"

    def as_event(self) -> Event:
        return Event.now(
            "sentinel",
            {
                "value": self.value,
                "created_at": self.created_at,
                "tag": PATCH_TEST_TAG,
                "unicode": _WEIRD_UNICODE,
            },
        )

    def as_json(self) -> str:
        payload = {
            "value": self.value,
            "created_at": self.created_at,
            "tag": PATCH_TEST_TAG,
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

### G) Bottom filler section: large deletions + insertion with ordering constraints
1) Delete functions filler_020 through filler_030 inclusive.

2) After:
def filler_050(): return "050"
insert:
def filler_050b(): return "050b"

3) Replace the block of functions filler_071 through filler_080 inclusive with this exact 20-line block:

def filler_071(): return "071"
def filler_072(): return "072"
def filler_073(): return "073"
def filler_074(): return "074"
def filler_075(): return "075"
def filler_076(): return "076"
def filler_077(): return "077"
def filler_078(): return "078"
def filler_079(): return "079"
def filler_080(): return "080"

def filler_bigblock_001(): return "BIG001"
def filler_bigblock_002(): return "BIG002"
def filler_bigblock_003(): return "BIG003"
def filler_bigblock_004(): return "BIG004"
def filler_bigblock_005(): return "BIG005"
def filler_bigblock_006(): return "BIG006"
def filler_bigblock_007(): return "BIG007"
def filler_bigblock_008(): return "BIG008"
def filler_bigblock_009(): return "BIG009"
def filler_bigblock_010(): return "BIG010"

### H) Add an end-of-file addition (EOF marker behavior)
At the very end of the file (after the last filler function), append:
# patcher_eof_marker: keep this line at EOF

Strictness rules:
- Update only tests/integration/fixture/dirty_script.py
- Do not modify any other files.
- Do not change unrelated spacing except where explicitly instructed.
- Keep the file importable and syntactically valid.

Return only the patch in the required patch format.
'''


def _assert_contains_all(haystack: str, needles: list[str]) -> None:
    missing = [n for n in needles if n not in haystack]
    assert not missing, "Missing expected substrings:\n" + "\n".join(
        f"- {m}" for m in missing
    )


def _assert_not_contains_any(haystack: str, needles: list[str]) -> None:
    present = [n for n in needles if n in haystack]
    assert not present, "Unexpected substrings present:\n" + "\n".join(
        f"- {p}" for p in present
    )


def _assert_contains_ordered(haystack: str, needles: list[str]) -> None:
    last = -1
    for n in needles:
        idx = haystack.find(n)
        assert idx != -1, f"Expected substring not found: {n!r}"
        assert idx > last, f"Expected substring order violated for: {n!r}"
        last = idx


async def apply_patch_tool(ctx: RunContext[Path], patch: str) -> int:  # noqa
    """Apply a patch to the current workspace.

    Args:
        patch: The patch text to apply.
            Must follow these instructions exactly:
            {get_patch_format_instructions()}
    """

    affected = await apply_patch_api(patch, workdir=ctx.deps)
    return 0 if affected.success else 1


APPLY_PATCH_TOOL = Tool(
    apply_patch_tool,
    takes_ctx=True,
    docstring_format="google",
    require_parameter_descriptions=True,
    description=get_patch_format_tool_instructions(),
)


def _heavy_patch_test_user_prompt() -> str:
    fixture_path = Path("tests/integration/fixture/dirty_script.py")
    file_content = fixture_path.read_text(encoding="utf-8")
    return HEAVY_PATCH_PROMPT.replace("___FILE_CONTENT___", str(file_content))


def _heavy_patch_test_system_prompt() -> str:
    return (
        _apply_patch_test_system_prompt()
        + "\n\n"
        + "You must edit exactly one file, and it must already exist in the workspace."
    )


def _prepare_dirty_fixture(tmp_path: Path) -> Path:
    src = Path("tests/integration/fixture/dirty_script.py")
    dest = tmp_path / "tests/integration/fixture/dirty_script.py"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    return dest


def _assert_dirty_fixture_before(before: str) -> None:
    _assert_contains_all(
        before,
        [
            'VERSION="0.0.0-dev"',
            "MAGIC_NUMBER=   42",
            '_WEIRD_UNICODE = "café—naïve–coöperate… “quotes” ‘single’ — minus − and hyphen‐"',
            "def _now_iso()->str: return dt.datetime.now(dt.timezone.utc).isoformat()",
            'def sloppy_join(items, sep=","):',
            "# intentionally wrong indentation",
            "return sep.join([str(x) for x in items])",
            "@timing",
            "def compute_something_big(n: int) -> Dict[str, Any]:",
            'data["evens"]=[x for x in range(n) if x%2==0]',
            "class process:  # noqa: N801 intentionally shadowing",
            'return f"process({self.x})"',
            'LOREM = """',
            '""".strip()',
            "class ReportBuilder:",
            'def filler_020(): return "020"',
            'def filler_030(): return "030"',
            'def filler_050(): return "050"',
            'def filler_071(): return "071"',
            'def filler_080(): return "080"',
        ],
    )


def _assert_dirty_fixture_after(after: str) -> None:
    _assert_contains_all(
        after,
        [
            'VERSION="0.1.0-int"',
            'PATCH_TEST_TAG = "integration-heavy"',
            "::PATCHER::",
            "def _now_iso() -> str:",
            "now = dt.datetime.now(dt.timezone.utc)",
            "return now.isoformat()",
            "def stable_hash(text: str) -> str:",
            "Return a deterministic short hash for text (not cryptographic).",
            "data: Dict[str, Any] = {}",
            "safe_n = clamp(n, 0, 500)",
            'data["odds"] = [x for x in range(safe_n) if x % 2 == 1]',
            'data["meta"] = {"version": VERSION, "tag": PATCH_TEST_TAG}',
            'LOREM = "LOREM_REMOVED_FOR_TESTING"',
            "class ProcessCallable:  # noqa: N801 intentionally shadowing",
            'return f"ProcessCallable({self.x})"',
            "class PatchTestSentinel:",
            "def as_event(self) -> Event:",
            "return json.dumps(payload, ensure_ascii=False, sort_keys=True)",
            'def filler_050b(): return "050b"',
            'def filler_bigblock_010(): return "BIG010"',
            "# patcher_eof_marker: keep this line at EOF",
        ],
    )

    _assert_not_contains_any(
        after,
        [
            'VERSION="0.0.0-dev"',
            "def _now_iso()->str: return dt.datetime.now(dt.timezone.utc).isoformat()",
            'LOREM = """',
            '""".strip()',
            "class process:  # noqa: N801 intentionally shadowing",
            'return f"process({self.x})"',
            'def filler_020(): return "020"',
            'def filler_030(): return "030"',
            'def filler_021(): return "021"',
            'def filler_029(): return "029"',
        ],
    )

    # Ordering constraints
    idx_050 = after.find('def filler_050(): return "050"')
    idx_050b = after.find('def filler_050b(): return "050b"')
    assert idx_050 != -1 and idx_050b != -1 and idx_050b > idx_050

    assert after.rstrip().endswith("# patcher_eof_marker: keep this line at EOF")


@pytest.mark.integration
@pytest.mark.parametrize(
    "model",
    [
        pytest.param(
            OPENAI_SPEC.model,
            marks=pytest.mark.skipif(
                not os.getenv(OPENAI_SPEC.required_env),
                reason=f"missing {OPENAI_SPEC.required_env}",
            ),
            id=OPENAI_SPEC.name,
        ),
        pytest.param(
            ANTHROPIC_SPEC.model,
            marks=pytest.mark.skipif(
                not os.getenv(ANTHROPIC_SPEC.required_env),
                reason=f"missing {ANTHROPIC_SPEC.required_env}",
            ),
            id=ANTHROPIC_SPEC.name,
        ),
        pytest.param(
            GEMINI_SPEC.model,
            marks=pytest.mark.skipif(
                not os.getenv(GEMINI_SPEC.required_env),
                reason=f"missing {GEMINI_SPEC.required_env}",
            ),
            id=GEMINI_SPEC.name,
        ),
    ],
)
def test_llm_heavy_patch_dirty_file(tmp_path, model):
    workdir = tmp_path
    dirty_path = _prepare_dirty_fixture(workdir)
    before = dirty_path.read_text(encoding="utf-8")
    _assert_dirty_fixture_before(before)

    agent = Agent(  # noqa
        model,
        deps_type=Path,
        output_type=ApplyPatchResult,
        tools=[APPLY_PATCH_TOOL],
        system_prompt=_heavy_patch_test_system_prompt(),
    )

    result = agent.run_sync(_heavy_patch_test_user_prompt(), deps=workdir)
    assert result.output.exit_code == 0

    after = dirty_path.read_text(encoding="utf-8")
    try:
        _assert_dirty_fixture_after(after)
    except AssertionError:
        # Include a compact diff to help diagnose which edit didn't apply.
        diff = "\n".join(
            difflib.unified_diff(
                before.splitlines(),
                after.splitlines(),
                fromfile="before",
                tofile="after",
                lineterm="",
                n=2,
            )
        )
        raise AssertionError(
            "Post-patch assertions failed. Diff (before -> after):\n" + diff
        )
