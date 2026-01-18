import os
import aiofiles
from pathlib import Path
from typing import List, Tuple
from .models import Hunk, AddFile, DeleteFile, UpdateFile, UpdateFileChunk, AffectedPaths
from .parser import PatchParser
from .search import ContentSearcher


class PatchApplier:
    @classmethod
    async def apply(cls, patch_text: str, workdir: Path = Path(".")) -> AffectedPaths:
        try:
            patch = PatchParser.parse(patch_text)
        except ValueError as e:
            raise RuntimeError(str(e)) from e

        if not patch.hunks:
            raise RuntimeError("No files were modified.")

        affected = AffectedPaths()

        for hunk in patch.hunks:
            await cls._apply_hunk(hunk, workdir, affected)

        return affected

    @classmethod
    async def _apply_hunk(cls, hunk: Hunk, workdir: Path, affected: AffectedPaths):
        workdir = workdir.resolve()
        path = workdir / hunk.path

        if isinstance(hunk, AddFile):
            if path.parent != workdir:
                path.parent.mkdir(parents=True, exist_ok=True)

            async with aiofiles.open(path, "w", encoding="utf-8") as f:
                await f.write(hunk.content)
            affected.added.append(hunk.path)

        elif isinstance(hunk, DeleteFile):
            try:
                os.remove(path)
            except OSError as e:
                raise RuntimeError(f"Failed to delete file {hunk.path}") from e

            affected.deleted.append(hunk.path)

        elif isinstance(hunk, UpdateFile):
            try:
                async with aiofiles.open(path, "r", encoding="utf-8") as f:
                    content = await f.read()
            except FileNotFoundError as e:
                raise RuntimeError(
                    f"Failed to read file to update {hunk.path}: No such file or directory (os error 2)"
                ) from e

            original_lines = content.split("\n")
            if original_lines and original_lines[-1] == "":
                original_lines.pop()

            new_lines = cls._apply_chunks(original_lines, hunk.chunks, hunk.path)

            if not new_lines or new_lines[-1] != "":
                new_lines.append("")
            new_content = "\n".join(new_lines)

            if hunk.move_to:
                dest = workdir / hunk.move_to
                if dest.parent != workdir:
                    dest.parent.mkdir(parents=True, exist_ok=True)

                async with aiofiles.open(dest, "w", encoding="utf-8") as f:
                    await f.write(new_content)

                try:
                    os.remove(path)
                except OSError as e:
                    raise RuntimeError(f"Failed to remove original {hunk.path}") from e

                affected.modified.append(hunk.move_to)
            else:
                async with aiofiles.open(path, "w", encoding="utf-8") as f:
                    await f.write(new_content)
                affected.modified.append(hunk.path)

    @classmethod
    def _apply_chunks(cls, original_lines: List[str], chunks: List[UpdateFileChunk], path: Path) -> List[str]:
        replacements: List[Tuple[int, int, List[str]]] = []
        line_index = 0

        for chunk in chunks:
            if chunk.change_context:
                found_idx = ContentSearcher.find_sequence(
                    original_lines,
                    [chunk.change_context],
                    line_index,
                    False,
                )
                if found_idx is None:
                    raise RuntimeError(f"Failed to find context '{chunk.change_context}' in {path}")
                line_index = found_idx + 1

            if not chunk.old_lines:
                insertion_idx = len(original_lines)
                replacements.append((insertion_idx, 0, list(chunk.new_lines)))
                line_index = insertion_idx
                continue

            found_idx = ContentSearcher.find_sequence(
                original_lines,
                chunk.old_lines,
                line_index,
                chunk.is_end_of_file,
            )

            pattern = chunk.old_lines
            new_block = list(chunk.new_lines)
            match_len = len(pattern)

            if found_idx is None and pattern and pattern[-1] == "":
                sub_pattern = pattern[:-1]
                found_idx = ContentSearcher.find_sequence(
                    original_lines,
                    sub_pattern,
                    line_index,
                    chunk.is_end_of_file,
                )
                if found_idx is not None:
                    pattern = sub_pattern
                    match_len = len(pattern)
                    if new_block and new_block[-1] == "":
                        new_block = new_block[:-1]

            if found_idx is None:
                raise RuntimeError(
                    f"Failed to find expected lines in {path}:\n" + "\n".join(chunk.old_lines)
                )

            replacements.append((found_idx, match_len, new_block))
            line_index = found_idx + match_len

        replacements.sort(key=lambda x: x[0], reverse=True)
        result_lines = list(original_lines)
        for start, length, new_block in replacements:
            result_lines[start : start + length] = new_block
        return result_lines