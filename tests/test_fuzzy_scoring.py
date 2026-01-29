from pathlib import Path
import pytest
from apply_patch_py.applier import PatchApplier


def calculate_score(
    file_content: str, patch_context: str, filename: str = "test.py"
) -> float:
    """
    Simulates the scoring logic inside PatchApplier._fuzzy_find.
    Returns the best ratio found.
    """

    chunk_lines = file_content.splitlines()
    pattern_lines = patch_context.splitlines()
    return PatchApplier()._smart_fuzzy_score(
        chunk_lines, pattern_lines, path=Path(filename)
    )


BASE_FILE = """
INTERNAL_WIDTH = 320
INTERNAL_HEIGHT = 224
SCALE = 3
SCREEN_WIDTH = INTERNAL_WIDTH * SCALE
SCREEN_HEIGHT = INTERNAL_HEIGHT * SCALE
"""

SCENARIOS = [
    ("perfect_match", BASE_FILE, BASE_FILE, "Should be 1.0", 1.0),
    (
        "comment_header_change",
        """
# Display Settings
INTERNAL_WIDTH = 320
INTERNAL_HEIGHT = 224
SCALE = 3
SCREEN_WIDTH = INTERNAL_WIDTH * SCALE
SCREEN_HEIGHT = INTERNAL_HEIGHT * SCALE
""",
        """
# Level Constants
INTERNAL_WIDTH = 320
INTERNAL_HEIGHT = 224
SCALE = 3
SCREEN_WIDTH = INTERNAL_WIDTH * SCALE
SCREEN_HEIGHT = INTERNAL_HEIGHT * SCALE
""",
        "Valid: Header comment changed (common LLM drift)",
        0.95,  # High score expected (>0.9)
    ),
    (
        "whitespace_indentation",
        """
    INTERNAL_WIDTH = 320
    INTERNAL_HEIGHT = 224
""",
        """
INTERNAL_WIDTH = 320
INTERNAL_HEIGHT = 224
""",
        "Valid: Indentation changed (should be high score due to strip())",
        1.0,
    ),
    (
        "extra_newline_in_file",
        """
INTERNAL_WIDTH = 320

INTERNAL_HEIGHT = 224
""",
        """
INTERNAL_WIDTH = 320
INTERNAL_HEIGHT = 224
""",
        "Valid: Extra blank line in file",
        0.95,
    ),
    (
        "typo_in_identifier_bad",
        """
INTERNAL_WIDTH = 320
INTERNAL_HEIGHT = 224
SCALE = 3
SCREEN_WIDTH = INTERNAL_WIDTH * SCALE
SCREEN_HEIGHT = INTERNAL_HEIGHT * SCALE
""",
        """
INTERNAL_WIDTH = 320
INTERNAL_HEIGadadHT = 224
SCALE = 3
SCREEN_WIDTH = INTERsNAL_WIDTH * SCALE
SCREEN_HEIGHT = INTasasERNAL_HEIGHT * SCALE
""",
        "Invalid: Corrupted identifiers (your example)",
        0.5,  # Should be LOW; safety gates should prevent high score
    ),
    (
        "wrong_values",
        """
INTERNAL_WIDTH = 320
INTERNAL_HEIGHT = 224
""",
        """
INTERNAL_WIDTH = 999
INTERNAL_HEIGHT = 888
""",
        "Invalid: Values are totally different (wrong location?)",
        0.5,  # Should be LOW
    ),
    (
        "totally_unrelated",
        """
def foo():
    return True
""",
        """
INTERNAL_WIDTH = 320
INTERNAL_HEIGHT = 224
""",
        "Invalid: Completely different text",
        0.2,
    ),
]


@pytest.mark.parametrize("name, file_text, patch_text, desc, min_expected", SCENARIOS)
def test_score_calibration(name, file_text, patch_text, desc, min_expected):
    score = calculate_score(file_text.strip(), patch_text.strip())
    print(f"\nSCENARIO: {name}")
    print(f"DESC: {desc}")
    print(f"SCORE: {score:.4f}")

    if min_expected >= 0.9:
        assert score >= min_expected, f"Score {score} too low for valid scenario {name}"
    else:
        # For invalid scenarios, we expect a low score (or at least strictly below the threshold of 0.9)
        assert score < 0.9, f"Score {score} too high for invalid scenario {name}"


def test_sql_comment_scoring_differentiation():
    """
    Verify that using the correct extension (SQL) treats '--' as comments (low weight),
    allowing a high score even if the comment text changes.
    Using the wrong extension (Python) treats '--' as code (high weight),
    punishing the mismatch more heavily.
    """
    file_text = "-- New comment\nSELECT * FROM table"
    patch_text = "-- Old comment\nSELECT * FROM table"

    # In SQL (correct ext), '--' is comment -> low weight -> high score.
    score_sql = calculate_score(file_text, patch_text, filename="query.sql")

    # In Python (wrong ext), '--' is code -> high weight -> mismatch -> lower score.
    score_py = calculate_score(file_text, patch_text, filename="query.py")

    print(f"SQL Score: {score_sql}")
    print(f"Py Score:  {score_py}")

    assert score_sql > 0.9
    assert score_sql > score_py
