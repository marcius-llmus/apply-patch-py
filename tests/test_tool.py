import subprocess


def run_cli(args, cwd, input_str=None):
    """Helper to run the CLI tool"""
    cmd = ["uv", "run", "apply-patch-py"] + args

    result = subprocess.run(
        cmd, cwd=cwd, input=input_str, text=True, capture_output=True
    )
    return result


def test_apply_patch_cli_applies_multiple_operations(tmp_path):
    modify_path = tmp_path / "modify.txt"
    delete_path = tmp_path / "delete.txt"
    modify_path.write_text("line1\nline2\n")
    delete_path.write_text("obsolete\n")

    patch = """*** Begin Patch
*** Add File: nested/new.txt
+created
*** Delete File: delete.txt
*** Update File: modify.txt
@@
-line2
+changed
*** End Patch"""

    res = run_cli([patch], cwd=tmp_path)
    assert res.returncode == 0
    assert "A nested/new.txt" in res.stdout
    assert "M modify.txt" in res.stdout
    assert "D delete.txt" in res.stdout

    assert (tmp_path / "nested/new.txt").read_text() == "created\n"
    assert modify_path.read_text() == "line1\nchanged\n"
    assert not delete_path.exists()


def test_apply_patch_cli_applies_multiple_chunks(tmp_path):
    target_path = tmp_path / "multi.txt"
    target_path.write_text("line1\nline2\nline3\nline4\n")

    patch = """*** Begin Patch
*** Update File: multi.txt
@@
-line2
+changed2
@@
-line4
+changed4
*** End Patch"""

    res = run_cli([patch], cwd=tmp_path)
    assert res.returncode == 0
    assert "M multi.txt" in res.stdout

    assert target_path.read_text() == "line1\nchanged2\nline3\nchanged4\n"


def test_apply_patch_cli_moves_file_to_new_directory(tmp_path):
    original_path = tmp_path / "old/name.txt"
    new_path = tmp_path / "renamed/dir/name.txt"
    original_path.parent.mkdir(parents=True)
    original_path.write_text("old content\n")

    patch = """*** Begin Patch
*** Update File: old/name.txt
*** Move to: renamed/dir/name.txt
@@
-old content
+new content
*** End Patch"""

    res = run_cli([patch], cwd=tmp_path)
    assert res.returncode == 0
    assert "M renamed/dir/name.txt" in res.stdout

    assert not original_path.exists()
    assert new_path.read_text() == "new content\n"


def test_apply_patch_cli_rejects_empty_patch(tmp_path):
    res = run_cli(["*** Begin Patch\n*** End Patch"], cwd=tmp_path)
    assert res.returncode != 0
    assert res.stderr == "No files were modified.\n"


def test_apply_patch_cli_reports_missing_context(tmp_path):
    target_path = tmp_path / "modify.txt"
    target_path.write_text("line1\nline2\n")

    patch = """*** Begin Patch
*** Update File: modify.txt
@@
-missing
+changed
*** End Patch"""

    res = run_cli([patch], cwd=tmp_path)
    assert res.returncode != 0
    assert res.stderr == "Failed to find expected lines in modify.txt:\nmissing\n"
    assert target_path.read_text() == "line1\nline2\n"


def test_apply_patch_cli_rejects_missing_file_delete(tmp_path):
    patch = """*** Begin Patch
*** Delete File: missing.txt
*** End Patch"""

    res = run_cli([patch], cwd=tmp_path)
    assert res.returncode != 0
    assert res.stderr == "Failed to delete file missing.txt\n"


def test_apply_patch_cli_rejects_empty_update_hunk(tmp_path):
    patch = """*** Begin Patch
*** Update File: foo.txt
*** End Patch"""

    res = run_cli([patch], cwd=tmp_path)
    assert res.returncode != 0
    assert (
        res.stderr
        == "Invalid patch hunk on line 2: Update file hunk for path 'foo.txt' is empty\n"
    )


def test_apply_patch_cli_requires_existing_file_for_update(tmp_path):
    patch = """*** Begin Patch
*** Update File: missing.txt
@@
-old
+new
*** End Patch"""

    res = run_cli([patch], cwd=tmp_path)
    assert res.returncode != 0
    assert (
        res.stderr
        == "Failed to read file to update missing.txt: No such file or directory (os error 2)\n"
    )


def test_apply_patch_cli_move_overwrites_existing_destination(tmp_path):
    original_path = tmp_path / "old/name.txt"
    destination = tmp_path / "renamed/dir/name.txt"
    original_path.parent.mkdir(parents=True)
    destination.parent.mkdir(parents=True)
    original_path.write_text("from\n")
    destination.write_text("existing\n")

    patch = """*** Begin Patch
*** Update File: old/name.txt
*** Move to: renamed/dir/name.txt
@@
-from
+new
*** End Patch"""

    res = run_cli([patch], cwd=tmp_path)
    assert res.returncode == 0
    assert "M renamed/dir/name.txt" in res.stdout

    assert not original_path.exists()
    assert destination.read_text() == "new\n"


