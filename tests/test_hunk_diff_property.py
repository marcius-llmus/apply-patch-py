from pathlib import Path
from apply_patch_py.models import AddFile, UpdateFile, UpdateFileChunk


def test_add_file_diff_property():
    # Normal content
    af = AddFile(Path("new.txt"), "line1\nline2")
    assert af.diff == "+line1\n+line2\n"

    af_escaped = AddFile(Path("esc.txt"), "+line\n-line\n space")
    assert af_escaped.diff == "++line\n+-line\n+ space\n"


def test_update_file_diff_property_simple():
    # Simple replacement
    expected = "@@\n-old\n+new"
    chunk = UpdateFileChunk(
        diff=expected, old_lines=["old"], new_lines=["new"], change_context=None
    )
    uf = UpdateFile(Path("mod.txt"), chunks=[chunk])
    assert uf.diff == expected


def test_update_file_diff_property_context():
    # With context
    expected = "@@ def foo():\n ctx\n-old\n+new"
    chunk = UpdateFileChunk(
        diff=expected,
        old_lines=["ctx", "old"],
        new_lines=["ctx", "new"],
        change_context="def foo():",
    )
    uf = UpdateFile(Path("mod.py"), chunks=[chunk])
    assert uf.diff == expected


def test_update_file_diff_property_multiple_chunks():
    diff1 = "@@ ctx1\n-a\n+b\n"
    chunk1 = UpdateFileChunk(
        diff=diff1, old_lines=["a"], new_lines=["b"], change_context="ctx1"
    )
    diff2 = "@@ ctx2\n-c\n+d\n"
    chunk2 = UpdateFileChunk(
        diff=diff2, old_lines=["c"], new_lines=["d"], change_context="ctx2"
    )
    uf = UpdateFile(Path("multi.py"), chunks=[chunk1, chunk2])

    expected = diff1 + diff2
    assert uf.diff == expected
