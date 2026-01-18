import asyncio
from pathlib import Path
from .applier import PatchApplier
from .models import AffectedPaths
from .cli import main

async def apply_patch(patch_text: str, workdir: Path = Path(".")) -> AffectedPaths:
    return await PatchApplier.apply(patch_text, workdir)

__all__ = ["apply_patch", "AffectedPaths", "main"]