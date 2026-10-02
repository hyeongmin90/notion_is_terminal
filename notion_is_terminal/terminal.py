from __future__ import annotations

import codecs
import errno
import fcntl
import os
import pty
import re
import shlex
import shutil
import signal
import struct
import tempfile
import termios
from dataclasses import dataclass
from pathlib import Path
from secrets import choice
from uuid import uuid4
from urllib.parse import unquote

import pyte

from .config import TerminalSettings


OSC7_RE = re.compile(r"\x1b]7;file://[^/]*(/[^\x07\x1b]*)\x07")

SANDBOX_WORKSPACE = Path("/workspace")
SANDBOX_HOME = Path("/tmp/t4g-home")
SANDBOX_RCFILE = Path("/tmp/t4g-bashrc")


@dataclass(slots=True)
class SandboxLaunch:
    executable: str
    argv: list[str]
    cwd: str
    home: str | None = None


SENTINEL_PREFIX = "fake_value_"
SENTINEL_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789_-"


@dataclass(slots=True)
class MaskedFileBind:
    fake_path: Path
    target_path: Path


class CredentialSentinelRegistry:
    """Per-PTY in-memory sentinel→real credential mapping."""

    def __init__(self) -> None:
        self._by_name: dict[str, tuple[str, str]] = {}
        self._by_sentinel: dict[str, str] = {}

    def register(self, name: str, real_value: str) -> str:
        existing = self._by_name.get(name)
        if existing is not None:
            sentinel, old_real = existing
            if old_real != real_value:
                self._by_sentinel.pop(sentinel, None)
                self._by_name[name] = (sentinel, real_value)
                self._by_sentinel[sentinel] = real_value
            return sentinel

        sentinel = _mint_sentinel(real_value)
        self._by_name[name] = (sentinel, real_value)
        self._by_sentinel[sentinel] = real_value
        return sentinel

    def lookup_real(self, sentinel: str) -> str | None:
        return self._by_sentinel.get(sentinel)

    @property
    def size(self) -> int:
        return len(self._by_name)


class CredentialMaskStore:
    """Host-only temp store for read-only fake credential files."""

    def __init__(self) -> None:
        self._dir: Path | None = None
        self._by_key: dict[str, Path] = {}

    def write(self, key: str, content: str) -> Path:
        if self._dir is None:
            self._dir = Path(tempfile.mkdtemp(prefix="t4g-credmask-"))

        fake_path = self._by_key.get(key)
        if fake_path is None:
            fake_path = self._dir / f"{len(self._by_key)}.fake"
            self._by_key[key] = fake_path

        try:
            fake_path.unlink(missing_ok=True)
        except OSError:
            pass
        fake_path.write_text(content, encoding="utf-8")
        fake_path.chmod(0o600)
        return fake_path

    @property
    def dir_path(self) -> Path | None:
        return self._dir

    def close(self) -> None:
        if self._dir is not None:
            shutil.rmtree(self._dir, ignore_errors=True)
        self._dir = None
        self._by_key.clear()


def _mint_sentinel(real_value: str) -> str:
    base = SENTINEL_PREFIX + str(uuid4())
    pad = len(real_value.encode("utf-8")) - len(base)
    if pad <= 0:
        return base
    return base + "".join(choice(SENTINEL_ALPHABET) for _ in range(pad))


