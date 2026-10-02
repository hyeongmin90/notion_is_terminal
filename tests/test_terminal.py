from pathlib import Path

import pytest

from notion_is_terminal.config import CredentialFileSettings, SandboxSettings, TerminalSettings
from notion_is_terminal.terminal import (
    SANDBOX_WORKSPACE,
    SENTINEL_PREFIX,
    CredentialMaskStore,
    CredentialSentinelRegistry,
    build_sandbox_launch,
    extract_and_substitute,
    prepare_credential_masks,
)


def _settings(
    tmp_path: Path,
    *,
    mode: str,
    deny_read=None,
    deny_write=None,
    credential_files=None,
):
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
            credential_files=list(credential_files or []),
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


def test_extract_masks_only_capture_and_preserves_structure():
    registry = CredentialSentinelRegistry()
    content = "API_KEY=real-secret\nPORT=8080\n"
    result = extract_and_substitute(
        content,
        r"(?m)^API_KEY=(\S+)$",
        lambda value, index: registry.register(f"file:.env#{index}", value),
    )

    assert result is not None
    fake, captures = result
    assert captures == ["real-secret"]
    assert "API_KEY=real-secret" not in fake
    assert "PORT=8080" in fake
    sentinel = fake.split("API_KEY=", 1)[1].splitlines()[0]
    assert sentinel.startswith(SENTINEL_PREFIX)
    assert registry.lookup_real(sentinel) == "real-secret"


def test_extract_reuses_sentinel_for_duplicate_capture():
    registry = CredentialSentinelRegistry()
    result = extract_and_substitute(
        "token=A\ntoken=A\ntoken=B\n",
        r"token=(\S+)",
        lambda value, index: registry.register(f"k#{index}", value),
    )
    assert result is not None
    fake, captures = result
    assert captures == ["A", "B"]
    lines = fake.splitlines()
    assert lines[0] == lines[1]
    assert lines[0] != lines[2]


def test_extract_mask_duplicates_masks_unmatched_copy():
    registry = CredentialSentinelRegistry()
    result = extract_and_substitute(
        "token=abc123\n# backup abc123\n",
        r"token=(\S+)",
        lambda value, index: registry.register(f"k#{index}", value),
        mask_duplicates=True,
    )
    assert result is not None
    fake, _ = result
    assert "abc123" not in fake
    sentinel = fake.split("token=", 1)[1].splitlines()[0]
    assert f"# backup {sentinel}" in fake


def test_prepare_structured_mask_writes_0600_fake_and_keeps_original(tmp_path):
    entry = CredentialFileSettings(
        path=".env",
        mode="mask",
        extract=r"(?m)^API_KEY=(\S+)$",
    )
    settings, workspace = _settings(
        tmp_path,
        mode="workspace",
        credential_files=[entry],
    )
    env_file = workspace / ".env"
    env_file.write_text("API_KEY=real-secret\nPORT=8080\n", encoding="utf-8")
    registry = CredentialSentinelRegistry()
    store = CredentialMaskStore()
    try:
        binds, deny = prepare_credential_masks(
            settings,
            cwd=workspace,
            registry=registry,
            store=store,
        )
        assert deny == []
        assert len(binds) == 1
        fake = binds[0].fake_path.read_text(encoding="utf-8")
        assert "real-secret" not in fake
        assert "PORT=8080" in fake
        assert binds[0].target_path == Path("/workspace/.env")
        assert binds[0].fake_path.stat().st_mode & 0o777 == 0o600
        assert env_file.read_text(encoding="utf-8") == "API_KEY=real-secret\nPORT=8080\n"
    finally:
        store.close()


def test_prepare_whole_file_mask_replaces_entire_content(tmp_path):
    entry = CredentialFileSettings(path="token.txt", mode="mask")
    settings, workspace = _settings(
        tmp_path,
        mode="workspace",
        credential_files=[entry],
    )
    token = workspace / "token.txt"
    token.write_text("super-secret", encoding="utf-8")
    registry = CredentialSentinelRegistry()
    store = CredentialMaskStore()
    try:
        binds, deny = prepare_credential_masks(
            settings,
            cwd=workspace,
            registry=registry,
            store=store,
        )
        assert deny == []
        fake = binds[0].fake_path.read_text(encoding="utf-8")
        assert fake.startswith(SENTINEL_PREFIX)
        assert "super-secret" not in fake
        assert registry.lookup_real(fake) == "super-secret"
    finally:
        store.close()


def test_extract_no_match_deny_degrades_to_read_deny(tmp_path):
    entry = CredentialFileSettings(
        path=".env",
        mode="mask",
        extract=r"TOKEN=(\S+)",
        on_extract_no_match="deny",
    )
    settings, workspace = _settings(
        tmp_path,
        mode="workspace",
        credential_files=[entry],
    )
    env_file = workspace / ".env"
    env_file.write_text("PORT=8080\n", encoding="utf-8")
    registry = CredentialSentinelRegistry()
    store = CredentialMaskStore()
    try:
        binds, deny = prepare_credential_masks(
            settings,
            cwd=workspace,
            registry=registry,
            store=store,
        )
        assert binds == []
        assert deny == [(env_file.resolve(), Path("/workspace/.env"))]
    finally:
        store.close()


def test_extract_no_match_error_aborts(tmp_path):
    entry = CredentialFileSettings(
        path=".env",
        mode="mask",
        extract=r"TOKEN=(\S+)",
        on_extract_no_match="error",
    )
    settings, workspace = _settings(
        tmp_path,
        mode="workspace",
        credential_files=[entry],
    )
    (workspace / ".env").write_text("PORT=8080\n", encoding="utf-8")
    registry = CredentialSentinelRegistry()
    store = CredentialMaskStore()
    try:
        with pytest.raises(RuntimeError, match="matched nothing"):
            prepare_credential_masks(
                settings,
                cwd=workspace,
                registry=registry,
                store=store,
            )
    finally:
        store.close()


def test_build_launch_ro_binds_fake_over_real_path(tmp_path):
    entry = CredentialFileSettings(
        path=".env",
        mode="mask",
        extract=r"API_KEY=(\S+)",
    )
    settings, workspace = _settings(
        tmp_path,
        mode="workspace",
        credential_files=[entry],
    )
    (workspace / ".env").write_text("API_KEY=secret\n", encoding="utf-8")
    registry = CredentialSentinelRegistry()
    store = CredentialMaskStore()
    try:
        binds, deny = prepare_credential_masks(
            settings,
            cwd=workspace,
            registry=registry,
            store=store,
        )
        launch = build_sandbox_launch(
            settings,
            cwd=workspace,
            shell=Path("/bin/bash"),
            rcfile=None,
            bwrap_path="/usr/bin/bwrap",
            masked_file_binds=binds,
            credential_deny_read=deny,
        )
        triples = list(zip(launch.argv, launch.argv[1:], launch.argv[2:]))
        assert (
            "--ro-bind",
            str(binds[0].fake_path),
            "/workspace/.env",
        ) in triples
    finally:
        store.close()
