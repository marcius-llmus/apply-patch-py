import pytest
import difflib
from apply_patch_py.applier import PatchApplier
from apply_patch_py.search import ContentSearcher

# We'll reuse the logic from PatchApplier._fuzzy_find to score these scenarios
# but exposing the score directly for calibration.

def calculate_score(file_content: str, patch_context: str) -> float:
    """
    Simulates the scoring logic inside PatchApplier._fuzzy_find.
    Returns the best ratio found.
    """
    # This mimics the logic in _smart_fuzzy_score and _fuzzy_find
    # We need to access the internal logic or replicate it here for testing.
    # Since _smart_fuzzy_score is a classmethod, we can call it.
    
    chunk_lines = file_content.splitlines()
    pattern_lines = patch_context.splitlines()
    
    # _smart_fuzzy_score calculates score for a specific chunk.
    # _fuzzy_find searches for the best chunk.
    # For these tests, we assume the file_content IS the candidate chunk 
    # (or close enough that we can just score them directly to see the raw affinity).
    
    # NOTE: PatchApplier._smart_fuzzy_score expects lines to NOT be pre-stripped,
    # because it does its own stripping/normalization inside.
    # However, our test strings below are raw multiline strings.
    # We should pass them as lines.
    
    return PatchApplier._smart_fuzzy_score(chunk_lines, pattern_lines)


BASE_FILE = """
INTERNAL_WIDTH = 320
INTERNAL_HEIGHT = 224
SCALE = 3
SCREEN_WIDTH = INTERNAL_WIDTH * SCALE
SCREEN_HEIGHT = INTERNAL_HEIGHT * SCALE
"""

SCENARIOS = [
    (
        "perfect_match",
        BASE_FILE,
        BASE_FILE,
        "Should be 1.0",
        1.0
    ),
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
        0.95  # High score expected (>0.9)
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
        1.0
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
        0.95
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
        0.5  # Should be LOW; safety gates should prevent high score
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
        0.5 # Should be LOW
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
        0.2
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