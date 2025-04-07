from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    from ._macho import MachOBinary


@dataclass
class Issue:
    fixable: bool
    details: str
    fix: Optional[Callable[[], bool]] = None


@dataclass
class BuildIssue(Issue):
    pass


@dataclass
class RcpathIssue(Issue):
    pass


@dataclass
class LibraryPathIssue(Issue):
    pass