def extract_and_substitute(
    content: str,
    pattern: str,
    sentinel_for: callable,
    *,
    mask_duplicates: bool = False,
) -> tuple[str, list[str]] | None:
    """Replace regex capture-group 1 spans with stable sentinels.

    The regex may match repeatedly. Equal captured values share one sentinel.
    When mask_duplicates is enabled, equal verbatim occurrences elsewhere in
    the original content are masked too, longest capture first.
    """
    compiled = re.compile(pattern)
    if compiled.groups != 1:
        raise ValueError("Credential extract regex must contain exactly one capture group")

    captures: list[str] = []
    capture_index: dict[str, int] = {}
    spans: list[tuple[int, int, str]] = []

    for match in compiled.finditer(content):
        value = match.group(1)
        if value is None:
            raise ValueError("Credential extract regex produced an undefined capture group 1")
        if value == "":
            continue
        index = capture_index.get(value)
        if index is None:
            index = len(captures)
            capture_index[value] = index
            captures.append(value)
        replacement = sentinel_for(value, index)
        spans.append((match.start(1), match.end(1), replacement))

    if not spans:
        return None

    if mask_duplicates:
        claimed = [(start, end) for start, end, _ in spans]
        sentinel_by_value = {
            value: sentinel_for(value, capture_index[value])
            for value in captures
        }
        for value in sorted(captures, key=len, reverse=True):
            replacement = sentinel_by_value[value]
            offset = 0
            while True:
                start = content.find(value, offset)
                if start < 0:
                    break
                end = start + len(value)
                if not any(start < c_end and end > c_start for c_start, c_end in claimed):
                    spans.append((start, end, replacement))
                    claimed.append((start, end))
                offset = start + max(len(value), 1)

    spans.sort(key=lambda item: item[0])
    out: list[str] = []
    cursor = 0
    for start, end, replacement in spans:
        if start < cursor:
            continue
        out.append(content[cursor:start])
        out.append(replacement)
        cursor = end
    out.append(content[cursor:])
    return "".join(out), captures


def prepare_credential_masks(
    settings: TerminalSettings,
    *,
    cwd: Path,
    registry: CredentialSentinelRegistry,
    store: CredentialMaskStore,
) -> tuple[list[MaskedFileBind], list[tuple[Path, Path]]]:
    """Build Claude-style fake-file binds and fail-closed deny fallbacks."""
    if not settings.sandbox.masking:
        return [], []

    entries = settings.sandbox.credential_files
    if not entries:
        return [], []

    workspace = (
        Path(settings.sandbox.workspace_path or settings.cwd).expanduser().resolve()
        if settings.sandbox.workspace
        else None
    )
    base = workspace if workspace is not None else cwd

    binds: list[MaskedFileBind] = []
    deny_pairs: list[tuple[Path, Path]] = []

    for item in entries:
        candidate = Path(item.path).expanduser()
        if not candidate.is_absolute():
            candidate = base / candidate

        try:
            real_path = candidate.resolve(strict=True)
        except (FileNotFoundError, OSError) as exc:
            print(f"[credential-mask] skipping unavailable file {item.path}: {exc}")
            continue

        target_path = _host_path_to_sandbox(
            real_path,
            workspace=workspace,
        )

        if item.mode == "deny":
            deny_pairs.append((real_path, target_path))
            continue

        if real_path.is_dir():
            print(
                f"[credential-mask] skipping directory in mask mode: {item.path}; "
                "use mode='deny' for directories"
            )
            continue

        try:
            raw = real_path.read_bytes()
            content = raw.decode("utf-8", errors="strict")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"[credential-mask] skipping unreadable/non-UTF8 file {item.path}: {exc}")
            continue

        key = f"file:{real_path}"
        if not item.extract:
            fake_content = registry.register(key, content)
        else:
            result = extract_and_substitute(
                content,
                item.extract,
                lambda value, index: registry.register(f"{key}#{index}", value),
                mask_duplicates=item.mask_duplicates,
            )
            if result is None:
                policy = item.on_extract_no_match
                if policy == "error":
                    raise RuntimeError(
                        f"Credential mask extract matched nothing for {item.path}"
                    )
                if policy == "deny":
                    print(
                        f"[credential-mask] extract matched nothing for {item.path}; "
                        "degrading to deny"
                    )
                    deny_pairs.append((real_path, target_path))
                    continue
                print(
                    f"[credential-mask] WARNING: extract matched nothing for {item.path}; "
                    "file is left unprotected"
                )
                continue
            fake_content, _captures = result

        fake_path = store.write(key, fake_content)
        binds.append(MaskedFileBind(fake_path=fake_path, target_path=target_path))

    return binds, deny_pairs


