import enum
import pathlib
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterator, Tuple

import structlog
from rich.progress import Progress

from ._commands import Command

logger = structlog.get_logger()


class BinaryType(enum.Enum):
    NONE = enum.auto()
    MACHO = enum.auto()
    JAR = enum.auto()


@dataclass
class BinaryObj:
    path: pathlib.Path


# def run_logged_read(args: list[str], **kwargs) -> str:
#     return run_logged_act(args, dry_run=False, intends_side_effect=False, **kwargs)


def run_logged(command: Command) -> str:
    logger.debug("Executing", command=command.to_dict())

    out = subprocess.run(command.args, stdout=subprocess.PIPE, stdin=subprocess.PIPE, cwd=command.cwd)
    if out.returncode != 0:
        logger.warning(
            "Nonzero exit code from command",
            command=command.to_dict(),
            exit_code=out.returncode,
            stderr=out.stderr.decode("utf-8") if out.stderr else "",
            output=out.stdout.decode("utf-8") if out.stdout else "",
        )
        raise subprocess.CalledProcessError(
            returncode=out.returncode,
            cmd=command.args,
            stderr=out.stderr.decode("utf-8") if out.stderr else "",
            output=out.stdout.decode("utf-8") if out.stdout else "",
        )

    logger.info(
        "Successful command",
        command=" ".join(command.args),
        exit_code=out.returncode,
        stdout=out.stdout.decode("utf-8") if out.stdout else "",
        stderr=out.stderr.decode("utf-8") if out.stderr else "",
    )

    return out.stdout.decode("utf-8")


def run_commands(commands: list[Command]):
    for command in commands:
        run_logged(command)


def serialize_to_sh(commands: list[Command], sh_cmd_out: pathlib.Path):
    cmds = []
    for cmd in commands:
        cmds.extend(cmd.to_sh())
    with open(sh_cmd_out, "w+") as f:
        f.write("\n".join(cmds))


def serialize_to_json(self, json_cmd_out: pathlib.Path):
    json_content = json.loads(json_cmd_out.read_text())


def is_binary(path: pathlib.Path) -> BinaryType:
    if path.suffix in (".a", ".o"):
        logger.info("Ignoring .a, and .o files", library=path)
        return BinaryType.NONE

    if path.suffix in (".py", ".txt", ".md", ".h", ".class", ".cpp", ".hpp", ".class"):
        return BinaryType.NONE
    file_out = run_logged_read(["file", str(path)]).lower()
    if "mach-o" in file_out:
        if "architectures" in file_out:
            logger.warning(f"Multiple architectures in file", filename=path)
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
