import json
import logging
from contextlib import ExitStack
from functools import partial
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import structlog
import typer
from rich.console import Console
from rich.text import Text

from app_pass._app import OSXAPP
from app_pass._issues import Issue

app = typer.Typer(name="app-pass", no_args_is_help=True, add_completion=False, pretty_exceptions_enable=False)
shared_options: Dict[str, int | None | Path] = dict(verbose=0, json_cmd_out=None, sh_cmd_out=None)

_PROCESSORS: List[Callable] = []


class SHLogger:
    def __init__(self, filename: Path):
        self._filename: Path = filename
        self._handle = None

    def __call__(self, _logger, _method_name, event_dict: dict):
        if self._handle is None:
            return event_dict
        if event_dict.get("side_effect", None):
            if cmd := event_dict.get("command", None):
                self._handle.write(f"{cmd}\n")
        return event_dict

    def __enter__(self):
        self._handle = self._filename.open("w")

    def __exit__(self, *_):
        if self._handle:
            self._handle.close()


class JSONLogger:
    def __init__(self, filename: Path):
        self._filename: Path = filename
        self._handle = None
        self._div = ""

    def __call__(self, _logger, _method_name, event_dict: dict):
        if self._handle is None:
            return event_dict
        if event_dict.get("side_effect", None):
            if cmd := event_dict.get("command", None):
                msg = json.dumps(dict(command=cmd))
                self._handle.write(f"{self._div}\n{msg}")
                if self._div == "":
                    self._div = ","
        return event_dict

    def __enter__(self):
        self._handle = self._filename.open("w")
        self._handle.write("[\n")

    def __exit__(self, *_):
        if self._handle:
            self._handle.write("]\n")
            self._handle.close()


def _drop_lvl(level, _logger, _method_name, event_dict: dict):
    if event_dict["level_number"] < level:
        raise structlog.DropEvent

    return event_dict


def configure_logging(verbose: int, json_cmd_out: Optional[Path] = None, sh_cmd_out: Optional[Path] = None):
    verbosity = {0: logging.ERROR, 1: logging.WARNING, 2: logging.INFO, 3: logging.DEBUG}
    processors = [
        structlog.stdlib.add_log_level_number,
        partial(_drop_lvl, verbosity[verbose]),
        structlog.stdlib.render_to_log_kwargs,
        structlog.dev.ConsoleRenderer(),
    ]
    if sh_cmd_out:
        _PROCESSORS.append(SHLogger(sh_cmd_out))

    if json_cmd_out:
        _PROCESSORS.append(JSONLogger(json_cmd_out))

    structlog.configure(
        processors=_PROCESSORS + processors,
        wrapper_class=structlog.BoundLogger,
        logger_factory=structlog.PrintLoggerFactory(),
    )


@app.callback()
def _shared_flags(
    verbose: int = typer.Option(0, "-v", "--verbose", help="If set print debug messages", count=True),
    json_cmd_out: Optional[Path] = typer.Option(None, "--json-cmd-out"),
    sh_cmd_out: Optional[Path] = typer.Option(None, "--sh-cmd-out"),
):
    shared_options["verbose"] = verbose
    shared_options["json_cmd_out"] = json_cmd_out
    shared_options["sh_cmd_out"] = sh_cmd_out
    configure_logging(verbose, json_cmd_out, sh_cmd_out)


def print_summary(app: OSXAPP, issues: Sequence[Issue]):
    console = Console()
    text = Text()
    text.append(f"Summary for {app.root}\n", style="bold magenta")
    if not issues:
        text.append("Found no issues!", style="bold lime")
    else:
        text.append(
            text.assemble(
                ("Found ", ""),
                (f"{len(issues)} ", "bold red"),
                ("issues of which ", ""),
                (f"{len([issue for issue in issues if issue.fixable])} ", "bold green"),
                ("can be fixed.", ""),
            )
        )

    console.print(text)


def print_unfixable(app: OSXAPP, issues: Sequence[Issue]):
    console = Console()
    text = Text()
    for issue in issues:
        text.append(
            text.assemble(
                ("Could ", ""),
                (f"not ", "bold red"),
                ("fix issue: ", ""),
                (f"{issue.details}\n ", "red"),
            )
        )

    console.print(text)


@app.command()
def check(root: Path):
    """Check if .app bundle is likely to pass MacOs Gatekeeper

    Check integrity of binaries:
      * no RC_PATH outside the app
      * all linked libraries can be reached within the app or
        in "/System/", "/usr/", "/Library/".

    Check all binaries are signed.
    """
    app = OSXAPP.from_path(root)
    issues = app.check_binaries()
    print_summary(app, issues)


@app.command()
def info(root: Path):
    fix(root, dry_run=True)


@app.command()
def fix(root: Path, dry_run: bool = False):
    """Fix issues in mach-o libraries .app bundle

    Remove paths that point outside the app.
    """
    app = OSXAPP.from_path(root)
    issues = app.check_binaries()

    print_summary(app, issues)

    with ExitStack() as xstack:
        for ctx in _PROCESSORS:
            xstack.enter_context(ctx)
        for issue in issues:
            if issue.fixable:
                assert issue.fix
                issue.fix(dry_run=dry_run)

    unfixable = [issue for issue in issues if not issue.fixable]

    print_unfixable(app, unfixable)


@app.command()
def sign():
    """Sign all binaries in the .app bundle"""
    pass


@app.command()
def notarize():
    """Zip app bundle using ditto and send off for notarization"""
    pass


@app.command()
def make_pass():
    """fix, sign, and notarize app"""
    pass


def main():
    app()


if __name__ == "__main__":
    main()
