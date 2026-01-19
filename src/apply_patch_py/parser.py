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

    @classmethod
    def parse(cls, text: str) -> Patch:
        lines = text.strip().splitlines()
        lines = cls._strip_heredoc(lines)

        if not lines:
            raise ValueError("Empty patch")

        first = lines[0].strip()
        last = lines[-1].strip()

        if first != cls.BEGIN_PATCH:
            raise ValueError(f"The first line of the patch must be '{cls.BEGIN_PATCH}'")

        if last != cls.END_PATCH:
            lines = cls._coerce_llm_patch(lines)
            if not lines:
                raise ValueError("Empty patch")
            last = lines[-1].strip()

        if last != cls.END_PATCH:
            raise ValueError(f"The last line of the patch must be '{cls.END_PATCH}'")

        hunks: List[Hunk] = []
        content_lines = lines[1:-1]
        idx = 0

        while idx < len(content_lines):
            hunk, consumed = cls._parse_one_hunk(content_lines[idx:], idx + 2)
            hunks.append(hunk)
            idx += consumed

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
    def _parse_one_hunk(cls, lines: List[str], line_number: int) -> Tuple[Hunk, int]:
        first_line = lines[0].strip()

        if first_line.startswith(cls.ADD_FILE):
            path_str = first_line[len(cls.ADD_FILE) :].strip()
            content = []
            consumed = 1

            for line in lines[1:]:
                if line.startswith("+"):
                    content.append(line[1:])
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

                if remaining[0].startswith("***"):
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
                new_lines.append(content)
            else:
                break

            consumed += 1

        if consumed == start_idx:
            raise ValueError(
                f"Invalid patch hunk on line {line_number + 1}: Update hunk does not contain any lines"
            )

        return UpdateFileChunk(old_lines, new_lines, change_context, is_eof), consumed
