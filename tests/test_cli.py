import subprocess


def run_cli(args, cwd, input_str=None):
    """Helper to run the CLI tool"""
    cmd = ["uv", "run", "apply-patch-py"] + args

    result = subprocess.run(
        cmd, cwd=cwd, input=input_str, text=True, capture_output=True
    )
    return result


def test_apply_patch_cli_add_and_update(tmp_path):
    file_name = "cli_test.txt"
    abs_path = tmp_path / file_name

    # 1) Add a file
    add_patch = f"""*** Begin Patch
*** Add File: {file_name}
+hello
*** End Patch"""

    res = run_cli([add_patch], cwd=tmp_path)
    assert res.returncode == 0
    assert f"A {file_name}" in res.stdout
    assert abs_path.read_text() == "hello\n"

    # 2) Update the file
    update_patch = f"""*** Begin Patch
*** Update File: {file_name}
@@
-hello
+world
*** End Patch"""

    res = run_cli([update_patch], cwd=tmp_path)
    assert res.returncode == 0
    assert f"M {file_name}" in res.stdout
    assert abs_path.read_text() == "world\n"


def test_apply_patch_cli_stdin_add_and_update(tmp_path):
    file_name = "cli_test_stdin.txt"
    abs_path = tmp_path / file_name

    # 1) Add a file via stdin
    add_patch = f"""*** Begin Patch
*** Add File: {file_name}
+hello
*** End Patch"""

    res = run_cli([], cwd=tmp_path, input_str=add_patch)
    assert res.returncode == 0
    assert f"A {file_name}" in res.stdout
    assert abs_path.read_text() == "hello\n"

    # 2) Update the file via stdin
    update_patch = f"""*** Begin Patch
*** Update File: {file_name}
@@
-hello
+world
*** End Patch"""

    res = run_cli([], cwd=tmp_path, input_str=update_patch)
    assert res.returncode == 0
    assert f"M {file_name}" in res.stdout
    assert abs_path.read_text() == "world\n"
