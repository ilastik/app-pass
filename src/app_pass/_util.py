import enum
import logging
import pathlib
import subprocess
from dataclasses import dataclass
from typing import Iterator, Tuple

from rich.progress import Progress

from ._commands import Command

logger = logging.getLogger(__name__)


class BinaryType(enum.Enum):
    NONE = enum.auto()
    MACHO = enum.auto()
    JAR = enum.auto()


@dataclass
class BinaryObj:
    path: pathlib.Path


def run_logged(command: Command) -> str:
    logger.debug(f"Executing command {' '.join(command.args)}")

    out = subprocess.run(command.args, stdout=subprocess.PIPE, stdin=subprocess.PIPE, cwd=command.cwd)
    if out.returncode != 0:
        logger.warning(f"Nonzero exit code ({out.returncode}) from command {' '.join(command.args)}")
        raise subprocess.CalledProcessError(
            returncode=out.returncode,
            cmd=command.args,
            stderr=out.stderr.decode("utf-8") if out.stderr else "",
            output=out.stdout.decode("utf-8") if out.stdout else "",
        )

    logger.info(f"Successful command {' '.join(command.args)}")

    return out.stdout.decode("utf-8")


def run_commands(commands: list[Command]):
    for command in commands:
        if command.run_python:
            run_logged(command)


def serialize_to_sh(commands: list[Command], sh_cmd_out: pathlib.Path):
    cmds = []
    for cmd in commands:
        cmds.extend(cmd.to_sh())
    if sh_cmd_out.exists():
        logger.warning(f"Found {sh_cmd_out} - overwriting.")

    sh_cmd_out.write_text("\n".join(cmds))


def is_binary(path: pathlib.Path) -> BinaryType:
    if path.suffix in (".a", ".o"):
        logger.debug(f"Ignoring .a, and .o files: {path}")
        return BinaryType.NONE

    if path.suffix in (".py", ".txt", ".md", ".h", ".class", ".cpp", ".hpp", ".class"):
        return BinaryType.NONE
    file_out = run_logged(Command(["file", str(path)])).lower()
    if "mach-o" in file_out:
        if "architectures" in file_out:
            logger.warning(f"Multiple architectures in file {path}")
        return BinaryType.MACHO
    elif path.suffix in (".jar", ".sym") and ("java archive data (jar)" in file_out or "zip archive data" in file_out):
        return BinaryType.JAR

    return BinaryType.NONE


def iter_all_binaries(
    root: pathlib.Path,
    progress: Progress,
) -> Iterator[Tuple[pathlib.Path, BinaryType]]:
    files = list(root.glob("**/*"))
    task = progress.add_task("Scanning files", total=len(files))
    for f in files:
        binary_type = is_binary(f)
        if binary_type != BinaryType.NONE:
            yield f, binary_type
        progress.advance(task, 1)

    progress.remove_task(task)