def _host_path_to_sandbox(
    host_path: Path,
    *,
    workspace: Path | None,
) -> Path:
    if workspace is None:
        return host_path

    assert workspace is not None
    try:
        relative = host_path.relative_to(workspace)
    except ValueError as exc:
        raise ValueError(
            f"Workspace credential path must stay inside {workspace}: {host_path}"
        ) from exc
    return SANDBOX_WORKSPACE / relative


KEYS: dict[str, bytes] = {
    "UP": b"\x1b[A",
    "DOWN": b"\x1b[B",
    "RIGHT": b"\x1b[C",
    "LEFT": b"\x1b[D",
    "HOME": b"\x1b[H",
    "END": b"\x1b[F",
    "PAGEUP": b"\x1b[5~",
    "PAGEDOWN": b"\x1b[6~",
    "INSERT": b"\x1b[2~",
    "DELETE": b"\x1b[3~",
    "TAB": b"\t",
    "ENTER": b"\r",
    "ESC": b"\x1b",
    "ESCAPE": b"\x1b",
    "BACKSPACE": b"\x7f",
    "F1": b"\x1bOP",
    "F2": b"\x1bOQ",
    "F3": b"\x1bOR",
    "F4": b"\x1bOS",
    "F5": b"\x1b[15~",
    "F6": b"\x1b[17~",
    "F7": b"\x1b[18~",
    "F8": b"\x1b[19~",
    "F9": b"\x1b[20~",
    "F10": b"\x1b[21~",
    "F11": b"\x1b[23~",
    "F12": b"\x1b[24~",
}


def build_sandbox_launch(
    settings: TerminalSettings,
    *,
    cwd: Path,
    shell: Path,
    rcfile: Path | None,
    bwrap_path: str | None = None,
    masked_file_binds: list[MaskedFileBind] | None = None,
    credential_deny_read: list[tuple[Path, Path]] | None = None,
) -> SandboxLaunch:
    sandbox = settings.sandbox
    shell_path = str(shell)

    if shell.name == "bash" and rcfile is not None:
        direct_shell_argv = [shell_path, "--rcfile", str(rcfile), "-i"]
    else:
        direct_shell_argv = [shell_path, "-i"]

    if not sandbox.active:
        return SandboxLaunch(
            executable=shell_path,
            argv=direct_shell_argv,
            cwd=str(cwd),
        )

    bwrap = bwrap_path or shutil.which("bwrap")
    if not bwrap:
        raise RuntimeError(
            "PTY sandbox features require bubblewrap (bwrap). Install the "
            "'bubblewrap' package or disable read_only, workspace, masking, "
            "deny_read, and deny_write."
        )

    args = [
        bwrap,
        "--die-with-parent",
        "--unshare-pid",
    ]

    workspace: Path | None = None
    policy_scope = "host"

    if sandbox.workspace:
        workspace = Path(sandbox.workspace_path or settings.cwd).expanduser().resolve()
        if not workspace.is_dir():
            raise FileNotFoundError(f"Sandbox workspace does not exist: {workspace}")

        _append_workspace_system_mounts(args)
        workspace_bind = "--ro-bind" if sandbox.read_only else "--bind"
        args.extend([workspace_bind, str(workspace), str(SANDBOX_WORKSPACE)])
        sandbox_cwd = str(SANDBOX_WORKSPACE)
        sandbox_home: str | None = str(SANDBOX_HOME)
        shell_in_sandbox = _map_workspace_executable(shell, workspace)
        policy_scope = "workspace"
    else:
        root_bind = "--ro-bind" if sandbox.read_only else "--bind"
        args.extend([root_bind, "/", "/"])
        sandbox_cwd = str(cwd)
        sandbox_home = None
        shell_in_sandbox = shell_path

    # Use sandbox-owned proc/dev/tmp whenever bubblewrap is active.
    # Network is intentionally still shared with the host.
    args.extend([
        "--proc", "/proc",
        "--dev", "/dev",
        "--tmpfs", "/tmp",
    ])
    if sandbox_home is not None:
        args.extend(["--dir", sandbox_home])

    if shell.name == "bash" and rcfile is not None:
        args.extend(["--ro-bind", str(rcfile), str(SANDBOX_RCFILE)])
        shell_argv = [shell_in_sandbox, "--rcfile", str(SANDBOX_RCFILE), "-i"]
    else:
        shell_argv = [shell_in_sandbox, "-i"]

    deny_write = _resolve_policy_paths(
        sandbox.deny_write,
        mode=policy_scope,
        cwd=cwd,
        workspace=workspace,
    )
    for host_path, sandbox_path in deny_write:
        args.extend(["--ro-bind", str(host_path), str(sandbox_path)])

    for masked in masked_file_binds or []:
        args.extend(["--ro-bind", str(masked.fake_path), str(masked.target_path)])

    deny_read = _resolve_policy_paths(
        sandbox.deny_read,
        mode=policy_scope,
        cwd=cwd,
        workspace=workspace,
    )
    deny_read.extend(credential_deny_read or [])
    if deny_read:
        mask_file, mask_dir = _sandbox_mask_paths()
        deny_read.sort(key=lambda pair: len(pair[1].parts), reverse=True)
        for host_path, sandbox_path in deny_read:
            source = mask_dir if host_path.is_dir() else mask_file
            args.extend(["--ro-bind", str(source), str(sandbox_path)])

    args.extend(["--chdir", sandbox_cwd, "--", *shell_argv])
    return SandboxLaunch(
        executable=bwrap,
        argv=args,
        cwd=sandbox_cwd,
        home=sandbox_home,
    )

