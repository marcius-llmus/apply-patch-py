from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class UpdateFileChunk:
    """
    Represents a chunk of changes within a file update.
    """

    old_lines: List[str]
    new_lines: List[str]
    change_context: Optional[str] = None
    is_end_of_file: bool = False


@dataclass
class Hunk:
    """
    Base class for a file operation in a patch.
    """

    path: Path


@dataclass
class AddFile(Hunk):
    """
    Operation to create a new file with specific content.
    """

    content: str


@dataclass
class DeleteFile(Hunk):
    """
    Operation to delete an existing file.
    """

    pass


@dataclass
class UpdateFile(Hunk):
    """
    Operation to update an existing file, optionally renaming it.
    """

    chunks: List[UpdateFileChunk]
    move_to: Optional[Path] = None


@dataclass
class Patch:
    hunks: List[Hunk]


@dataclass
class AffectedPaths:
    added: List[Path] = field(default_factory=list)
    modified: List[Path] = field(default_factory=list)
    deleted: List[Path] = field(default_factory=list)
    success: bool = True
