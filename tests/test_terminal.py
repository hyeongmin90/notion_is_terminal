from pathlib import Path

import pytest

from notion_is_terminal.config import SandboxSettings, TerminalSettings
from notion_is_terminal.terminal import SANDBOX_WORKSPACE, build_sandbox_launch


def _settings(tmp_path: Path, *, mode: str, deny_read=None, deny_write=None):
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    return TerminalSettings(
        shell="/bin/bash",
        cwd=str(workspace),
        sandbox=SandboxSettings(
            mode=mode,
            workspace=str(workspace),
            deny_read=list(deny_read or []),
            deny_write=list(deny_write or []),
        ),
    ), workspace


def test_none_mode_launches_shell_directly(tmp_path):
    settings, workspace = _settings(tmp_path, mode="none")
    launch = build_sandbox_launch(
        settings,
        cwd=workspace,
        shell=Path("/bin/bash"),
        rcfile=None,
    )

    assert launch.executable == "/bin/bash"
    assert launch.argv == ["/bin/bash", "-i"]
    assert launch.cwd == str(workspace)
    assert launch.home is None


def test_read_only_mode_mounts_host_root_read_only(tmp_path):
    settings, workspace = _settings(tmp_path, mode="read_only")
    launch = build_sandbox_launch(
        settings,
        cwd=workspace,
        shell=Path("/bin/bash"),
        rcfile=None,
        bwrap_path="/usr/bin/bwrap",
    )

    assert launch.executable == "/usr/bin/bwrap"
    assert ["--ro-bind", "/", "/"] == launch.argv[3:6]
    assert "--proc" in launch.argv
    assert "--dev" in launch.argv
    assert "--tmpfs" in launch.argv
    assert launch.cwd == str(workspace)
    assert launch.home is None


def test_workspace_mode_exposes_only_workspace_as_user_data(tmp_path):
    settings, workspace = _settings(tmp_path, mode="workspace")
    launch = build_sandbox_launch(
        settings,
        cwd=workspace,
        shell=Path("/bin/bash"),
        rcfile=None,
        bwrap_path="/usr/bin/bwrap",
    )

    argv = launch.argv
    bind_index = argv.index("--bind")
    assert argv[bind_index + 1] == str(workspace)
    assert argv[bind_index + 2] == str(SANDBOX_WORKSPACE)
    assert ["--ro-bind", "/", "/"] != argv[3:6]
    assert launch.cwd == "/workspace"
    assert launch.home == "/tmp/t4g-home"


def test_workspace_deny_write_remounts_subpath_read_only(tmp_path):
    settings, workspace = _settings(tmp_path, mode="workspace", deny_write=["protected"])
    protected = workspace / "protected"
    protected.mkdir()

    launch = build_sandbox_launch(
        settings,
        cwd=workspace,
        shell=Path("/bin/bash"),
        rcfile=None,
        bwrap_path="/usr/bin/bwrap",
    )

    triples = list(zip(launch.argv, launch.argv[1:], launch.argv[2:]))
    assert ("--ro-bind", str(protected), "/workspace/protected") in triples


def test_workspace_deny_read_masks_original_content(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()

    settings, workspace = _settings(tmp_path, mode="workspace", deny_read=["secret.txt"])
    secret = workspace / "secret.txt"
    secret.write_text("secret", encoding="utf-8")

    launch = build_sandbox_launch(
        settings,
        cwd=workspace,
        shell=Path("/bin/bash"),
        rcfile=None,
        bwrap_path="/usr/bin/bwrap",
    )

    triples = list(zip(launch.argv, launch.argv[1:], launch.argv[2:]))
    matching = [triple for triple in triples if triple[0] == "--ro-bind" and triple[2] == "/workspace/secret.txt"]
    assert len(matching) == 1
    assert matching[0][1] != str(secret)
    assert matching[0][1].endswith("deny-file")


def test_workspace_policy_cannot_escape_workspace(tmp_path):
    settings, workspace = _settings(tmp_path, mode="workspace", deny_read=["../outside.txt"])
    (tmp_path / "outside.txt").write_text("outside", encoding="utf-8")

    with pytest.raises(ValueError, match="must stay inside"):
        build_sandbox_launch(
            settings,
            cwd=workspace,
            shell=Path("/bin/bash"),
            rcfile=None,
            bwrap_path="/usr/bin/bwrap",
        )
