from pathlib import Path

import pytest

from apply_patch_py import apply_patch


@pytest.mark.parametrize(
    "original_header, patch_header",
    [
        ("# Display Settings", "# Level Constants"),
        ("# Level Constants", "# Display Settings"),
    ],
)
async def test_apply_patch_fuzzy_matches_nearby_context(tmp_path, original_header, patch_header):
    """Applies an Update File hunk even if a nearby context line differs.

    This covers the common case where an LLM changes a comment header, but the
    surrounding lines uniquely identify the intended location.
    """

    target = tmp_path / "settings.py"
    target.write_text(
        "\n".join(
            [
                original_header,
                "INTERNAL_WIDTH = 320",
                "INTERNAL_HEIGHT = 224",
                "SCALE = 3",
                "SCREEN_WIDTH = INTERNAL_WIDTH * SCALE",
                "SCREEN_HEIGHT = INTERNAL_HEIGHT * SCALE",
                "FPS = 60",
                "",
            ]
        )
    )

    patch = "\n".join(
        [
            "*** Begin Patch",
            "*** Update File: settings.py",
            "@@",
            f" {patch_header}",
            " INTERNAL_WIDTH = 320",
            " INTERNAL_HEIGadadHT = 224",
            " INTERNAL_HEIGadadHT = 224",
            "+LEVEL_WIDTH = 5000",
            " SCALE = 3",
            " SCREEN_WIDTH = INTERsNAL_WIDTH * SCALE",
            " SCREEN_HEIGHT = INTasasERNAL_HEIGHT * SCALE",
            " FPS = 60",
            "*** End Patch",
            "",
        ]
    )

    affected = await apply_patch(patch, workdir=tmp_path)
    assert affected.success is True
    assert affected.modified == [Path("settings.py")]

    updated = target.read_text(encoding="utf-8")
    assert "LEVEL_WIDTH = 5000\n" in updated
    assert updated.endswith("\n")


async def test_apply_patch_fuzzy_does_not_apply_if_similarity_too_low(tmp_path):
    """When the patch context is too different, we should still fail safely."""

    target = tmp_path / "settings.py"
    target.write_text(
        "\n".join(
            [
                "# Display Settings",
                "INTERNAL_WIDTH = 320",
                "INTERNAL_HEIGHT = 224",
                "SCALE = 3",
                "SCREEN_WIDTH = INTERNAL_WIDTH * SCALE",
                "SCREEN_HEIGHT = INTERNAL_HEIGHT * SCALE",
                "FPS = 60",
                "",
            ]
        )
    )

    # This hunk doesn't resemble the file block enough.
    patch = "\n".join(
        [
            "*** Begin Patch",
            "*** Update File: settings.py",
            "@@",
            " totally unrelated header",
            " -not even python",
            "+LEVEL_WIDTH = 5000",
            "*** End Patch",
            "",
        ]
    )

    with pytest.raises(RuntimeError, match=r"Failed to find expected lines in settings\.py"):
        await apply_patch(patch, workdir=tmp_path)