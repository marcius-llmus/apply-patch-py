import pytest
import shutil
from pathlib import Path
from apply_patch_py import apply_patch

# Locate scenarios directory
SCENARIOS_DIR = Path(__file__).parent / "fixtures" / "scenarios"


def get_scenarios():
    if not SCENARIOS_DIR.exists():
        return []
    return sorted(
        [
            d
            for d in SCENARIOS_DIR.iterdir()
            if d.is_dir() and (d / "patch.txt").exists()
        ]
    )


def _compare_directories(expected_root, actual_root):
    expected_entries = {
        p.relative_to(expected_root): p.is_dir() for p in expected_root.rglob("*")
    }
    actual_entries = {
        p.relative_to(actual_root): p.is_dir() for p in actual_root.rglob("*")
    }

    assert expected_entries == actual_entries

    for rel_path, is_dir in expected_entries.items():
        if is_dir:
            continue
        exp_content = (expected_root / rel_path).read_bytes()
        act_content = (actual_root / rel_path).read_bytes()
        assert exp_content == act_content


@pytest.mark.parametrize("scenario_path", get_scenarios(), ids=lambda p: p.name)
async def test_scenario(scenario_path, tmp_path):
    # Setup
    input_dir = scenario_path / "input"
    expected_dir = scenario_path / "expected"
    patch_file = scenario_path / "patch.txt"

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    if input_dir.exists():
        shutil.copytree(input_dir, work_dir, dirs_exist_ok=True)

    # Read patch
    patch_text = patch_file.read_text(encoding="utf-8")

    # Run apply_patch
    try:
        await apply_patch(patch_text, workdir=work_dir)
    except Exception as e:  # noqa
        pass

    # Compare with expected
    if expected_dir.exists():
        _compare_directories(expected_dir, work_dir)
