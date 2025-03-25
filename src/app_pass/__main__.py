import logging
from pathlib import Path
from typing import Optional, Sequence

import structlog
import typer
from rich.console import Console
from rich.text import Text

from app_pass._app import OSXAPP
from app_pass._issues import Issue

app = typer.Typer(name="app-pass", no_args_is_help=True, add_completion=False, pretty_exceptions_enable=False)
shared_options = {}


def configure_logging(verbose: int):
    verbosity = {0: logging.ERROR, 1: logging.WARNING, 2: logging.INFO, 3: logging.DEBUG}
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(verbosity[verbose]),
    )


@app.callback()
def _shared_flags(
    verbose: int = typer.Option(0, "-v", "--verbose", help="If set print debug messages", count=True),
):
    shared_options["verbose"] = verbose
    configure_logging(verbose)


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

    app.check_binaries()

    # print(f"{set(x.header.filetype for x in macho_binaries)=}, {set(x.header.magic for x in macho_binaries)=}")
    # print(set(lib for x in macho_binaries for lib in x.dylibs))


@app.command()
def fix(root: Path, dry_run: bool=False):
    """Fix issues in mach-o libraries .app bundle

    Remove paths that point outside the app.
    """
    app = OSXAPP.from_path(root)
    issues = app.check_binaries()
    print_summary(app, issues)
    if dry_run:
        return

    for issue in issues:
        issue.fix(dry_run=dry_run)


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
