from dataclasses import dataclass
from functools import cached_property, partial
from pathlib import Path
from typing import List, Optional

from rich.progress import Progress
import structlog
from lxml import etree

from ._issues import BuildIssue, Issue, LibraryPathIssue, RcpathIssue
from ._jar import Jar
from ._macho import Build, MachOBinary, fix_lib_id, fix_load_path, fix_rpath, parse_macho, remove_rpath, vtool_overwrite
from ._util import BinaryType, iter_all_binaries

logger = structlog.get_logger()


def parse_plist(plist: Path):
    """partial read of plist"""
    doc = etree.parse(plist)
    root = doc.getroot()
    return {x.text: x.getnext().text for x in root.findall(".//dict/key")}


# for now the assumption is that whenever these are encountered, things should be fine.
_ALLOWED_SPECIAL = [Path(x) for x in ["@rpath", "@executable_path", "@loader_path"]]
_ALLOWED_SYSTEM = [Path(x) for x in ["/System/", "/usr/", "/Library/"]]


@dataclass
class OSXAPP:
    root: Path
    loader_path: Path  # dir
    bundle_exe: Path  # file
    macho_binaries: list[MachOBinary]
    jars: list[Jar]
    # TODO: make build configurable
    default_build: Build = Build(platform="macos", minos="11.0", sdk="11.0")

    @staticmethod
    def from_path(root: Path) -> "OSXAPP":
        if not root.is_absolute():
            root = root.resolve()
        plist = root / "Contents" / "Info.plist"
        assert plist.exists()
        plist_dict = parse_plist(plist)
        # I've seen both, the executable "CFBundleExecutable" being only the `binary` within "MacOS" folder
        # and `MacOS/binary`:
        executable = Path(plist_dict["CFBundleExecutable"])
        if executable.parent == Path("MacOS"):
            bundle_exe = root / "Contents" / executable
        else:
            bundle_exe = root / "Contents" / "MacOS" / executable

        loader_path = bundle_exe.parent

        macho_binaries: list[MachOBinary] = []
        jars: list[Jar] = []

        with Progress() as progress:
            for f, bin_type in iter_all_binaries(root, progress):
                if bin_type == BinaryType.MACHO:
                    macho_bin = parse_macho(f)
                    macho_binaries.append(macho_bin)
                elif bin_type == BinaryType.JAR:
                    jars.append(Jar.from_path(f, progress))

        return OSXAPP(root, loader_path, bundle_exe, macho_binaries, jars)

    def __post_init__(self):
        assert self.bundle_exe.exists(), self.bundle_exe
        assert self.bundle_exe.is_file()
        assert self.bundle_exe.is_relative_to(self.root), self.bundle_exe

    @cached_property
    def libraries(self) -> dict[str, MachOBinary]:
        return {x.path.name: x for x in self.macho_binaries}

    def lib_loader_relative(self, libname):
        assert libname in self.libraries
        lib_path = self.libraries[libname].path

        loader_root_relative = self.loader_path.relative_to(self.root)

        candiates = [loader_root_relative] + list(loader_root_relative.parents)

        loader_relative_path = None
        for i, candidate in enumerate(candiates):
            if lib_path.is_relative_to(self.root / candidate):
                up = "/".join([".."] * i)
                loader_relative_path = Path("@loader_path") / up / lib_path.relative_to(self.root / candidate)
                break

        if loader_relative_path:
            return loader_relative_path
        else:
            raise ValueError(f"Could not determine loader relative path for {lib_path} in {self.root=}")

    @cached_property
    def bundle_exe_rpaths(self) -> List[Path]:
        filtered = list(filter(lambda x: x.path == self.bundle_exe, self.macho_binaries))
        assert len(filtered) == 1
        bundle_exe_macho = filtered[0]
        if any(rc.is_absolute() for rc in bundle_exe_macho.rpaths):
            raise ValueError(
                f"{bundle_exe_macho.rpaths=} in {bundle_exe_macho.path=} need fixing, may not be absolute."
            )
        return bundle_exe_macho.rpaths

    def check_binaries(self, rc_path_delete: bool = False) -> List[Issue]:
        issues = []
        for macho_binary in self.macho_binaries:
            id_issues = check_id_needs_fix(self, macho_binary)
            issues.extend(id_issues)
            lib_issues = check_libs_need_fix(self, macho_binary)
            issues.extend(lib_issues)
            rc_issues = check_rpaths_need_fix(self, macho_binary, rc_path_delete)
            issues.extend(rc_issues)

            if macho_binary.build and not macho_binary.build.is_valid:
                if macho_binary.build.can_fix:
                    valid_build = macho_binary.build.valid_build(self.default_build)
                    issue = BuildIssue(
                        fixable=True,
                        details="Missing build number.",
                        fix=partial(vtool_overwrite, macho_binary.path, valid_build),
                    )
                else:
                    issue = BuildIssue(
                        fixable=False,
                        details=f"Probably sdk for build outdated - gatekeeper requires >=10.9 ({macho_binary.path}: {macho_binary.build.platform=} {macho_binary.build.sdk=} {macho_binary.build.minos=})",
                    )
                issues.append(issue)
                if issue.fixable:
                    logger.info(
                        "Issue found",
                        library=macho_binary.path,
                        issue_type="build_version_issue",
                        fixable=issue.fixable,
                    )
                else:
                    logger.warning(
                        "Issue found",
                        library=macho_binary.path,
                        issue_type="build_version_issue",
                        fixable=issue.fixable,
                    )

        return issues


