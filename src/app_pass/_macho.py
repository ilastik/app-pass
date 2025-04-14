import re
import subprocess
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Optional

from packaging import version

from ._commands import Command
from ._util import BinaryObj, run_logged

_LOAD_DYLIB_REGEX = re.compile(r"\s*name (?P<dylib>.+) \(offset \d+\)$")
_LOAD_RCPATH_REGEX = re.compile(r"\s*path (?P<rc_path>.+) \(offset \d+\)$")
_LOAD_COMMAND_REGEX = re.compile(r"(Load command \d+.*?)(?=Load command \d+|$)", re.DOTALL)


_VTOOL_OUT_PARSE_PLATFORM = re.compile(r"platform (?P<platform>.*)\n", re.IGNORECASE)
_VTOOL_OUT_PARSE_MINOS = re.compile(r"minos (?P<minos>.*)\n", re.IGNORECASE)
_VTOOL_OUT_PARSE_SDK = re.compile(r"sdk (?P<sdk>.*)\n", re.IGNORECASE)
_VALID_VER = re.compile(r"\d+\..*", re.IGNORECASE)


class DependencyNotFountInBundle(Exception):
    pass


@dataclass
class LoadCommand:
    index: str
    cmd: str
    cmd_size: str
    cmd_specifics: list[str]

    @staticmethod
    def from_otool_output(otool_l_output) -> "LoadCommand":
        lines: list[str] = [x.strip() for x in otool_l_output.split("\n")]

        # strip trailing empty lines
        lines = [line for line in lines if line]

        index = re.search(r"Load command (\d+)", lines[0]).groups()[0]
        cmd = re.search(r"cmd (\S+)", lines[1]).groups()[0]
        cmd_size = re.search(r"cmdsize (\d+)", lines[2]).groups()[0]

        additional = lines[3:]
        return LoadCommand(index=index, cmd=cmd, cmd_size=cmd_size, cmd_specifics=additional)


class FILETYPE(IntEnum):
    """
    ref: https://github.com/apple/darwin-xnu/blob/main/EXTERNAL_HEADERS/mach-o/loader.h
    """

    relocatable_object_file = 1
    demand_paged_executable_file = 2
    fixed_VM_shared_library_file = 3
    core_file = 4
    preloaded_executable_file = 5
    dynamically_bound_shared_library = 6
    dynamic_link_editor = 7
    dynamically_bound_bundle_file = 8
    shared_library_stub_for_static = 9

    companion_file_with_only_debug = 10
    x86_64_kexts = 11
    set_of_mach_o_s = 12

    @staticmethod
    def from_hex_str(hex_string: str) -> "FILETYPE":
        return FILETYPE(int(hex_string, base=16))

    def __repr__(self):
        return f"{self.name}"


@dataclass
class MachOHeader:

    magic: str
    filetype: FILETYPE

    @staticmethod
    def from_otool_output(otool_L_output):
        out = otool_L_output.split("\n")
        line = out[-2].strip().split()
        vals = line
        return MachOHeader(vals[0], FILETYPE.from_hex_str(vals[4]))


