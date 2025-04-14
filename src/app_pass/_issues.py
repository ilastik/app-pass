from dataclasses import dataclass
from typing import Optional

from ._commands import Command


@dataclass
class Issue:
    fixable: bool
    details: str
    fix: Optional[Command] = None


@dataclass
class BuildIssue(Issue):
    pass


@dataclass
class RcpathIssue(Issue):
    pass


@dataclass
class LibraryPathIssue(Issue):
    pass