def fix_path_pointer(app: OSXAPP, path: Path) -> Optional[Path]:
    """
    Return a modified, valid path inside the app for a given path
    """
    if any(path.is_relative_to(x) for x in _ALLOWED_SYSTEM + _ALLOWED_SPECIAL):
        # could still be broken but if the app is running at all, this should
        # be fine
        return path

    if path.is_absolute() and path.is_relative_to(app.root):
        # we should be able to fix it somehow.
        # check if relative to one of the rpaths of the main executable
        app_rpaths = app.bundle_exe_rpaths
        for rpath in app_rpaths:
            assert not rpath.is_absolute()
            if "@loader_path/" in str(rpath):
                rc_abs = app.loader_path / Path(str(rpath).replace("@loader_path/", ""))
            elif "@executable_path/" in str(rpath):
                rc_abs = app.loader_path / Path(str(rpath).replace("@executable_path/", ""))
            elif "@executable_path/" in str(rpath):
                raise ValueError("Didn't really expect a relative path with @rpath, but it seems to exist :).")
            else:
                raise ValueError(f"Could not resolve rc_path - probably not valid {path}")

            if path.is_relative_to(rc_abs):
                new_path = path.relative_to(rc_abs)
                return rpath / new_path

        # fallback to loader_path and hope for the best (will break if loaded
        # based on some other executable)
        path = path.relative_to(app.loader_path)
        return Path("@loader_path") / path


def check_id_needs_fix(app: OSXAPP, binary: MachOBinary) -> List[LibraryPathIssue]:
    if not binary.id_:
        return []

    if not any(binary.id_.is_relative_to(x) for x in _ALLOWED_SYSTEM + _ALLOWED_SPECIAL):
        return [
            LibraryPathIssue(
                fixable=True,
                details="Library ID with fixed path",
                fix=partial(fix_lib_id, binary.path, Path("@rpath") / binary.id_.name),
            )
        ]
    else:
        return []


def check_libs_need_fix(app: OSXAPP, binary: MachOBinary) -> List[LibraryPathIssue]:
    invalid = []
    for lib in binary.dylibs:
        if not any(lib.is_relative_to(x) for x in _ALLOWED_SYSTEM + _ALLOWED_SPECIAL):
            invalid.append(lib)

    issues = []
    # try to find a direct hit for the library
    for lib in invalid:
        if lib.name in app.libraries:
            found = app.lib_loader_relative(lib.name)
            issues.append(
                LibraryPathIssue(
                    fixable=True,
                    details="Link to library not valid",
                    fix=partial(fix_load_path, binary.path, lib, found),
                )
            )
        else:
            issues.append(LibraryPathIssue(fixable=False, details=f"Issue with {lib.name} at {lib} for {binary.path}"))

    return issues


def check_rpaths_need_fix(app: OSXAPP, binary: MachOBinary, rc_path_delete: bool) -> List[RcpathIssue]:
    issues: List[RcpathIssue] = []
    for pth in binary.rpaths:
        fixed = fix_path_pointer(app, pth)
        if fixed and fixed != pth:
            issues.append(
                RcpathIssue(
                    fixable=True,
                    details=f"Rcpath fix: {pth} -> {fixed}",
                    fix=partial(fix_rpath, binary.path, pth, fixed),
                )
            )

        if not fixed:
            if rc_path_delete:
                issues.append(
                    RcpathIssue(
                        fixable=True,
                        details=f"DELETING rpath in {binary.path} pointing outside of binary and allowed system paths, this may indicate build issues {pth}.",
                        fix=partial(remove_rpath, binary.path, pth),
                    )
                )
            else:
                issues.append(
                    RcpathIssue(
                        fixable=False,
                        details=f"rpath in {binary.path} pointing outside of binary and allowed system paths, this may indicate build issues {pth}.",
                    )
                )

    return issues
