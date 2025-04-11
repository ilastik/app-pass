import enum
import pathlib
import subprocess
from dataclasses import dataclass
from typing import Iterator, Tuple

import structlog
from rich.progress import Progress

logger = structlog.get_logger()


class BinaryType(enum.Enum):
    NONE = enum.auto()
    MACHO = enum.auto()
    JAR = enum.auto()


@dataclass
class BinaryObj:
    path: pathlib.Path


def run_logged_read(args: list[str], **kwargs) -> str:
    return run_logged_act(args, dry_run=False, intends_side_effect=False, **kwargs)


def run_logged_act(args: list[str], dry_run=True, intends_side_effect=True, **kwargs) -> str:
    logger.debug("About to execute", command=" ".join(args), side_effect=intends_side_effect)
    if dry_run:
        return ""

    out = subprocess.run(args, stdout=subprocess.PIPE, stdin=subprocess.PIPE, **kwargs)
    if out.returncode != 0:
        logger.warning(
            "Nonzero exit code from command",
            command=" ".join(args),
            exit_code=out.returncode,
            stderr=out.stderr.decode("utf-8") if out.stderr else "",
            output=out.stdout.decode("utf-8") if out.stdout else "",
        )
        raise subprocess.CalledProcessError(
            returncode=out.returncode,
            cmd=" ".join(args),
            stderr=out.stderr.decode("utf-8") if out.stderr else "",
            output=out.stdout.decode("utf-8") if out.stdout else "",
        )

    if intends_side_effect:
        log_fun = logger.info
    else:
        log_fun = logger.debug

    log_fun(
        "Successful command",
        command=" ".join(args),
        exit_code=out.returncode,
        stdout=out.stdout.decode("utf-8") if out.stdout else "",
        stderr=out.stderr.decode("utf-8") if out.stderr else "",
    )

    return out.stdout.decode("utf-8")


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
