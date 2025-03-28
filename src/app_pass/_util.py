import pathlib
import subprocess
from typing import Optional

import structlog
from rich.progress import track

logger = structlog.get_logger()


def run_logged_read(args: list[str]) -> str:
    return run_logged_act(args, dry_run=False, intends_side_effect=False)


def run_logged_act(args: list[str], dry_run=True, intends_side_effect=True) -> str:
    logger.debug("About to execute", command=" ".join(args), side_effect=intends_side_effect)
    if dry_run:
        return ""

    out = subprocess.run(args, stdout=subprocess.PIPE, stdin=subprocess.PIPE)
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


def is_macho(path: pathlib.Path) -> bool:
    file_out = run_logged_read(["file", str(path)]).lower()
    if "mach-o" in file_out:
        if path.suffix == ".a":
            logger.info("Ignoring static library", library=path)
            return False

        if "architectures" in file_out:
            logger.warning(f"Multiple architectures in file", filename=path)
        return True

    return False


def iter_all_binaries(root: pathlib.Path, description: Optional[str] = None):
    desc = description or "Scanning..."
    print("remember to scan all, this is for dev only")
    for f in track(list(root.glob("**/*.dylib")) + list(root.glob("**/*.so")), description=desc):
        if is_macho(f):
            yield f
