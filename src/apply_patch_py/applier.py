import os
import math
import difflib
import aiofiles
from pathlib import Path
from typing import List, Tuple

from .models import (
    Hunk,
    AddFile,
    DeleteFile,
    UpdateFile,
    UpdateFileChunk,
    AffectedPaths,
)
from .parser import PatchParser
from .search import count_occurrences, find_sequence, normalise

COMMENT_PREFIXES = {
    ".py": "#",
    ".sh": "#",
    ".yaml": "#",
    ".yml": "#",
    ".js": "//",
    ".ts": "//",
    ".c": "//",
    ".cpp": "//",
    ".java": "//",
    ".rs": "//",
    ".go": "//",
    ".sql": "--",
    ".lua": "--",
}


class PatchApplier:
    @staticmethod
    def _resolve_in_workdir(workdir: Path, path: Path) -> Path:
        if path.is_absolute():
            raise RuntimeError(f"Path must be within the workspace: {path}")

        resolved_root = workdir.resolve()
        full_path = (workdir / path).resolve()

        if not full_path.is_relative_to(resolved_root):
            raise RuntimeError(f"Path must be within the workspace: {path}")

        return full_path

    @staticmethod
    def _is_comment_or_blank(line: str, path: Path | None = None) -> bool:
        if not (s := line.strip()):
            return True

        prefix = "#"
        if path:
            prefix = COMMENT_PREFIXES.get(path.suffix, "#")

        return s.startswith(prefix)

    def _count_exact_code_line_matches(
        self,
        *,
        chunk_lines: List[str],
        pattern_lines: List[str],
        path: Path | None = None,
    ) -> int:
        """Counts exact matches among non-comment, non-blank lines.

        This is a safety gate for fuzzy matching: we only accept a fuzzy match
        if enough real code lines match exactly (after normalization).
        """

        chunk_norm = {
            normalise(line)
            for line in chunk_lines
            if not self._is_comment_or_blank(line, path)
        }
        if not chunk_norm:
            return 0

        matches = 0
        for line in pattern_lines:
            if self._is_comment_or_blank(line, path):
                continue
            if normalise(line) in chunk_norm:
                matches += 1
        return matches

    async def apply(self, patch_text: str, workdir: Path = Path(".")) -> AffectedPaths:
        try:
            parser = PatchParser()
            patch = parser.parse(patch_text)
        except ValueError as e:
            raise RuntimeError(str(e)) from e

        if not patch.hunks:
            raise RuntimeError("No files were modified.")

        affected = AffectedPaths()

        for hunk in patch.hunks:
            await self._apply_hunk(hunk, workdir, affected)

        return affected

    async def _apply_hunk(self, hunk: Hunk, workdir: Path, affected: AffectedPaths):
        path = self._resolve_in_workdir(workdir, hunk.path)
        root = workdir.resolve()

        if isinstance(hunk, AddFile):
            if path.parent != root:
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

            new_lines = self._apply_chunks(original_lines, hunk.chunks, hunk.path)

            if not new_lines or new_lines[-1] != "":
                new_lines.append("")
            new_content = "\n".join(new_lines)

            if hunk.move_to:
                dest = self._resolve_in_workdir(workdir, hunk.move_to)
                if dest.parent != root:
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

    def _apply_chunks(
        self, original_lines: List[str], chunks: List[UpdateFileChunk], path: Path
    ) -> List[str]:
        current_lines = list(original_lines)
        line_index = 0

        if not chunks:
            raise RuntimeError(
                f"Invalid patch: Update file hunk for path '{path}' is empty"
            )

        for chunk in chunks:
            search_start_index = line_index
            if chunk.change_context:
                found_idx = find_sequence(
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
                if chunk.change_context:
                    match_count = count_occurrences(
                        current_lines, [chunk.change_context], search_start_index
                    )
                    if match_count > 1:
                        raise RuntimeError(
                            f"Ambiguous context: '{chunk.change_context}' matches {match_count} locations. "
                            "Please provide more specific context or surrounding lines to uniquely identify the insertion point."
                        )
                    insertion_idx = line_index
                else:
                    insertion_idx = len(current_lines)
                    if current_lines and current_lines[-1] == "":
                        insertion_idx -= 1
                current_lines[insertion_idx:insertion_idx] = chunk.new_lines
                line_index = insertion_idx + len(chunk.new_lines)
                continue

            pattern: List[str] = list(chunk.old_lines)
            new_block: List[str] = list(chunk.new_lines)

            match_len = len(pattern)
            found_idx = find_sequence(
                current_lines,
                pattern,
                line_index,
                chunk.is_end_of_file,
            )

            if found_idx is None and pattern and pattern[-1] == "":
                pattern = pattern[:-1]
                if new_block and new_block[-1] == "":
                    new_block = new_block[:-1]

                found_idx = find_sequence(
                    current_lines,
                    pattern,
                    line_index,
                    chunk.is_end_of_file,
                )
                if found_idx is not None:
                    match_len = len(pattern)

            if found_idx is None and line_index > 0:
                found_idx = find_sequence(
                    current_lines,
                    pattern,
                    0,
                    chunk.is_end_of_file,
                )
                if found_idx is not None:
                    match_len = len(pattern)

            if found_idx is None:
                # Fuzzy search
                fuzzy_res = self._fuzzy_find(
                    current_lines, pattern, line_index, path=path
                )
                if fuzzy_res is None and line_index > 0:
                    fuzzy_res = self._fuzzy_find(current_lines, pattern, 0, path=path)

                if fuzzy_res:
                    found_idx, match_len = fuzzy_res

            if found_idx is None:
                raise RuntimeError(
                    f"Failed to find expected lines in {path}:\n"
                    + "\n".join(chunk.old_lines)
                )

            current_lines[found_idx : found_idx + match_len] = new_block
            line_index = found_idx + len(new_block)

        return current_lines

    def _fuzzy_find(
        self,
        current_lines: List[str],
        pattern: List[str],
        start_idx: int,
        path: Path | None = None,
    ) -> Tuple[int, int] | None:
        """
        Finds the best matching chunk in current_lines starting from start_idx
        using difflib.SequenceMatcher. Returns (start_index, length) or None.
        """
        if not pattern:
            return None

        pattern_str = "\n".join(pattern)

        # Coarse gating: only consider candidates that are somewhat similar.
        coarse_thresh = 0.6
        # Refined threshold after applying safety gates.
        smart_thresh = 0.9

        max_similarity = 0.0
        best_start = -1
        best_len = -1

        scale = 0.3
        pat_len = len(pattern)
        min_len = math.floor(pat_len * (1 - scale))
        max_len = math.ceil(pat_len * (1 + scale))

        # If pattern is small, ensure we at least try exact length
        if min_len == max_len:
            max_len += 1

        lines_len = len(current_lines)

        for length in range(min_len, max_len + 1):
            if length <= 0:
                continue

            for i in range(start_idx, lines_len - length + 1):
                chunk = current_lines[i : i + length]
                chunk_str = "\n".join(chunk)

                ratio = difflib.SequenceMatcher(None, chunk_str, pattern_str).ratio()

                if ratio > coarse_thresh:
                    # Safety gate: require at least 2 exact code-line matches
                    # (ignoring comments/blanks). This prevents patching unrelated
                    # regions that are only superficially similar.
                    if (
                        self._count_exact_code_line_matches(
                            chunk_lines=chunk, pattern_lines=pattern, path=path
                        )
                        < 2
                    ):
                        continue

                    # Calculate refined score
                    smart_score = self._smart_fuzzy_score(chunk, pattern, path=path)

                    if smart_score > max_similarity:
                        max_similarity = smart_score
                        best_start = i
                        best_len = length

        if max_similarity >= smart_thresh:
            return best_start, best_len

        return None

    def _smart_fuzzy_score(
        self,
        chunk_lines: List[str],
        pattern_lines: List[str],
        path: Path | None = None,
    ) -> float:
        """Calculates a weighted similarity score between chunk and pattern.

        - Code lines (not starting with comment prefix) have high weight (1.0).
        - Comment lines have low weight (0.1).
        - Lines are normalized (stripped) before comparison.
        """

        # Safety: if there are many code lines and none of them match exactly,
        # treat this as unsafe even if SequenceMatcher returns a high score.
        code_lines = [
            line for line in pattern_lines if not self._is_comment_or_blank(line, path)
        ]
        if len(code_lines) >= 3:
            exact_matches = self._count_exact_code_line_matches(
                chunk_lines=chunk_lines, pattern_lines=pattern_lines, path=path
            )
            if exact_matches == 0:
                return 0.0

        # 1. Normalize lines
        chunk_norm = [line.strip() for line in chunk_lines]
        pattern_norm = [line.strip() for line in pattern_lines]

        # 2. Align lines using SequenceMatcher on the list of strings
        matcher = difflib.SequenceMatcher(None, chunk_norm, pattern_norm)

        total_weight = 0.0
        weighted_score = 0.0

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                # Lines match perfectly after strip
                for k in range(i2 - i1):
                    # Check if code or comment based on pattern
                    # Use pattern line to determine weight (what we are looking for)
                    line = pattern_norm[j1 + k]
                    is_code = not self._is_comment_or_blank(line, path)
                    weight = 1.0 if is_code else 0.1
                    weighted_score += 1.0 * weight
                    total_weight += weight

                    # Verify strict equality for code lines even in 'equal' block (sanity check)
                    # (SequenceMatcher 'equal' means they match based on the input lists, which are stripped)
                    # So this is already fine.

            elif tag == "replace":
                # Lines are different, compare them individually
                len1 = i2 - i1
                len2 = j2 - j1
                min_len = min(len1, len2)

                for k in range(min_len):
                    c_line = chunk_norm[i1 + k]
                    p_line = pattern_norm[j1 + k]

                    is_code = not self._is_comment_or_blank(p_line, path)
                    weight = 1.0 if is_code else 0.1
                    total_weight += weight

                    if is_code:
                        # STRICT GATING: Code lines must match exactly (normalized)
                        # We do not allow fuzzy matching on code logic, only on comments/whitespace.
                        if normalise(c_line) == normalise(p_line):
                            weighted_score += 1.0 * weight
                        else:
                            weighted_score += 0.0  # Penalize mismatching code heavily
                    else:
                        # Comments can be fuzzy
                        sim = difflib.SequenceMatcher(None, c_line, p_line).ratio()
                        weighted_score += sim * weight

                # Extra lines in pattern are "missing" from chunk -> mismatch (sim=0)

        if total_weight <= 0:
            return 0.0

        return weighted_score / total_weight
