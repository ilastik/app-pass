from dataclasses import dataclass
from pathlib import Path
from typing import Optional

@dataclass
class Command:
    # One or multiple commands that can be executed in the shell
    args: list[str]
    cwd: Optional[Path] = None
    comment: Optional[str] = None
    run_python: bool = True

    def to_sh(self) -> list[str]:
        args = [f'"{arg}"' for arg in self.args]
        cmds = [" ".join(args)]
        if self.cwd:
            cmds.insert(0, f'"cd" "{self.cwd}"')
            cmds.append('"cd" "-"')

        if self.comment:
            # fix multi-line comments - who knows
            cmds = [f"# {c}" for c in self.comment.split("\n")] + cmds

        return cmds
