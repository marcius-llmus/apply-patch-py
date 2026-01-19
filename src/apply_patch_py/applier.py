import os
import aiofiles
from pathlib import Path
from typing import List
from .models import (
    Hunk,
    AddFile,
    DeleteFile,
    UpdateFile,
    UpdateFileChunk,
    AffectedPaths,
)
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
    def _apply_chunks(
        cls, original_lines: List[str], chunks: List[UpdateFileChunk], path: Path
    ) -> List[str]:
        current_lines = list(original_lines)
        line_index = 0

        if not chunks:
            raise RuntimeError(
                f"Invalid patch: Update file hunk for path '{path}' is empty"
            )

        for chunk in chunks:
            if chunk.change_context:
                found_idx = ContentSearcher.find_sequence(
                    current_lines,
                    [chunk.change_context],
                    line_index,
                    False,
                )
                if found_idx is None:
                    raise RuntimeError(
                        f"Failed to find context '{chunk.change_context}' in {path}"
                    )
                line_index = found_idx + 1

            if not chunk.old_lines:
                insertion_idx = len(current_lines)
                if current_lines and current_lines[-1] == "":
                    insertion_idx -= 1
                current_lines[insertion_idx:insertion_idx] = chunk.new_lines
                line_index = insertion_idx + len(chunk.new_lines)
                continue

            pattern: List[str] = list(chunk.old_lines)
            new_block: List[str] = list(chunk.new_lines)

            found_idx = ContentSearcher.find_sequence(
                current_lines,
                pattern,
                line_index,
                chunk.is_end_of_file,
            )

            if found_idx is None and pattern and pattern[-1] == "":
                pattern = pattern[:-1]
                if new_block and new_block[-1] == "":
                    new_block = new_block[:-1]

                found_idx = ContentSearcher.find_sequence(
                    current_lines,
                    pattern,
                    line_index,
                    chunk.is_end_of_file,
                )

            if found_idx is None and line_index > 0:
                found_idx = ContentSearcher.find_sequence(
                    current_lines,
                    pattern,
                    0,
                    chunk.is_end_of_file,
                )

            if found_idx is None:
                found_idx = cls._fallback_find_lines_independently(
                    current_lines=current_lines,
                    pattern=pattern,
                    start_idx=line_index,
                    is_end_of_file=chunk.is_end_of_file,
                )

            if found_idx is None:
                raise RuntimeError(
                    f"Failed to find expected lines in {path}:\n"
                    + "\n".join(chunk.old_lines)
                )

            match_len = len(pattern)
            current_lines[found_idx : found_idx + match_len] = new_block
            line_index = found_idx + len(new_block)

        return current_lines

    @classmethod
    def _fallback_find_lines_independently(
        cls,
        *,
        current_lines: List[str],
        pattern: List[str],
        start_idx: int,
        is_end_of_file: bool,
    ) -> int | None:
        """Fallback matcher for imperfect LLM hunks.

        Strict matching is attempted first. If it fails, we try to locate the edit
        position using a couple of distinctive "anchor" lines from the old block.

        To reduce the chance of patching the wrong location, we only accept anchors
        that are unique in the file.
        """

        candidates: List[str] = [p for p in pattern if p.strip()]
        if not candidates:
            return None

        anchors = candidates[:2]
        if not anchors:
            return None

        anchor_matches: List[int] = []
        for anchor in anchors:
            if not cls._is_unique_line(current_lines, anchor):
                return None

            idx = ContentSearcher.find_sequence(
                current_lines, [anchor], start_idx, is_end_of_file
            )
            if idx is None and start_idx > 0:
                idx = ContentSearcher.find_sequence(
                    current_lines, [anchor], 0, is_end_of_file
                )
            if idx is None:
                return None
            anchor_matches.append(idx)

        if len(anchor_matches) >= 2 and anchor_matches[1] < anchor_matches[0]:
            return None

        return min(anchor_matches)

    @staticmethod
    def _is_unique_line(lines: List[str], line: str) -> bool:
        """Return True if 'line' occurs exactly once in 'lines'.

        We use strict equality; if normalization is needed, it should be applied at
        the search layer.
        """

        count = 0
        for candidate in lines:
            if candidate == line:
                count += 1
                if count > 1:
                    return False
        return count == 1
