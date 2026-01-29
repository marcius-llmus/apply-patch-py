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
