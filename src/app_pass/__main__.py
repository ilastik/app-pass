import logging
from pathlib import Path

import structlog
import typer

from app_pass._app import OSXAPP

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


@app.command()
def check_app(root: Path):
    """Check if .app bundle is likely to pass MacOs Gatekeeper

    Check integrity of binaries:
      * no RC_PATH outside the app
      * all linked libraries can be reached within the app or
        in "/System/", "/usr/", "/Library/".

    Check all binaries are signed.
    """
    app = OSXAPP.from_path(root)
    app.check_binaries()

    # print(f"{set(x.header.filetype for x in macho_binaries)=}, {set(x.header.magic for x in macho_binaries)=}")
    # print(set(lib for x in macho_binaries for lib in x.dylibs))


@app.command()
def fix():
    """Fix issues in mach-o libraries .app bundle

    Remove paths that point outside the app.
    """
    pass


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
