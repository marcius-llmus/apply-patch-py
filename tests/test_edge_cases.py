import pytest

from apply_patch_py import apply_patch


async def test_apply_patch_pure_addition_uses_context(tmp_path):
    """
    If a hunk has a context header (@@ ...) and ONLY additions (no space/minus lines),
    it should insert the new lines AFTER the context line, not at the end of the file.
    """
    target = tmp_path / "target.py"
    target.write_text("def foo():\n    pass\n\ndef bar():\n    pass\n")

    # We want to insert '    print("foo")' inside foo(), using 'def foo():' as anchor.
    # This hunk has NO ' ' lines, so old_lines is empty.
    patch = """*** Begin Patch
*** Update File: target.py
@@ def foo():
+    print("foo")
*** End Patch"""

    await apply_patch(patch, workdir=tmp_path)

    content = target.read_text()

    expected_snippet = 'def foo():\n    print("foo")\n    pass'
    assert expected_snippet in content, f"Result was:\n{content}"
    # Ensure it wasn't appended to the end
    assert content.strip().endswith("pass")


async def test_apply_patch_multiple_pure_additions(tmp_path):
    """Test inserting lines into multiple different locations in the same file."""
    target = tmp_path / "multi.py"
    target.write_text("""
class A:
    def method_a(self):
        pass

class B:
    def method_b(self):
        pass
""".strip())

    patch = """*** Begin Patch
*** Update File: multi.py
@@ def method_a(self):
++        print("A")
@@ def method_b(self):
++        print("B")
*** End Patch"""

    await apply_patch(patch, workdir=tmp_path)
    content = target.read_text()

    assert 'def method_a(self):\n        print("A")\n        pass' in content
    assert 'def method_b(self):\n        print("B")\n        pass' in content


async def test_apply_patch_repeated_context(tmp_path):
    """Test that we advance the search index so we don't keep finding the first occurrence."""
    target = tmp_path / "repeated.py"
    target.write_text("""
def foo():
    return 1

def foo():
    return 1
""".strip())

    # We want to insert into the first foo, then the second foo.
    # Note: The applier searches from `line_index`.

    patch = """*** Begin Patch
*** Update File: repeated.py
@@ def foo():
-    return 1
+    return 11
@@ def foo():
-    return 1
+    return 12
*** End Patch"""

    await apply_patch(patch, workdir=tmp_path)
    content = target.read_text()

    # The file should look like:
    # def foo():
    #     return 11
    #
    # def foo():
    #     return 12

    parts = content.split("def foo():")
    # parts[0] is empty (before first def)
    # parts[1] is body of first
    # parts[2] is body of second

    assert "return 11" in parts[1]
    assert "return 12" in parts[2]


async def test_apply_patch_addition_no_context_appends(tmp_path):
    """Regression test: No context should still append to end."""
    target = tmp_path / "append.txt"
    target.write_text("line1\n")

    patch = """*** Begin Patch
*** Update File: append.txt
@@
++line2
*** End Patch"""

    await apply_patch(patch, workdir=tmp_path)
    content = target.read_text()
    assert content.strip() == "line1\nline2"


async def test_apply_patch_nested_class_context(tmp_path):
    """Test inserting code inside a nested class/method structure."""
    target = tmp_path / "nested.py"
    target.write_text("""
class Outer:
    class Inner:
        def method(self):
            return True
""".strip())

    patch = """*** Begin Patch
*** Update File: nested.py
@@ def method(self):
++            print("Executing method")
*** End Patch"""

    await apply_patch(patch, workdir=tmp_path)
    content = target.read_text()

    assert (
        'def method(self):\n            print("Executing method")\n            return True'
        in content
    )


async def test_apply_patch_interleaved_additions_and_updates(tmp_path):
    """Test mixing pure additions and standard replacements in one file."""
    target = tmp_path / "mixed.py"
    target.write_text("""
def a():
    return 1

def b():
    return 2

def c():
    return 3
""".strip())

    patch = """*** Begin Patch
*** Update File: mixed.py
@@ def a():
++    print("a")
@@ def b():
-    return 2
+    return 20
@@ def c():
++    print("c")
*** End Patch"""

    await apply_patch(patch, workdir=tmp_path)
    content = target.read_text()

    assert 'def a():\n    print("a")\n    return 1' in content
    assert "def b():\n    return 20" in content
    assert 'def c():\n    print("c")\n    return 3' in content


async def test_apply_patch_ambiguous_context_raises_error(tmp_path):
    """Test that we reject pure additions if the context matches multiple locations."""
    target = tmp_path / "ambiguous.py"
    target.write_text("""
def foo():
    pass

def foo():
    pass
""".strip())

    patch = """*** Begin Patch
*** Update File: ambiguous.py
@@ def foo():
++    print("ambiguous")
*** End Patch"""

    with pytest.raises(RuntimeError, match="Ambiguous context"):
        await apply_patch(patch, workdir=tmp_path)


async def test_apply_patch_rejects_add_through_symlink_outside_workspace(tmp_path):
    """Ensure workspace enforcement also blocks paths that traverse via symlinks.

    Create a symlink inside the workspace that points outside of it, then attempt
    to add a file underneath that symlinked directory.
    """

    outside_dir = tmp_path.parent / "outside_symlink_target"
    outside_dir.mkdir(exist_ok=True)

    link = tmp_path / "link_to_outside"
    link.symlink_to(outside_dir, target_is_directory=True)

    patch = """*** Begin Patch
*** Add File: link_to_outside/evil.txt
++owned
*** End Patch"""

    with pytest.raises(RuntimeError, match=r"Path must be within the workspace"):
        await apply_patch(patch, workdir=tmp_path)

    assert not (outside_dir / "evil.txt").exists()


async def test_apply_patch_rejects_update_through_symlink_outside_workspace(tmp_path):
    """Ensure Update File is rejected when the target resolves outside workspace via symlink."""

    outside_dir = tmp_path.parent / "outside_symlink_target_update"
    outside_dir.mkdir(exist_ok=True)

    # Create file outside workspace
    outside_file = outside_dir / "victim.txt"
    outside_file.write_text("hello\n", encoding="utf-8")

    # Symlink inside workspace pointing to outside file
    link = tmp_path / "link_victim.txt"
    link.symlink_to(outside_file)

    patch = """*** Begin Patch
*** Update File: link_victim.txt
@@
-hello
++pwned
*** End Patch"""

    with pytest.raises(RuntimeError, match=r"Path must be within the workspace"):
        await apply_patch(patch, workdir=tmp_path)

    # Ensure outside file wasn't modified
    assert outside_file.read_text(encoding="utf-8") == "hello\n"


async def test_apply_patch_rejects_move_to_through_symlink_outside_workspace(tmp_path):
    """Ensure Move to destination is rejected when it resolves outside workspace via symlink."""

    (tmp_path / "src.txt").write_text("hello\n", encoding="utf-8")

    outside_dir = tmp_path.parent / "outside_symlink_target_move"
    outside_dir.mkdir(exist_ok=True)

    link_dir = tmp_path / "link_dir"
    link_dir.symlink_to(outside_dir, target_is_directory=True)

    patch = """*** Begin Patch
*** Update File: src.txt
*** Move to: link_dir/moved.txt
@@
-hello
++world
*** End Patch"""

    with pytest.raises(RuntimeError, match=r"Path must be within the workspace"):
        await apply_patch(patch, workdir=tmp_path)

    assert (tmp_path / "src.txt").read_text(encoding="utf-8") == "hello\n"
    assert not (outside_dir / "moved.txt").exists()
