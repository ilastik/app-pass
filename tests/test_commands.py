from pathlib import Path

from app_pass._commands import Command, serialize_to_sh


def test_command_serialization_to_dict_with_cwd():
    cmd = Command(args=["ls", "-l"], cwd=Path("/some/path"))

    json_cmd = cmd.to_dict()
    assert json_cmd == {"args": ["ls", "-l"], "cwd": "/some/path", "comment": None}


def test_command_serialization_to_dict_no_cwd():
    cmd = Command(args=["ls", "-l"], cwd=None)

    json_cmd = cmd.to_dict()
    assert json_cmd == {"args": ["ls", "-l"], "cwd": None, "comment": None}


def test_command_serialization_to_sh_with_cwd():
    cmd = Command(args=["ls", "-l"], cwd=Path("/some/path"))

    sh_cmd = cmd.to_sh()

    assert len(sh_cmd) == 3
    assert sh_cmd[0] == "cd /some/path"
    assert sh_cmd[1] == "ls -l"
    assert sh_cmd[2] == "cd -"


def test_command_serialization_to_sh_with_cwd_with_comment():
    cmd = Command(args=["ls", "-l"], cwd=Path("/some/path"), comment="Something\nMultiline")

    sh_cmd = cmd.to_sh()

    assert len(sh_cmd) == 5
    assert sh_cmd[0] == "# Something"
    assert sh_cmd[1] == "# Multiline"
    assert sh_cmd[2] == "cd /some/path"
    assert sh_cmd[3] == "ls -l"
    assert sh_cmd[4] == "cd -"


def test_command_serialization_to_sh_no_cwd():
    cmd = Command(args=["ls", "-l"], cwd=None)

    sh_cmd = cmd.to_sh()

    assert len(sh_cmd) == 1
    assert sh_cmd[0] == "ls -l"


def test_serialize_to_sh(tmp_path: Path):
    cmds = [Command(["echo", f"{i}"]) for i in range(42)]

    sh_file = tmp_path / "sh_out.sh"

    serialize_to_sh(cmds, sh_file)

    lines = sh_file.read_text().split("\n")
    assert len(lines) == 42

    expected = [f"echo {i}" for i in range(42)]
    assert lines == expected


def test_serialize_to_sh_with_comment(tmp_path: Path):
    cmds = [Command(["echo", f"{i}"], comment=f"This echos {i}") for i in range(42)]

    sh_file = tmp_path / "sh_out.sh"

    serialize_to_sh(cmds, sh_file)

    lines = sh_file.read_text().split("\n")
    assert len(lines) == 42 * 2

    expected_comments = [f"# This echos {i}" for i in range(42)]
    expected_runs = [f"echo {i}" for i in range(42)]
    expected = [x for pair in zip(expected_comments, expected_runs) for x in pair]

    assert lines == expected


def test_serialize_to_sh_with_cwd(tmp_path: Path):
    cmds = [Command(["echo", f"{i}"], cwd=Path(f"/my/home{i}")) for i in range(42)]

    sh_file = tmp_path / "sh_out.sh"

    serialize_to_sh(cmds, sh_file)

    lines = sh_file.read_text().split("\n")
    assert len(lines) == 42 * 3

    expected_cd_in = [f"cd /my/home{i}" for i in range(42)]
    expected_runs = [f"echo {i}" for i in range(42)]
    expected_cd_out = ["cd -" for i in range(42)]
    expected = [x for triple in zip(expected_cd_in, expected_runs, expected_cd_out) for x in triple]

    assert lines == expected


def test_serialize_to_sh_with_all(tmp_path: Path):
    cmds = [Command(["echo", f"{i}"], cwd=Path(f"/my/home{i}"), comment=f"This echos {i}") for i in range(42)]

    sh_file = tmp_path / "sh_out.sh"

    serialize_to_sh(cmds, sh_file)

    lines = sh_file.read_text().split("\n")
    assert len(lines) == 42 * 4

    expected_comments = [f"# This echos {i}" for i in range(42)]
    expected_cd_in = [f"cd /my/home{i}" for i in range(42)]
    expected_runs = [f"echo {i}" for i in range(42)]
    expected_cd_out = ["cd -" for i in range(42)]
    expected = [x for quad in zip(expected_comments, expected_cd_in, expected_runs, expected_cd_out) for x in quad]

    assert lines == expected
