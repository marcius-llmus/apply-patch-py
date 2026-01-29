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

    @classmethod
    def _strip_prefixed_marker(cls, line: str, *, max_pluses: int = 2) -> str:
        s = line.strip()
        if not s.startswith("+"):
            return s

        i = cls._count_leading_pluses(s, max_pluses=max_pluses)
        if i > max_pluses:
            return s
        return s[i:].lstrip()

    @classmethod
    def _is_unprefixed_end_patch(cls, line: str) -> bool:
        return line.strip() == cls.END_PATCH

    @classmethod
    def _strip_single_plus_prefix(cls, line: str) -> str:
        s = line.strip()
        if s.startswith("++"):
            return s
        if s.startswith("+"):
            return s[1:].lstrip()
        return s

    @classmethod
    def _maybe_strip_plus_from_hunk_header(cls, line: str) -> str:
        """Normalize a single leading '+' from a hunk header.

        LLMs sometimes prefix hunk headers with '+' (or even '++') when they are
        accidentally emitted as diff additions.

        We only strip a single '+' when the remainder is an unambiguous hunk
        header (Add/Delete/Update). We do not normalize arbitrary lines.
        """

        s = line.strip()
        if not s.startswith("+") or s.startswith("++"):
            return s
        candidate = s[1:].lstrip()
        if cls._is_hunk_header(candidate):
            return candidate
        return s

    @classmethod
    def _maybe_strip_pluses_from_hunk_header(cls, line: str) -> str:
        """Like _maybe_strip_plus_from_hunk_header, but tolerate '++*** ...'."""

        s = line.strip()
        if not s.startswith("+"):
            return s

        i = cls._count_leading_pluses(s, max_pluses=2)
        if i > 2:
            return s

        candidate = s[i:].lstrip()
        if cls._is_hunk_header(candidate):
            return candidate
        return s

    @classmethod
    def _is_blank(cls, line: str) -> bool:
        return not line.strip()

    @classmethod
    def _is_end_patch_marker(cls, line: str) -> bool:
        s = line.strip()
        if s == cls.END_PATCH:
            return True
        stripped = cls._strip_prefixed_marker(line)
        return stripped == cls.END_PATCH

    @classmethod
    def parse(cls, text: str) -> Patch:
        lines = text.strip().splitlines()
        lines = cls._strip_heredoc(lines)

        if not lines:
            raise ValueError("Empty patch")

        lines = cls._coerce_llm_patch(lines)
        if not lines:
            raise ValueError("Empty patch")

        # being and end are implicit. if they come, OK, but if they don't, DW :D
        start_idx = 0
        end_idx = len(lines)

        if lines and lines[0].strip() == cls.BEGIN_PATCH:
            start_idx = 1

        if end_idx > start_idx and cls._is_end_patch_marker(lines[end_idx - 1]):
            end_idx -= 1

        content_lines = lines[start_idx:end_idx]

        hunks: List[Hunk] = []
        idx = 0
        while idx < len(content_lines):
            if cls._is_blank(content_lines[idx]):
                idx += 1
                continue

            if cls._is_end_patch_marker(content_lines[idx]):
                break

            hunk, consumed = cls._parse_one_hunk(
                content_lines[idx:], idx + start_idx + 1
            )
            hunks.append(hunk)
            idx += consumed

        if not hunks:
            # Maintain existing CLI/tool behavior which expects this to surface
            # as "No files were modified." at the applier layer.
            raise ValueError("No files were modified.")

        while idx < len(content_lines):
            if cls._is_blank(content_lines[idx]) or cls._is_end_patch_marker(
                content_lines[idx]
            ):
                idx += 1
                continue
            raise ValueError(
                f"Invalid patch hunk on line {idx + start_idx + 1}: '{content_lines[idx]}' is not a valid hunk header. "
                "Valid hunk headers: '*** Add File: {path}', '*** Delete File: {path}', '*** Update File: {path}'"
            )

        return Patch(hunks=hunks)

    @classmethod
    def _coerce_llm_patch(cls, lines: List[str]) -> List[str]:
        """Attempt to recover from common LLM formatting mistakes.

        In some model outputs, "*** End Patch" may appear as an added line in the
        final hunk (prefixed with '+') instead of as the required final line.
        This function normalizes that case by:
        - stripping trailing whitespace-only lines
        - converting a trailing '+*** End Patch' (and trailing '+') into
          a proper final '*** End Patch'

        It intentionally stays conservative to avoid mis-parsing legitimate
        file content additions.
        """

        if not lines:
            return lines

        while lines and not lines[-1].strip():
            lines.pop()

        if not lines:
            return lines

        if lines[-1].strip() == f"+{cls.END_PATCH}":
            lines[-1] = cls.END_PATCH
            return lines

        if (
            len(lines) >= 2
            and lines[-2].strip() == f"+{cls.END_PATCH}"
            and lines[-1].strip() == "+"
        ):
            lines = lines[:-1]
            lines[-1] = cls.END_PATCH
            return lines

        return lines

    @classmethod
    def _strip_heredoc(cls, lines: List[str]) -> List[str]:
        if len(lines) < 4:
            return lines

        first = lines[0].strip()
        last = lines[-1].strip()

        is_heredoc_start = first in {"<<EOF", "<<'EOF'", '<<"EOF"'}
        if is_heredoc_start and last.endswith("EOF"):
            return lines[1:-1]

        return lines

    @classmethod
    def _is_hunk_header(cls, line: str) -> bool:
        s = line.strip()
        return (
            s.startswith(cls.ADD_FILE)
            or s.startswith(cls.DELETE_FILE)
            or s.startswith(cls.UPDATE_FILE)
        )

    @classmethod
    def _is_prefixed_hunk_header(cls, line: str) -> bool:
        stripped = cls._strip_prefixed_marker(line)
        if stripped == line.strip():
            return False
        return cls._is_hunk_header(stripped)

    @classmethod
    def _is_prefixed_end_patch(cls, line: str) -> bool:
        stripped = cls._strip_prefixed_marker(line)
        if stripped == line.strip():
            return False
        return stripped == cls.END_PATCH

    @classmethod
    def _parse_one_hunk(cls, lines: List[str], line_number: int) -> Tuple[Hunk, int]:
        first_line = cls._maybe_strip_pluses_from_hunk_header(lines[0])

        if first_line.startswith(cls.ADD_FILE):
            path_str = first_line[len(cls.ADD_FILE) :].strip()
            content = []
            consumed = 1

            for line in lines[1:]:
                if (
                    cls._is_prefixed_hunk_header(line)
                    or cls._is_prefixed_end_patch(line)
                    or cls._is_end_patch_marker(line)
                ):
                    break

                if line.startswith("+"):
                    val = line[1:]
                    if val.startswith("+"):
                        val = val[1:]
                    content.append(val)
                    consumed += 1
                else:
                    break

            content_str = "\n".join(content) + "\n" if content else ""
            return AddFile(path=Path(path_str), content=content_str), consumed

        elif first_line.startswith(cls.DELETE_FILE):
            path_str = first_line[len(cls.DELETE_FILE) :].strip()
            return DeleteFile(path=Path(path_str)), 1

        elif first_line.startswith(cls.UPDATE_FILE):
            path_str = first_line[len(cls.UPDATE_FILE) :].strip()
            consumed = 1
            remaining = lines[1:]
            move_to = None

            if remaining and remaining[0].strip().startswith(cls.MOVE_TO):
                move_path = remaining[0].strip()[len(cls.MOVE_TO) :].strip()
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
                if cls._is_unprefixed_end_patch(remaining[0]):
                    break
                if cls._is_hunk_header(remaining[0]):
                    break
                if cls._is_prefixed_hunk_header(remaining[0]):
                    break
                if cls._is_prefixed_end_patch(remaining[0]):
                    break

                if cls._is_end_patch_marker(remaining[0]):
                    break

                chunk, chunk_consumed = cls._parse_update_chunk(
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
                UpdateFile(path=Path(path_str), move_to=move_to, chunks=chunks),
                consumed,
            )

        else:
            raise ValueError(
                f"Invalid patch hunk on line {line_number}: '{first_line}' is not a valid hunk header. "
                "Valid hunk headers: '*** Add File: {path}', '*** Delete File: {path}', '*** Update File: {path}'"
            )

    @classmethod
    def _parse_update_chunk(
        cls,
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

        # LLMs sometimes prefix the chunk header with '+' or '++'.
        # We normalize:
        #  - '+@@ ...' -> '@@ ...'
        #  - '++@@ ...' -> '@@ ...'
        stripped = first.lstrip()
        if stripped.startswith("+@@"):
            first = stripped[1:]
        elif stripped.startswith("++@@"):
            first = stripped[2:]

        if first.strip() == cls.EMPTY_CHANGE_CONTEXT:
            start_idx = 1
        elif first.startswith(cls.CHANGE_CONTEXT):
            raw_context = first[len(cls.CHANGE_CONTEXT) :].strip()
            # Some LLMs (notably Gemini) emit unified-diff style range headers
            # (e.g. "-21,6 +21,7 @@") instead of a literal context anchor.
            # Our applier interprets change_context as a line to search for, so
            # we treat these numeric headers as "no context".
            if re.fullmatch(r"-\d+(?:,\d+)?\s+\+\d+(?:,\d+)?\s+@@", raw_context):
                change_context = None
            else:
                change_context = raw_context
            start_idx = 1
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
            if line.strip() == cls.EOF_MARKER.strip():
                is_eof = True
                consumed += 1
                break

            if line == "":
                old_lines.append("")
                new_lines.append("")
                consumed += 1
                continue

            marker = line[0]
            content = line[1:]

            if marker == " ":
                old_lines.append(content)
                new_lines.append(content)
            elif marker == "-":
                old_lines.append(content)
            elif marker == "+":
                if content.startswith("+"):
                    content = content[1:]
                new_lines.append(content)
            else:
                break

            consumed += 1

        if consumed == start_idx:
            raise ValueError(
                f"Invalid patch hunk on line {line_number + 1}: Update hunk does not contain any lines"
            )

        return UpdateFileChunk(old_lines, new_lines, change_context, is_eof), consumed
