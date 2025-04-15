import atexit
import logging
import shutil
import tempfile
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Optional

from rich.progress import Progress

from app_pass._commands import Command
from app_pass._macho import MachOBinary, parse_macho, sign_impl

from ._util import BinaryObj, BinaryType, is_binary, run_logged

logger = logging.getLogger(__name__)


@dataclass
class Jar(BinaryObj):

    temp_path: Path
    binaries: list[MachOBinary]

    @staticmethod
    def from_path(p: Path, progress: Optional[Progress]) -> "Jar":
        if progress:
            task = progress.add_task(f"tempdir({p.name})", total=None)
        t = tempfile.mkdtemp()
        run_logged(Command(["ditto", "-x", "-k", str(p), t]))

        files = list(Path(t).glob("**/*"))

        if progress:
            progress.update(task, total=len(files))

        machos = []
        for file in files:
            binary_type = is_binary(file)

            if binary_type == BinaryType.MACHO:
                machos.append(parse_macho(file))
            elif binary_type == BinaryType.JAR:
                logger.warning(f"Nested jar in {p}: {file} - not expected")

            if progress:
                progress.advance(task, 1)

        if progress:
            progress.remove_task(task)

        def _cleanup(t):
            print(f"Cleaning up {t}")
            shutil.rmtree(t, ignore_errors=True)

        atexit.register(partial(_cleanup, t))

        return Jar(path=p, temp_path=Path(t), binaries=machos)

    @property
    def create_commands(self) -> list[Command]:
        return [
            Command(["mkdir", "-p", str(self.temp_path)], run_python=False),
            Command(["ditto", "-x", "-k", str(self.path), str(self.temp_path)], run_python=False)
        ]

    def sign(self, entitlement_file, developer_id) -> list[Command]:
        # nothing needs to be done if there aren't any binaries
        if not self.binaries:
            return []

        sign_commands = []

        for binary in self.binaries:
            sign_commands.append(sign_impl(entitlement_file, developer_id, binary.path))

        return sign_commands

    def repack(self) -> list[Command]:
        pack_command = Command(
            args=["ditto", "-v", "-c", "-k", str(self.temp_path), self.path.with_suffix(".zip").name],
            cwd=self.temp_path,
        )
        move_command = Command(args=["mv", str(self.temp_path / self.path.with_suffix(".zip").name), str(self.path)])
        return [pack_command, move_command]
