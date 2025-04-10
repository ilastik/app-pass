import atexit
import shutil
import tempfile
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Optional

from rich.progress import Progress

from app_pass._macho import MachOBinary, parse_macho, sign_impl

from ._util import BinaryObj, BinaryType, is_binary, run_logged_act


@dataclass
class Jar(BinaryObj):

    temp_path: Path
    binaries: list[MachOBinary]

    @staticmethod
    def from_path(p: Path, progress: Optional[Progress]) -> "Jar":
        if progress:
            task = progress.add_task(f"tempdir({p.name})", total=None)
        t = tempfile.mkdtemp()
        run_logged_act(["ditto", "-x", "-k", str(p), t], dry_run=False, intends_side_effect=True)

        files = list(Path(t).glob("**/*"))

        if progress:
            progress.update(task, total=len(files))

        machos = []
        for file in files:
            binary_type = is_binary(file)

            if binary_type == BinaryType.MACHO:
                machos.append(parse_macho(file))
            elif binary_type == BinaryType.JAR:
                print(f"Nested jar in {p}: {file} - not expected")

            if progress:
                progress.advance(task, 1)

        if progress:
            progress.remove_task(task)

        atexit.register(partial(shutil.rmtree, t, ignore_errors=True))

        return Jar(p, Path(t), machos)

    def sign(self, entitlement_file, developer_id, dry_run):
        for binary in self.binaries:
            sign_impl(entitlement_file, developer_id, binary.path, dry_run=False)
        # run_logged_act(["mv", str(self.path), str(self.path.with_suffix(".bak"))], dry_run=False, intends_side_effect=True)
        run_logged_act(
            ["ditto", "-v", "-c", "-k", "--keepParent", str(self.temp_path), self.path.with_suffix(".zip").name],
            dry_run=False,
            intends_side_effect=False,
            cwd=str(self.temp_path),
        )
        run_logged_act(
            ["mv", str(self.temp_path / self.path.with_suffix(".zip").name), str(self.path)],
            dry_run=False,
            intends_side_effect=True,
        )
