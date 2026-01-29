from apply_patch_py.parser import PatchParser
from apply_patch_py.models import AddFile


def test_add_file_with_diff_content():
    """
    Verify that we can add a file whose content looks like a diff.
    The format requires lines to start with '+'.
    If the content line itself starts with '+', it should appear as '++' in the patch.
    """
    patch_text = """*** Begin Patch
*** Add File: test.diff
++line_starting_with_plus
+-line_starting_with_minus
+ normal_line
*** End Patch"""

    # If the file content is "-line", the patch line is "+-line".
    # If the file content is "+line", the patch line is "++line".

    parser = PatchParser()
    patch = parser.parse(patch_text)

    assert len(patch.hunks) == 1
    hunk = patch.hunks[0]
    assert isinstance(hunk, AddFile)

    lines = hunk.content.splitlines()

    # We expect '++' to become '+'
    assert lines[0] == "+line_starting_with_plus"
    assert lines[1] == "-line_starting_with_minus"
    assert lines[2] == " normal_line"


def test_add_file_creating_udiff():
    """Test creating a file that is itself a patch file (udiff)."""
    patch_text = """*** Begin Patch
*** Add File: change.patch
+--- a.py
++++ b.py
+@@ -1,1 +1,1 @@
+-old
++new
*** End Patch"""

    parser = PatchParser()
    patch = parser.parse(patch_text)
    hunk = patch.hunks[0]

    expected = "--- a.py\n+++ b.py\n@@ -1,1 +1,1 @@\n-old\n+new\n"
    assert hunk.content == expected