@dataclass
class Build:
    platform: str
    minos: str
    sdk: str

    @staticmethod
    def from_vtool_output(vtool_str: str) -> "Build":
        if m := _VTOOL_OUT_PARSE_PLATFORM.search(vtool_str):
            platform = m.groupdict()["platform"].lower()
        else:
            platform = ""

        if m := _VTOOL_OUT_PARSE_MINOS.search(vtool_str):
            minos = m.groupdict()["minos"]
        else:
            minos = ""

        if m := _VTOOL_OUT_PARSE_SDK.search(vtool_str):
            sdk = m.groupdict()["sdk"]
        else:
            sdk = ""

        return Build(platform=platform, minos=minos, sdk=sdk)

    @staticmethod
    def _version_req_met(v: str) -> bool:
        _MIN_V = version.parse("10.9")
        if version.parse(v) >= _MIN_V:
            return True

        return False

    @property
    def is_valid(self) -> bool:
        """Will pass gatekeeper"""
        if self.platform and _VALID_VER.match(self.minos) and _VALID_VER.match(self.sdk):
            # older versions can not pass gatekeeper
            if Build._version_req_met(self.minos) and Build._version_req_met(self.sdk):
                return True

        return False

    @property
    def can_fix(self) -> bool:
        """Libraries that were build with too old of an sdk can not be fixed."""
        if _VALID_VER.match(self.minos):
            if not Build._version_req_met(self.minos):
                return False

        if _VALID_VER.match(self.sdk):
            if not Build._version_req_met(self.sdk):
                return False

        return True

    @property
    def invalid_fields(self) -> dict[str, str]:
        ret = {}
        if not self.platform:
            ret["platform"] = self.platform

        if not self.sdk:
            ret["sdk"] = self.sdk

        if not self.minos:
            ret["minos"] = self.minos

        return ret

    @property
    def invalid_field_names(self) -> list[str]:
        invalid_fields = self.invalid_fields
        return list(invalid_fields.keys())

    def valid_build(self, default_build: "Build", overwrite=False) -> "Build":
        platform = self.platform
        minos = self.minos
        sdk = self.sdk

        if overwrite:
            return Build(
                platform=default_build.platform or platform,
                minos=default_build.minos or minos,
                sdk=default_build.sdk or sdk,
            )

        if not _VALID_VER.match(sdk) and not _VALID_VER.match(minos):
            assert _VALID_VER.match(default_build.sdk) and _VALID_VER.match(default_build.minos)
            sdk = default_build.sdk
            minos = default_build.minos

        if not _VALID_VER.match(self.sdk):
            if _VALID_VER.match(default_build.sdk):
                sdk_version = version.parse(default_build.sdk)
                # don't set sdk version lower than minos
                minos_version = version.parse(minos)
                sdk = default_build.sdk if sdk_version > minos_version else minos
            else:
                sdk = minos

        if not _VALID_VER.match(minos):
            if _VALID_VER.match(default_build.minos):
                minos_version = version.parse(default_build.minos)
                # don't set minos higher than sdk
                sdk_version = version.parse(sdk)
                minos = default_build.minos if minos_version < sdk_version else sdk
            else:
                minos = sdk

        if not platform:
            platform = default_build.platform

        return Build(platform=platform, minos=minos, sdk=sdk)


def vtool_read(path: Path) -> Build:
    """
    vtool -show-build  ilastik-1.4.1rc2-OSX.app/Contents/ilastik-release/lib/libxcb.1.dylib

    ilastik-1.4.1rc2-OSX.app/Contents/ilastik-release/lib/libxcb.1.dylib:
    Load command 16
          cmd LC_BUILD_VERSION
      cmdsize 24
     platform MACOS
        minos 10.9
          sdk 10.9
       ntools 0
    """
    return Build.from_vtool_output(run_logged(Command(["/usr/bin/vtool", "-show-build", str(path)])))


def vtool_overwrite(path: Path, build: Build) -> Command:
    cmd = Command(
        args=[
            "/usr/bin/vtool",
            "-set-build-version",
            build.platform,
            build.minos,
            build.sdk,
            "-replace",
            "-output",
            str(path),
            str(path),
        ],
    )

    return cmd


@dataclass
class MachOBinary(BinaryObj):
    header: MachOHeader
    rpaths: list[Path]
    dylibs: list[Path]
    build: Optional[Build]
    id_: Optional[Path]


def otool_l(path: Path) -> tuple[LoadCommand, ...]:
    out = run_logged(Command(args=["otool", "-l", str(path)]))
    cmds = tuple(LoadCommand.from_otool_output(x) for x in _LOAD_COMMAND_REGEX.findall(out))
    return cmds


