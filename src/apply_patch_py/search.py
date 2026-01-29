from typing import List, Optional


def find_sequence(
    lines: List[str], pattern: List[str], start_idx: int, is_end_of_file: bool
) -> Optional[int]:
    if not pattern:
        return start_idx

    if len(pattern) > len(lines):
        return None

    search_start = start_idx
    if is_end_of_file and len(lines) >= len(pattern):
        search_start = len(lines) - len(pattern)

    max_start = len(lines) - len(pattern)
    if search_start > max_start:
        return None

    for i in range(search_start, max_start + 1):
        if lines[i : i + len(pattern)] == pattern:
            return i

    for i in range(search_start, max_start + 1):
        if _match_rstrip(lines, pattern, i):
            return i

    for i in range(search_start, max_start + 1):
        if _match_trim(lines, pattern, i):
            return i

    for i in range(search_start, max_start + 1):
        if _match_normalized(lines, pattern, i):
            return i

    return None


def count_occurrences(lines: List[str], pattern: List[str], start_idx: int) -> int:
    if not pattern:
        return 0

    count = 0
    # Scan the whole file starting from start_idx
    for i in range(start_idx, len(lines) - len(pattern) + 1):
        if (
            _match_rstrip(lines, pattern, i)
            or _match_trim(lines, pattern, i)
            or _match_normalized(lines, pattern, i)
        ):
            count += 1
    return count


def _match_rstrip(lines: List[str], pattern: List[str], idx: int) -> bool:
    for p_idx, pat_line in enumerate(pattern):
        if lines[idx + p_idx].rstrip() != pat_line.rstrip():
            return False
    return True


def _match_trim(lines: List[str], pattern: List[str], idx: int) -> bool:
    for p_idx, pat_line in enumerate(pattern):
        if lines[idx + p_idx].strip() != pat_line.strip():
            return False
    return True


def _match_normalized(lines: List[str], pattern: List[str], idx: int) -> bool:
    for p_idx, pat_line in enumerate(pattern):
        if normalise(lines[idx + p_idx]) != normalise(pat_line):
            return False
    return True


def normalise(text: str) -> str:
    replacements = {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2015": "-",
        "\u2212": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u201b": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u201f": '"',
        "\u00a0": " ",
        "\u2002": " ",
        "\u2003": " ",
        "\u2004": " ",
        "\u2005": " ",
        "\u2006": " ",
        "\u2007": " ",
        "\u2008": " ",
        "\u2009": " ",
        "\u200a": " ",
        "\u202f": " ",
        "\u205f": " ",
        "\u3000": " ",
    }
    return "".join(replacements.get(c, c) for c in text.strip())
