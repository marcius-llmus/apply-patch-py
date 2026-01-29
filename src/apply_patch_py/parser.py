from typing import List, Tuple
from pathlib import Path
import re
from .models import Patch, Hunk, AddFile, DeleteFile, UpdateFile, UpdateFileChunk


class PatchParser:
    BEGIN_PATCH = "*** Begin Patch"
    END_PATCH = "*** End Patch"
    ADD_FILE = "*** Add File: "
    DELETE_FILE = "*** Delete File: "
    UPDATE_FILE = "*** Update File: "
    MOVE_TO = "*** Move to: "
    EOF_MARKER = "*** End of File"
    CHANGE_CONTEXT = "@@ "
    EMPTY_CHANGE_CONTEXT = "@@"

    @staticmethod
    def _count_leading_pluses(s: str, *, max_pluses: int = 2) -> int:
        i = 0
        while i < len(s) and s[i] == "+":
            i += 1
            if i > max_pluses:
                return i
        return i

    def _strip_prefixed_marker(self, line: str, *, max_pluses: int = 2) -> str:
        if not (s := line.strip()).startswith("+"):
            return s

        i = self._count_leading_pluses(s, max_pluses=max_pluses)
        if i > max_pluses:
            return s
        return s[i:].lstrip()

    def _maybe_strip_pluses_from_hunk_header(self, line: str) -> str:
        """It will allow lines with malformed '++*** ...'."""

        stripped = self._strip_prefixed_marker(line)
        if self._is_hunk_header(stripped):
            return stripped
        return line.strip()

    @staticmethod
    def _is_blank(line: str) -> bool:
        return not line.strip()

    def _is_end_patch_marker(self, line: str) -> bool:
        if line.strip() == self.END_PATCH:
            return True
        stripped = self._strip_prefixed_marker(line)
        return stripped == self.END_PATCH

    def parse(self, text: str) -> Patch:
        lines = text.strip().splitlines()
        lines = self._strip_heredoc(lines)

        if not lines:
            raise ValueError("Empty patch")

        # being and end are implicit. if they come, OK, but if they don't, DW :D
        start_idx = 0
        end_idx = len(lines)

        if lines and lines[0].strip() == self.BEGIN_PATCH:
            start_idx = 1

        if end_idx > start_idx and self._is_end_patch_marker(lines[end_idx - 1]):
            end_idx -= 1

        content_lines = lines[start_idx:end_idx]

        hunks: List[Hunk] = []
        idx = 0
        while idx < len(content_lines):
            if self._is_blank(content_lines[idx]):
                idx += 1
                continue

            if self._is_end_patch_marker(content_lines[idx]):
                break

            hunk, consumed = self._parse_one_hunk(
                content_lines[idx:], idx + start_idx + 1
            )
            hunks.append(hunk)
            idx += consumed

        if not hunks:
            # Maintain existing CLI/tool behavior which expects this to surface
            # as "No files were modified." at the applier layer.
            raise ValueError("No files were modified.")

        while idx < len(content_lines):
            if self._is_blank(content_lines[idx]) or self._is_end_patch_marker(
                content_lines[idx]
            ):
                idx += 1
                continue
            raise ValueError(
                f"Invalid patch hunk on line {idx + start_idx + 1}: '{content_lines[idx]}' is not a valid hunk header. "
                "Valid hunk headers: '*** Add File: {path}', '*** Delete File: {path}', '*** Update File: {path}'"
            )

        return Patch(hunks=hunks)

    @staticmethod
    def _strip_heredoc(lines: List[str]) -> List[str]:
        if len(lines) < 4:
            return lines

        first = lines[0].strip()
        last = lines[-1].strip()

        is_heredoc_start = first in {"<<EOF", "<<'EOF'", '<<"EOF"'}
        if is_heredoc_start and last.endswith("EOF"):
            return lines[1:-1]

        return lines

    def _is_hunk_header(self, line: str) -> bool:
        return (
            (s := line.strip()).startswith(self.ADD_FILE)
            or s.startswith(self.DELETE_FILE)
            or s.startswith(self.UPDATE_FILE)
        )

    def _is_any_hunk_header(self, line: str) -> bool:
        stripped = self._strip_prefixed_marker(line)
        return self._is_hunk_header(stripped)

    def _parse_one_hunk(self, lines: List[str], line_number: int) -> Tuple[Hunk, int]:
        first_line = self._maybe_strip_pluses_from_hunk_header(lines[0])

        if first_line.startswith(self.ADD_FILE):
            path_str = first_line[len(self.ADD_FILE) :].strip()
            content = []
            consumed = 1

            for line in lines[1:]:
                if self._is_any_hunk_header(line) or self._is_end_patch_marker(line):
                    break

                if line.startswith("+"):
                    val = line[1:]
                    content.append(val)
                    consumed += 1
                else:
                    break

            content_str = "\n".join(content) + "\n" if content else ""
            return AddFile(path=Path(path_str), content=content_str), consumed

        elif first_line.startswith(self.DELETE_FILE):
            path_str = first_line[len(self.DELETE_FILE) :].strip()
            return DeleteFile(path=Path(path_str)), 1

        elif first_line.startswith(self.UPDATE_FILE):
            path_str = first_line[len(self.UPDATE_FILE) :].strip()
            consumed = 1
            remaining = lines[1:]
            move_to = None

            if remaining and remaining[0].strip().startswith(self.MOVE_TO):
                move_path = remaining[0].strip()[len(self.MOVE_TO) :].strip()
                move_to = Path(move_path)
                consumed += 1
                remaining = remaining[1:]

            chunks: list = []

            while remaining:
                if not remaining[0].strip():
                    consumed += 1
                    remaining = remaining[1:]
                    continue

                # Break on the start of the next hunk OR end marker, even if
                # the model prefixed the marker with '+' or '++'.
                if self._is_end_patch_marker(remaining[0]):
                    break
                if self._is_any_hunk_header(remaining[0]):
                    break

                chunk, chunk_consumed = self._parse_update_chunk(
                    remaining,
                    line_number=line_number + consumed,
                    allow_missing_context=not chunks,
                )
                chunks.append(chunk)
                consumed += chunk_consumed
                remaining = remaining[chunk_consumed:]

            if not chunks:
                raise ValueError(
                    f"Invalid patch hunk on line {line_number}: Update file hunk for path '{path_str}' is empty"
                )

            return (
                UpdateFile(
                    path=Path(path_str),
                    move_to=move_to,
                    chunks=chunks,
                ),
                consumed,
            )

        else:
            raise ValueError(
                f"Invalid patch hunk on line {line_number}: '{first_line}' is not a valid hunk header. "
                "Valid hunk headers: '*** Add File: {path}', '*** Delete File: {path}', '*** Update File: {path}'"
            )

    @staticmethod
    def _get_raw_diff_from_lines(diff_lines):
        return "\n".join(diff_lines) + "\n"

    def _parse_update_chunk(
        self,
        lines: List[str],
        *,
        line_number: int,
        allow_missing_context: bool,
    ) -> Tuple[UpdateFileChunk, int]:
        if not lines:
            raise ValueError(
                f"Invalid patch hunk on line {line_number}: Update hunk does not contain any lines"
            )

        first = lines[0]
        change_context = None
        diff_lines = []

        # LLMs sometimes prefix the chunk header with '+' or '++'.
        # We normalize:
        #  - '+@@ ...' -> '@@ ...'
        #  - '++@@ ...' -> '@@ ...'
        stripped = first.lstrip()
        if stripped.startswith("+@@"):
            first = stripped[1:]
        elif stripped.startswith("++@@"):
            first = stripped[2:]

        if first.strip() == self.EMPTY_CHANGE_CONTEXT:
            start_idx = 1
            diff_lines.append("@@")
        elif first.startswith(self.CHANGE_CONTEXT):
            raw_context = first[len(self.CHANGE_CONTEXT) :].strip()
            # Some LLMs (notably Gemini) emit unified-diff style range headers
            # (e.g. "-21,6 +21,7 @@") instead of a literal context anchor.
            # Our applier interprets change_context as a line to search for, so
            # we treat these numeric headers as "no context".
            if re.fullmatch(r"-\d+(?:,\d+)?\s+\+\d+(?:,\d+)?\s+@@", raw_context):
                change_context = None
            else:
                change_context = raw_context
            start_idx = 1
            diff_lines.append(f"@@ {change_context}" if change_context else "@@")
        else:
            if not allow_missing_context:
                raise ValueError(
                    f"Invalid patch hunk on line {line_number}: Expected update hunk to start with a @@ context marker, got: '{first}'"
                )
            start_idx = 0

        old_lines = []
        new_lines = []
        is_eof = False
        consumed = start_idx

        for line in lines[start_idx:]:
            if line.strip() == self.EOF_MARKER.strip():
                is_eof = True
                consumed += 1
                break

            if line == "":
                old_lines.append("")
                new_lines.append("")
                diff_lines.append("")
                consumed += 1
                continue

            marker = line[0]
            content = line[1:]

            if marker == " ":
                old_lines.append(content)
                new_lines.append(content)
                diff_lines.append(line)
            elif marker == "-":
                old_lines.append(content)
                diff_lines.append(line)
            elif marker == "+":
                if content.startswith("+"):
                    content = content[1:]
                new_lines.append(content)
                diff_lines.append(f"+{content}")
            else:
                break

            consumed += 1

        if consumed == start_idx:
            raise ValueError(
                f"Invalid patch hunk on line {line_number + 1}: Update hunk does not contain any lines"
            )

        diff = self._get_raw_diff_from_lines(diff_lines)

        return (
            UpdateFileChunk(
                diff=diff,
                old_lines=old_lines,
                new_lines=new_lines,
                change_context=change_context,
                is_end_of_file=is_eof,
            ),
            consumed,
        )