def _append_workspace_system_mounts(args: list[str]) -> None:
    usr = Path("/usr")
    if not usr.is_dir():
        raise RuntimeError("Workspace sandbox requires /usr to be available.")
    args.extend(["--ro-bind", "/usr", "/usr"])

    for path_text in ("/bin", "/sbin", "/lib", "/lib64"):
        path = Path(path_text)
        if path.is_symlink():
            args.extend(["--symlink", os.readlink(path), path_text])
        elif path.exists():
            args.extend(["--ro-bind", path_text, path_text])

    if Path("/etc").exists():
        args.extend(["--ro-bind", "/etc", "/etc"])


def _map_workspace_executable(shell: Path, workspace: Path) -> str:
    resolved = shell.resolve()
    try:
        relative = resolved.relative_to(workspace)
    except ValueError:
        return str(shell)
    return str(SANDBOX_WORKSPACE / relative)


def _resolve_policy_paths(
    values: list[str],
    *,
    mode: str,
    cwd: Path,
    workspace: Path | None,
) -> list[tuple[Path, Path]]:
    resolved: list[tuple[Path, Path]] = []
    base = workspace if mode == "workspace" and workspace is not None else cwd

    for raw in values:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = base / candidate

        try:
            host_path = candidate.resolve(strict=True)
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"Sandbox policy path does not exist: {candidate}"
            ) from exc

        if mode == "workspace":
            assert workspace is not None
            try:
                relative = host_path.relative_to(workspace)
            except ValueError as exc:
                raise ValueError(
                    f"Workspace sandbox policy path must stay inside {workspace}: {raw}"
                ) from exc
            if relative == Path(".") and raw in values:
                # deny_write may intentionally cover the whole workspace, but
                # deny_read on the root would make the configured cwd unusable.
                pass
            sandbox_path = SANDBOX_WORKSPACE / relative
        else:
            sandbox_path = host_path

        resolved.append((host_path, sandbox_path))

    return resolved


def _sandbox_mask_paths() -> tuple[Path, Path]:
    cache_dir = Path.home() / ".cache" / "notion_is_terminal" / "sandbox"
    cache_dir.mkdir(parents=True, exist_ok=True)
    mask_file = cache_dir / "deny-file"
    mask_dir = cache_dir / "deny-dir"
    if not mask_file.exists():
        mask_file.write_bytes(b"")
    mask_dir.mkdir(exist_ok=True)
    return mask_file, mask_dir


