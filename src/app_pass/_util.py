import pathlib
import subprocess

import structlog
from rich.progress import track

logger = structlog.get_logger()


def run_logged(args: list[str]) -> str:
    out = subprocess.run(args, stdout=subprocess.PIPE, stdin=subprocess.PIPE)
    if out.returncode != 0:
        logger.warning(
            "Nonzero exit code from command",
            command=" ".join(args),
            exit_code=out.returncode,
            stdout=out.stdout.decode("utf-8"),
            stderr=out.stderr.decode("utf-8"),
        )
        raise subprocess.CalledProcessError(
            returncode=out.returncode,
            cmd=args,
            stderr=out.stderr.decode("utf-8") if out.stderr else "",
            output=out.stdout.decode("utf-8") if out.stdout else "",
        )

    logger.debug(
        "Successful command",
        command=" ".join(args),
        exit_code=out.returncode,
        stdout=out.stdout.decode("utf-8") if out.stdout else "",
        stderr=out.stderr.decode("utf-8") if out.stderr else "",
    )

    return out.stdout.decode("utf-8")


def is_macho(path: pathlib.Path) -> bool:
    if "mach-o" in run_logged(["file", str(path)]).lower():
        return True

    return False


def iter_all_binaries(root: pathlib.Path):
    for f in track(list(root.glob("**/*"))):
        if is_macho(f):
            yield f