def test_apply_patch_cli_add_overwrites_existing_file(tmp_path):
    path = tmp_path / "duplicate.txt"
    path.write_text("old content\n")

    patch = """*** Begin Patch
*** Add File: duplicate.txt
+new content
*** End Patch"""

    res = run_cli([patch], cwd=tmp_path)
    assert res.returncode == 0
    assert "A duplicate.txt" in res.stdout
    assert path.read_text() == "new content\n"


def test_apply_patch_cli_delete_directory_fails(tmp_path):
    (tmp_path / "dir").mkdir()

    patch = """*** Begin Patch
*** Delete File: dir
*** End Patch"""

    res = run_cli([patch], cwd=tmp_path)
    assert res.returncode != 0
    assert res.stderr == "Failed to delete file dir\n"


def test_apply_patch_cli_rejects_invalid_hunk_header(tmp_path):
    patch = """*** Begin Patch
*** Frobnicate File: foo
*** End Patch"""

    res = run_cli([patch], cwd=tmp_path)
    assert res.returncode != 0
    assert (
        res.stderr
        == "Invalid patch hunk on line 2: '*** Frobnicate File: foo' is not a valid hunk header. Valid hunk headers: '*** Add File: {path}', '*** Delete File: {path}', '*** Update File: {path}'\n"
    )


def test_apply_patch_cli_updates_file_appends_trailing_newline(tmp_path):
    target_path = tmp_path / "no_newline.txt"
    target_path.write_text("no newline at end")

    patch = """*** Begin Patch
*** Update File: no_newline.txt
@@
-no newline at end
+first line
+second line
*** End Patch"""

    res = run_cli([patch], cwd=tmp_path)
    assert res.returncode == 0

    contents = target_path.read_text()
    assert contents.endswith("\n")
    assert contents == "first line\nsecond line\n"


def test_apply_patch_cli_failure_after_partial_success_leaves_changes(tmp_path):
    new_file = tmp_path / "created.txt"

    patch = """*** Begin Patch
*** Add File: created.txt
+hello
*** Update File: missing.txt
@@
-old
+new
*** End Patch"""

    res = run_cli([patch], cwd=tmp_path)
    assert res.returncode != 0
    assert (
        res.stderr
        == "Failed to read file to update missing.txt: No such file or directory (os error 2)\n"
    )

    # Check that the first part of the patch was applied
    assert new_file.read_text() == "hello\n"


def test_apply_patch_rejects_add_outside_workspace(tmp_path):
    outside = tmp_path.parent / "outside_add.txt"
    if outside.exists():
        outside.unlink()

    patch = """*** Begin Patch
*** Add File: ../outside_add.txt
++nope
*** End Patch"""

    res = run_cli([patch], cwd=tmp_path)
    assert res.returncode != 0
    assert res.stderr == "Path must be within the workspace: ../outside_add.txt\n"
    assert not outside.exists()


def test_apply_patch_rejects_update_move_outside_workspace(tmp_path):
    outside = tmp_path.parent / "outside_move.txt"
    if outside.exists():
        outside.unlink()

    (tmp_path / "in.txt").write_text("hello\n")

    patch = """*** Begin Patch
*** Update File: in.txt
*** Move to: ../outside_move.txt
@@
-hello
+world
*** End Patch"""

    res = run_cli([patch], cwd=tmp_path)
    assert res.returncode != 0
    assert res.stderr == "Path must be within the workspace: ../outside_move.txt\n"
    assert not outside.exists()
    assert (tmp_path / "in.txt").read_text() == "hello\n"


def test_apply_patch_rejects_delete_outside_workspace(tmp_path):
    outside = tmp_path.parent / "outside_delete.txt"
    outside.write_text("should not be deletable\n")

    patch = """*** Begin Patch
*** Delete File: ../outside_delete.txt
*** End Patch"""

    res = run_cli([patch], cwd=tmp_path)
    assert res.returncode != 0
    assert res.stderr == "Path must be within the workspace: ../outside_delete.txt\n"
    assert outside.exists()


def test_apply_patch_rejects_update_outside_workspace(tmp_path):
    outside = tmp_path.parent / "outside_update.txt"
    outside.write_text("hello\n")

    patch = """*** Begin Patch
*** Update File: ../outside_update.txt
@@
-hello
+world
*** End Patch"""

    res = run_cli([patch], cwd=tmp_path)
    assert res.returncode != 0
    assert res.stderr == "Path must be within the workspace: ../outside_update.txt\n"
    assert outside.read_text() == "hello\n"


def test_apply_patch_rejects_absolute_paths(tmp_path):
    patch = """*** Begin Patch
*** Add File: /tmp/evil.txt
++nope
*** End Patch"""

    res = run_cli([patch], cwd=tmp_path)
    assert res.returncode != 0
    assert res.stderr.startswith("Path must be within the workspace: ")


def test_apply_patch_rejects_absolute_move_to(tmp_path):
    (tmp_path / "in.txt").write_text("hello\n")

    patch = """*** Begin Patch
*** Update File: in.txt
*** Move to: /tmp/evil_move.txt
@@
-hello
+world
*** End Patch"""

    res = run_cli([patch], cwd=tmp_path)
    assert res.returncode != 0
    assert res.stderr == "Path must be within the workspace: /tmp/evil_move.txt\n"
    assert (tmp_path / "in.txt").read_text() == "hello\n"
