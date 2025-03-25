from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Optional

from lxml import etree

from ._issues import BuildIssue, LibararyPathIssue
from ._macho import Build, MachOBinary, parse_macho, vtool_overwrite
from ._util import iter_all_binaries

import structlog


logger = structlog.get_logger()


def parse_plist(plist: Path):
    """partial read of plist"""
    doc = etree.parse(plist)
    root = doc.getroot()
    return {x.text: x.getnext().text for x in root.findall(".//dict/key")}


_ALLOWED = [Path(x) for x in ["@rpath", "@executable_path", "@loader_path", "/System/", "/usr/", "/Library/"]]


@dataclass
class OSXAPP:
    root: Path
    loader_path: Path
    macho_binaries: list[MachOBinary]
    # TODO: make build configurable
    default_build: Build = Build(platform="macos", minos="11.0", sdk="11.0")

    @staticmethod
    def from_path(root: Path) -> "OSXAPP":
        plist = root / "Contents" / "Info.plist"
        assert plist.exists()
        plist_dict = parse_plist(plist)

        macho_binaries: list[MachOBinary] = []

        for f in iter_all_binaries(root):
            if macho_bin := parse_macho(f):
                macho_binaries.append(macho_bin)

        return OSXAPP(root, root / "Contents" / "MacOS" / plist_dict["CFBundleExecutable"], macho_binaries)

    def __post_init__(self):
        assert self.loader_path.exists(), self.loader_path
        assert self.loader_path.is_relative_to(self.root), self.loader_path

    def check_binaries(self):
        issues = []
        for macho_binary in self.macho_binaries:
            if not check_libs_valid(self, macho_binary):
                print(macho_binary)
            if not check_rpaths_valid(self, macho_binary):
                print(macho_binary)
            if macho_binary.build and not macho_binary.build.is_valid:
                if valid_build := macho_binary.build.valid_build(self.default_build):
                    issue = BuildIssue(fixable=True, fix=partial(vtool_overwrite, macho_binary.path, valid_build))
                else:
                    issue = BuildIssue(fixable=False)
                issues.append(issue)
                if issue.fixable:
                    logger.info("Issue found", library=macho_binary.path, issue_type="build_version_issue", fixable=issue.fixable)
                else:
                    logger.warning("Issue found", library=macho_binary.path, issue_type="build_version_issue", fixable=issue.fixable)

        return issues

def check_libs_valid(app: OSXAPP, binary: MachOBinary) -> Optional[LibararyPathIssue]:
    invalid = []
    for lib in binary.dylibs:
        if not any(lib.is_relative_to(x) for x in _ALLOWED + [app.root]):
            invalid.append(lib)

    for inv in invalid:
        pass

    return True


def check_rpaths_valid(app: OSXAPP, binary: MachOBinary) -> bool:
    invalid = []
    for pth in binary.rc_paths:
        if not any(pth.is_relative_to(x) for x in _ALLOWED + [app.root]):
            invalid.append(pth)

    return not invalid
