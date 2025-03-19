import re
import subprocess
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path

from ._util import run_logged

_LIB_REGEX = re.compile(r"\t(?P<library>[@/]\S+\.(dylib|so))")
_LOAD_DYLIB_REGEX = re.compile(r"\s*name (?P<dylib>.+) \(offset \d+\)$")
_LOAD_RCPATH_REGEX = re.compile(r"\s*path (?P<rc_path>.+) \(offset \d+\)$")
_LOAD_COMMAND_REGEX = re.compile(r"(Load command \d+.*?)(?=Load command \d+|$)", re.DOTALL)


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
class MachOBinary:
    path: Path
    header: MachOHeader
    rc_paths: list[Path]
    dylibs: list[Path]


def otool_l(path: Path) -> tuple[LoadCommand, ...]:
    out = run_logged(["otool", "-l", str(path)])
    cmds = tuple(LoadCommand.from_otool_output(x) for x in _LOAD_COMMAND_REGEX.findall(out))
    return cmds


def otool_h(path: Path) -> MachOHeader:
    try:
        out = run_logged(["otool", "-h", str(path)])
    except subprocess.CalledProcessError as e:
        return False
    return MachOHeader.from_otool_output(out)


def rc_paths(cmds: tuple[LoadCommand, ...]) -> list[Path]:
    rcpath_cmds = [cmd for cmd in cmds if cmd.cmd == "LC_RPATH"]
    paths = []
    for rcpath_cmd in rcpath_cmds:
        p = [x for x in rcpath_cmd.cmd_specifics if x.split()[0] == "path"]
        assert len(p) == 1
        paths.append(Path(_LOAD_RCPATH_REGEX.match(p[0]).groupdict()["rc_path"]))

    return paths


def dylibs(cmds: tuple[LoadCommand, ...]) -> list[Path]:
    """LC_LOAD_DYLIB

    returns a list of dynamic libraries loaded via load commands
    """
    dylib_cmds = [cmd for cmd in cmds if cmd.cmd == "LC_LOAD_DYLIB"]
    dylibs = []
    for rcpath_cmd in dylib_cmds:
        p = [x for x in rcpath_cmd.cmd_specifics if x.split()[0] == "name"]
        assert len(p) == 1
        if m := _LOAD_DYLIB_REGEX.match(p[0]):
            p = m.groupdict()["dylib"]
            dylibs.append(Path(p))

    return dylibs


def parse_macho(some_path: Path):
    header = otool_h(some_path)
    cmds = otool_l(some_path)
    paths = rc_paths(cmds)
    libs = dylibs(cmds)

    return MachOBinary(some_path, header, paths, libs)
