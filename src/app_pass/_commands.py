import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class Command:
    # One or multiple commands that can be executed in the shell
    args: list[str]
    cwd: Optional[Path] = None
    comment: Optional[str] = None


    def to_sh(self) -> list[str]:
        cmds = [" ".join(self.args)]
        if self.cwd:
            cmds.insert(0, f"cd {self.cwd}")
            cmds.append("cd -")

        if self.comment:
            # fix multi-line comments - who knows
            cmds = [f"# {c}" for c in self.comment.split("\n")] + cmds

        return cmds

    def to_dict(self):
        return dict(args=self.args, cwd=str(self.cwd) if self.cwd else None, comment=self.comment)



def serialize_to_sh(commands: list[Command], sh_cmd_out: Path):
    cmds = []
    for cmd in commands:
        cmds.extend(cmd.to_sh())
    with open(sh_cmd_out, "w+") as f:
        f.write("\n".join(cmds))


