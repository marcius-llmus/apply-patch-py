from pathlib import Path

import pytest

from apply_patch_py.parser import PatchParser
from apply_patch_py.models import AddFile, DeleteFile, UpdateFile


def _parse(text: str):
    return PatchParser().parse(text)


def _assert_is_add_file(hunk, path: str, *, contains: list[str] | None = None):
    assert isinstance(hunk, AddFile)
    assert hunk.path == Path(path)
    if contains:
        for needle in contains:
            assert needle in hunk.content


def test_parser_recovers_from_prefixed_headers():
    """
    Test that the parser correctly handles cases where an LLM prefixes '*** Update File:'
    with a '+' inside an '*** Add File:' block, instead of consuming it as file content.
    """
    patch_text = """*** Begin Patch
*** Add File: src/settings.py
+import pygame
+
+# Colors
+COLOR_BG = (13, 16, 33)
+
+*** Update File: src/main.py
@@ def main() -> None:
-    Game().run()
+    from src.game import Game
+    Game().run()
*** End Patch
"""
    patch = _parse(patch_text)

    assert len(patch.hunks) == 2

    # Check first hunk (Add File)
    _assert_is_add_file(patch.hunks[0], "src/settings.py", contains=["COLOR_BG"])
    # Crucially, the content should NOT contain the Update File header
    assert "*** Update File" not in patch.hunks[0].content

    # Check second hunk (Update File)
    assert isinstance(patch.hunks[1], UpdateFile)
    assert patch.hunks[1].path == Path("src/main.py")
    assert len(patch.hunks[1].chunks) == 1
    assert patch.hunks[1].chunks[0].change_context == "def main() -> None:"


def test_parser_accepts_prefixed_top_level_hunk_header():
    """LLMs sometimes prefix the top-level hunk header itself with '+'.

    We accept this (conservatively) because the header is unambiguous and otherwise
    causes hard-to-understand failures.
    """

    patch_text = """*** Begin Patch
++*** Update File: src/main.py
++@@ def main() -> None:
+-    Game().run()
++    from src.game import Game
++    Game().run()
*** End Patch
"""

    patch = _parse(patch_text)
    assert len(patch.hunks) == 1
    assert isinstance(patch.hunks[0], UpdateFile)
    assert patch.hunks[0].path == Path("src/main.py")
    assert patch.hunks[0].chunks[0].change_context == "def main() -> None:"


def test_parser_handles_prefixed_context_marker():
    """
    Test that the parser handles '@@' markers prefixed with '+' inside an Update File block.
    """
    patch_text = """*** Begin Patch
*** Update File: src/main.py
+@@ def main() -> None:
-    Game().run()
+    from src.game import Game
+    Game().run()
*** End Patch
"""
    patch = _parse(patch_text)

    assert len(patch.hunks) == 1
    assert isinstance(patch.hunks[0], UpdateFile)
    chunk = patch.hunks[0].chunks[0]
    assert chunk.change_context == "def main() -> None:"
    assert chunk.old_lines == ["    Game().run()"]
    assert chunk.new_lines == ["    from src.game import Game", "    Game().run()"]


def test_parser_accepts_prefixed_empty_context_marker():
    """Accept '+@@' where the intended marker is '@@' (empty context)."""

    patch_text = """*** Begin Patch
*** Update File: src/main.py
++@@
++line
*** End Patch
"""
    patch = _parse(patch_text)
    assert len(patch.hunks) == 1
    assert isinstance(patch.hunks[0], UpdateFile)
    assert patch.hunks[0].chunks[0].change_context is None


def test_parser_accepts_numeric_unified_diff_range_header_as_no_context():
    """Gemini-style '-1,2 +1,3 @@' should be treated as no change_context."""

    patch_text = """*** Begin Patch
*** Update File: src/main.py
@@ -21,6 +21,7 @@
-before
+after
*** End Patch
"""
    patch = _parse(patch_text)
    chunk = patch.hunks[0].chunks[0]
    assert chunk.change_context is None
    assert chunk.old_lines == ["before"]
    assert chunk.new_lines == ["after"]


def test_parser_handles_prefixed_end_patch_inside_add_file():
    """
    Test that the parser stops consuming Add File content if it encounters '+*** End Patch'
    and does not treat it as literal file content.
    """

    # Make the overall patch valid by including a real final END_PATCH marker.
    patch_text = """*** Begin Patch
*** Add File: new_file.txt
+some content
++*** End Patch
*** End Patch
"""

    patch = _parse(patch_text)
    assert len(patch.hunks) == 1
    _assert_is_add_file(patch.hunks[0], "new_file.txt", contains=["some content"])
    assert patch.hunks[0].content.splitlines() == ["some content"]


def test_parser_accepts_trailing_prefixed_end_patch():
    """If the very last line is '+*** End Patch', _coerce_llm_patch should fix it."""

    patch_text = """*** Begin Patch
*** Add File: new_file.txt
+some content
+*** End Patch
"""
    patch = _parse(patch_text)
    assert len(patch.hunks) == 1
    assert isinstance(patch.hunks[0], AddFile)


def test_parser_parses_multiple_hunks_with_blank_lines_between():
    """Blank lines between hunks should be tolerated."""

    patch_text = """*** Begin Patch
*** Add File: a.txt
+ a
+
*** Delete File: b.txt
*** End Patch
"""
    patch = _parse(patch_text)
    assert len(patch.hunks) == 2
    assert isinstance(patch.hunks[0], AddFile)
    assert isinstance(patch.hunks[1], DeleteFile)


def test_parser_add_file_stops_on_unprefixed_next_header():
    """Add File should stop when the next hunk header begins (unprefixed)."""

    patch_text = """*** Begin Patch
*** Add File: a.txt
+line1
*** Add File: b.txt
+line2
*** End Patch
"""
    patch = _parse(patch_text)
    assert len(patch.hunks) == 2
    _assert_is_add_file(patch.hunks[0], "a.txt", contains=["line1"])
    _assert_is_add_file(patch.hunks[1], "b.txt", contains=["line2"])


# Regression: normal '+***' content that is NOT a patch header must remain content.
def test_parser_add_file_allows_literal_stars_not_a_header():
    """Regression: normal '+***' content that is NOT a patch header must remain content."""

    patch_text = """*** Begin Patch
*** Add File: a.txt
+*** this is not a header
+*** neither is this: *** Totally Not A Header
*** End Patch
"""
    patch = _parse(patch_text)
    assert len(patch.hunks) == 1
    assert isinstance(patch.hunks[0], AddFile)
    assert "*** this is not a header" in patch.hunks[0].content


def test_parser_recovers_missing_begin_patch():
    patch_text = """*** Add File: a.txt
+x
"""
    patch = _parse(patch_text)
    assert len(patch.hunks) == 1
    assert isinstance(patch.hunks[0], AddFile)


def test_parser_rejects_non_patch_blob():
    patch_text = """hello
world
"""
    with pytest.raises(ValueError):
        _parse(patch_text)
