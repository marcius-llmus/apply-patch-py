from pathlib import Path

from .applier import PatchApplier
from .cli import main
from .models import AffectedPaths


async def apply_patch(patch_text: str, workdir: Path = Path(".")) -> AffectedPaths:
    return await PatchApplier.apply(patch_text, workdir)


__all__ = ["apply_patch", "AffectedPaths", "main"]