def otool_h(path: Path) -> MachOHeader:
    try:
        out = run_logged(Command(["otool", "-h", str(path)]))
    except subprocess.CalledProcessError:
        return False
    return MachOHeader.from_otool_output(out)


def rpaths(cmds: tuple[LoadCommand, ...]) -> list[Path]:
    rcpath_cmds = [cmd for cmd in cmds if cmd.cmd == "LC_RPATH"]
    paths = []
    for rcpath_cmd in rcpath_cmds:
        p = [x for x in rcpath_cmd.cmd_specifics if x.split()[0] == "path"]
        assert len(p) == 1
        paths.append(Path(_LOAD_RCPATH_REGEX.match(p[0]).groupdict()["rc_path"]))

    return paths


def libid(cmds: tuple[LoadCommand, ...]) -> Optional[Path]:
    id_commands = [cmd for cmd in cmds if cmd.cmd == "LC_ID_DYLIB"]
    if len(id_commands) == 0:
        return None
    id_command = id_commands[0]
    p = [x for x in id_command.cmd_specifics if x.split()[0] == "name"]
    assert len(p) == 1
    if m := _LOAD_DYLIB_REGEX.match(p[0]):
        p = m.groupdict()["dylib"]
        dylib = Path(p)
    else:
        raise ValueError(f"Could not parse command {id_command}")

    return dylib


def dylibs(cmds: tuple[LoadCommand, ...]) -> list[Path]:
    """LC_LOAD_DYLIB

    returns a list of dynamic libraries loaded via load commands
    """
    dylib_cmds = [cmd for cmd in cmds if cmd.cmd in ("LC_LOAD_DYLIB", "LC_REEXPORT_DYLIB")]
    dylibs = []
    for rcpath_cmd in dylib_cmds:
        p = [x for x in rcpath_cmd.cmd_specifics if x.split()[0] == "name"]
        assert len(p) == 1
        if m := _LOAD_DYLIB_REGEX.match(p[0]):
            p = m.groupdict()["dylib"]
            dylibs.append(Path(p))

    return dylibs


def parse_macho(some_path: Path):
    if not some_path.is_absolute():
        some_path = some_path.resolve()
    try:
        header = otool_h(some_path)
        cmds = otool_l(some_path)
        paths = rpaths(cmds)
        lib_id = libid(cmds)
        libs = dylibs(cmds)
    except Exception as e:
        raise ValueError(f"Problem parsing {some_path}") from e

    # Found these to contain multiple architectures and binaries
    # vtool (currently) doesn't seem to handle those.
    # TODO: should warn
    # if header.filetype == FILETYPE.fixed_VM_shared_library_file:
    #     build = None
    # else:
    build = vtool_read(some_path)
    return MachOBinary(some_path, header, paths, libs, build, lib_id)


def fix_lib_id(library_path: Path, new_path: Path) -> Command:
    args = ["install_name_tool", "-id", str(new_path), str(library_path)]
    return Command(args=args)


def fix_load_path(library_path: Path, dependency: Path, new_path: Path) -> Command:
    args = ["install_name_tool", "-change", str(dependency), str(new_path), str(library_path)]
    return Command(args=args)


def remove_rpath(library_path, rpath) -> Command:
    args = ["install_name_tool", "-delete_rpath", str(rpath), str(library_path)]
    return Command(args=args)


def fix_rpath(library_path, old_rpath, new_rpath) -> Command:
    args = ["install_name_tool", "-rpath", str(old_rpath), str(new_rpath), str(library_path)]
    return Command(args=args)


def sign_impl(entitlement_file, developer_id, path) -> Command:
    args = [
        "/usr/bin/codesign",
        "--entitlements",
        str(entitlement_file),
        "--timestamp",
        "-o",
        "runtime",
        "-f",
        "-s",
        developer_id,
        str(path),
    ]

    return Command(args=args)