class PTYSession:
    """Persistent PTY-backed shell plus a text-mode terminal emulator."""

    def __init__(self, settings: TerminalSettings) -> None:
        self.settings = settings
        self.pid: int | None = None
        self.master_fd: int | None = None
        self.screen = pyte.Screen(settings.columns, settings.rows)
        self.stream = pyte.Stream(self.screen)
        self.decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self.current_cwd = str(Path(settings.cwd).expanduser().resolve())
        self._osc_buffer = ""
        self._rcfile: Path | None = None
        self._credential_store: CredentialMaskStore | None = None
        self._credential_registry = CredentialSentinelRegistry()
        self._closed = False

    def start(self) -> None:
        if self.pid is not None:
            raise RuntimeError("PTY session is already running")

        cwd = Path(self.settings.cwd).expanduser().resolve()
        if not cwd.is_dir():
            raise FileNotFoundError(f"Working directory does not exist: {cwd}")

        shell = Path(self.settings.shell).expanduser()
        if not shell.exists():
            raise FileNotFoundError(f"Shell does not exist: {shell}")

        if shell.name == "bash":
            self._rcfile = self._write_bash_rcfile()

        masked_file_binds: list[MaskedFileBind] = []
        credential_deny_read: list[tuple[Path, Path]] = []
        if (
            self.settings.sandbox.masking
            and self.settings.sandbox.credential_files
        ):
            self._credential_store = CredentialMaskStore()
            try:
                masked_file_binds, credential_deny_read = prepare_credential_masks(
                    self.settings,
                    cwd=cwd,
                    registry=self._credential_registry,
                    store=self._credential_store,
                )
            except Exception:
                self._credential_store.close()
                self._credential_store = None
                raise

        try:
            launch = build_sandbox_launch(
                self.settings,
                cwd=cwd,
                shell=shell,
                rcfile=self._rcfile,
                masked_file_binds=masked_file_binds,
                credential_deny_read=credential_deny_read,
            )
        except Exception:
            if self._credential_store is not None:
                self._credential_store.close()
                self._credential_store = None
            raise
        self.current_cwd = launch.cwd

        pid, master_fd = pty.fork()
        if pid == 0:
            if not self.settings.sandbox.active:
                os.chdir(cwd)

            env = os.environ.copy()
            env["TERM"] = "xterm-256color"
            env.setdefault("COLORTERM", "truecolor")
            env["COLUMNS"] = str(self.settings.columns)
            env["LINES"] = str(self.settings.rows)
            if launch.home is not None:
                env["HOME"] = launch.home

            os.execvpe(launch.executable, launch.argv, env)
            raise SystemExit(127)

        self.pid = pid
        self.master_fd = master_fd
        flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        self.resize(self.settings.columns, self.settings.rows)

    def fileno(self) -> int:
        if self.master_fd is None:
            raise RuntimeError("PTY session is not running")
        return self.master_fd

    def read_ready(self) -> bool:
        if self.master_fd is None:
            return False
        changed = False
        while True:
            try:
                chunk = os.read(self.master_fd, 65536)
            except BlockingIOError:
                break
            except OSError as exc:
                if exc.errno == errno.EIO:
                    break
                raise
            if not chunk:
                break
            changed = True
            text = self.decoder.decode(chunk)
            if text:
                self._capture_cwd(text)
                self.stream.feed(text)
        return changed

    def send_text(self, text: str) -> None:
        self.send_bytes(text.encode("utf-8"))

    def send_line(self, text: str) -> None:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        self.send_text(normalized.replace("\n", "\r") + "\r")

    def send_bytes(self, data: bytes) -> None:
        if not self.is_alive() or self.master_fd is None:
            raise RuntimeError("Shell session is not running")
        view = memoryview(data)
        while view:
            written = os.write(self.master_fd, view)
            view = view[written:]

    def send_control(self, key: str) -> None:
        normalized = key.strip().upper()
        if normalized in {"\\", "BACKSLASH"}:
            self.send_bytes(b"\x1c")
            return
        if len(normalized) != 1 or not ("@" <= normalized <= "_"):
            raise ValueError(f"Unsupported Ctrl key: {key}")
        self.send_bytes(bytes([ord(normalized) & 0x1F]))

    def send_key(self, key: str) -> None:
        normalized = key.strip().upper().replace("_", "")
        aliases = {
            "PGUP": "PAGEUP",
            "PGDN": "PAGEDOWN",
            "DEL": "DELETE",
            "INS": "INSERT",
            "RETURN": "ENTER",
            "RET": "ENTER",
            "ENT": "ENTER",
            "BS": "BACKSPACE",
            "BKSP": "BACKSPACE",
        }
        normalized = aliases.get(normalized, normalized)
        data = KEYS.get(normalized)
        if data is None:
            raise ValueError(f"Unsupported key: {key}")
        self.send_bytes(data)

    def resize(self, columns: int, rows: int) -> None:
        if not (20 <= columns <= 400 and 5 <= rows <= 200):
            raise ValueError("Terminal size must be within 20..400 columns and 5..200 rows")
        self.settings.columns = columns
        self.settings.rows = rows
        self.screen.resize(lines=rows, columns=columns)
        if self.master_fd is not None:
            winsize = struct.pack("HHHH", rows, columns, 0, 0)
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
            if self.pid and self.is_alive():
                try:
                    os.kill(self.pid, signal.SIGWINCH)
                except ProcessLookupError:
                    pass

    def render(self) -> str:
        lines = list(self.screen.display)
        if self.settings.show_cursor and self.screen.cursor and 0 <= self.screen.cursor.y < len(lines):
            y = self.screen.cursor.y
            x = min(max(self.screen.cursor.x, 0), max(self.settings.columns - 1, 0))
            line = lines[y]
            if len(line) < self.settings.columns:
                line = line.ljust(self.settings.columns)
            lines[y] = line[:x] + "▌" + line[x + 1 :]
        return "\n".join(line.rstrip() for line in lines).rstrip("\n")

    def prompt(self) -> str:
        return f"{self.settings.user}@{self.settings.host}:{self.current_cwd}$ "

    def is_alive(self) -> bool:
        if self.pid is None:
            return False
        try:
            waited, _status = os.waitpid(self.pid, os.WNOHANG)
        except ChildProcessError:
            return False
        return waited == 0

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except OSError:
                pass
            self.master_fd = None
        if self.pid is not None and self.is_alive():
            try:
                os.kill(self.pid, signal.SIGHUP)
            except ProcessLookupError:
                pass
        self.pid = None
        if self._credential_store is not None:
            self._credential_store.close()
            self._credential_store = None

    def _capture_cwd(self, text: str) -> None:
        self._osc_buffer = (self._osc_buffer + text)[-8192:]
        matches = list(OSC7_RE.finditer(self._osc_buffer))
        if matches:
            path = unquote(matches[-1].group(1))
            if path:
                self.current_cwd = path
            self._osc_buffer = self._osc_buffer[-1024:]

    def _write_bash_rcfile(self) -> Path:
        cache_dir = Path.home() / ".cache" / "notion_is_terminal"
        cache_dir.mkdir(parents=True, exist_ok=True)
        rcfile = cache_dir / "bashrc"

        lines: list[str] = []
        if self.settings.source_bashrc:
            lines.extend([
                'if [ -f "$HOME/.bashrc" ]; then',
                '  . "$HOME/.bashrc"',
                "fi",
            ])

        prompt = f"{self.settings.user}@{self.settings.host}:\\w\\$ "
        lines.extend([
            "__nit_emit_cwd() {",
            "  printf '\\033]7;file://localhost%s\\007' \"$PWD\"",
            "}",
            'if [ -n "${PROMPT_COMMAND-}" ]; then',
            '  PROMPT_COMMAND="__nit_emit_cwd;${PROMPT_COMMAND}"',
            "else",
            '  PROMPT_COMMAND="__nit_emit_cwd"',
            "fi",
            f"PS1={shlex.quote(prompt)}",
            "export PS1 PROMPT_COMMAND",
            "",
        ])
        rcfile.write_text("\n".join(lines), encoding="utf-8")
        try:
            rcfile.chmod(0o600)
        except OSError:
            pass
        return rcfile
