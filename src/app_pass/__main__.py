import json
import logging
from argparse import ArgumentParser, Namespace
from contextlib import ExitStack
from functools import partial
from itertools import chain
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import structlog
from rich.console import Console
from rich.text import Text

from app_pass._app import OSXAPP
from app_pass._issues import Issue
from app_pass._macho import sign_impl

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


def parse_args() -> Namespace:

    common_args = ArgumentParser(add_help=False)
    common_args.add_argument("-v", "--verbose", action="count", default=0)
    common_args.add_argument("--sh-output", type=Path)
    common_args.add_argument("--dry-run", action="store_true")
    common_args.add_argument("app_bundle", type=Path)

    fix_args = ArgumentParser(add_help=False)
    fix_args.add_argument("--rc-path-delete", action="store_true")
    fix_args.add_argument("--force_update", action="store_true")

    sign_args = ArgumentParser(add_help=False)
    sign_args.add_argument("entitlement_file", type=Path)
    sign_args.add_argument("developer_id", type=str)

    parser = ArgumentParser()

    subparsers = parser.add_subparsers(dest="action", help="action to perform on an .app bundle")
    check = subparsers.add_parser("check", parents=[common_args])

    fix = subparsers.add_parser("fix", parents=[common_args, fix_args])
    sign = subparsers.add_parser("sign", parents=[common_args, sign_args])

    fixsign = subparsers.add_parser("fixsign", parents=[common_args, sign_args, fix_args])

    return parser.parse_args()


def check(app: OSXAPP):
    """Check if .app bundle is likely to pass MacOs Gatekeeper

    Check integrity of binaries:
      * no RC_PATH outside the app
      * all linked libraries can be reached within the app or
        in "/System/", "/usr/", "/Library/".

    Check all binaries are signed.
    """
    fix(app, dry_run=True)


def fix(app: OSXAPP, rc_path_delete: bool = False, force_update: bool = False, dry_run: bool = False):
    """Fix issues in mach-o libraries .app bundle

    Remove paths that point outside the app.

    Args:
        rc_path_delete: delete rc_paths that point outside the app. Use with care

    """
    issues = app.check_macho_binaries(rc_path_delete=rc_path_delete)
    issues.extend(app.check_jar_binaries(force_update=force_update))
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


def sign(app: OSXAPP, entitlement_file: Path, developer_id: str, dry_run: bool = False):
    with ExitStack() as xstack:
        for ctx in _PROCESSORS:
            xstack.enter_context(ctx)

        for jar in app.jars:
            jar.sign(entitlement_file, developer_id, dry_run)

        for binary in chain(app.macho_binaries, app.jars):
            sign_impl(entitlement_file, developer_id, binary.path, dry_run)

        sign_impl(entitlement_file, developer_id, app.bundle_exe, dry_run)
        sign_impl(entitlement_file, developer_id, app.root, dry_run)


def fixsign(app: OSXAPP, entitlement_file: Path, developer_id: str, rc_path_delete: bool=False, force_update: bool=False, dry_run: bool = False):
    fix(app, rc_path_delete, force_update, dry_run)
    sign(app, entitlement_file, developer_id, dry_run)

def main():
    args = parse_args()
    configure_logging(verbose=args.verbose, json_cmd_out=args.json_output, sh_cmd_out=args.sh_output)

    with OSXAPP.from_path(args.app_bundle) as app:
        match args.action:
            case "check":
                return check(app)
            case "fix":
                return fix(app, args.rc_path_delete, args.force_update, args.dry_run)
            case "sign":
                return sign(app, args.entitlement_file, args.developer_id, args.dry_run)
            case "fixsign":
                return fixsign(app, args.entitlement_file, args.developer_id, args.rc_path_delete, args.force_update, args.dry_run)
            case _:
                raise ValueError(f"Unexpected action {args.action}")


if __name__ == "__main__":
    main()
