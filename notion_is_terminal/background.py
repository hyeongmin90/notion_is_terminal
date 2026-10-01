from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from .config import DEFAULT_CONFIG_PATH, load_config


CACHE_DIR = Path.home() / ".cache" / "notion_is_terminal"
PID_FILE = CACHE_DIR / "daemon.pid"
LOG_FILE = CACHE_DIR / "daemon.log"


def start_daemon(config_path: Path | str = DEFAULT_CONFIG_PATH) -> int:
    config_path = Path(config_path).expanduser().resolve()
    load_config(config_path)

    existing = read_pid()
    if existing and process_is_our_daemon(existing):
        print(f"notion_is_terminal daemon is already running (pid {existing}).")
        return 0
    if existing:
        _remove_pid_file()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    log = LOG_FILE.open("ab", buffering=0)
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["NIT_DAEMON_MODE"] = "1"

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "notion_is_terminal",
            "run",
            "--config",
            str(config_path),
        ],
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        close_fds=True,
        env=env,
    )
    log.close()

    PID_FILE.write_text(str(process.pid), encoding="utf-8")
    try:
        PID_FILE.chmod(0o600)
    except OSError:
        pass

    time.sleep(0.15)
    if process.poll() is not None:
        _remove_pid_file()
        print(f"daemon failed to start; check {LOG_FILE}", file=sys.stderr)
        return process.returncode or 1

    print(f"started notion_is_terminal daemon (pid {process.pid})")
    print(f"log: {LOG_FILE}")
    return 0


def stop_daemon(*, timeout: float = 5.0) -> int:
    pid = read_pid()
    if not pid:
        print("notion_is_terminal daemon is not running.")
        return 0

    if not process_is_our_daemon(pid):
        _remove_pid_file()
        print("removed stale daemon pid file.")
        return 0

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        _remove_pid_file()
        print("notion_is_terminal daemon is not running.")
        return 0

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not process_exists(pid):
            _remove_pid_file()
            print("stopped notion_is_terminal daemon.")
            return 0
        time.sleep(0.1)

    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass

    for _ in range(20):
        if not process_exists(pid):
            break
        time.sleep(0.05)

    _remove_pid_file()
    print("stopped notion_is_terminal daemon (forced).")
    return 0


def restart_daemon(config_path: Path | str = DEFAULT_CONFIG_PATH) -> int:
    code = stop_daemon()
    if code != 0:
        return code
    return start_daemon(config_path)


def daemon_status(config_path: Path | str = DEFAULT_CONFIG_PATH) -> int:
    pid = read_pid()
    if not pid or not process_is_our_daemon(pid):
        if pid:
            _remove_pid_file()
        print("notion_is_terminal daemon: stopped")
        return 1

    print(f"notion_is_terminal daemon: running (pid {pid})")
    try:
        config = load_config(config_path)
        if config.notion.page_url:
            print(f"Notion: {config.notion.page_url}")
    except Exception:
        pass
    print(f"log: {LOG_FILE}")
    return 0


def show_logs(*, lines: int = 100, follow: bool = False) -> int:
    if not LOG_FILE.exists():
        print(f"no daemon log yet: {LOG_FILE}")
        return 0

    if not follow:
        for line in _tail_lines(LOG_FILE, lines):
            print(line, end="")
        return 0

    with LOG_FILE.open("r", encoding="utf-8", errors="replace") as stream:
        stream.seek(0, os.SEEK_END)
        try:
            while True:
                line = stream.readline()
                if line:
                    print(line, end="", flush=True)
                else:
                    time.sleep(0.25)
        except KeyboardInterrupt:
            return 0


def read_pid() -> int | None:
    try:
        value = PID_FILE.read_text(encoding="utf-8").strip()
        return int(value)
    except (FileNotFoundError, ValueError, OSError):
        return None


def process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def process_is_our_daemon(pid: int) -> bool:
    if not process_exists(pid):
        return False

    cmdline_path = Path(f"/proc/{pid}/cmdline")
    try:
        cmdline = cmdline_path.read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace")
    except OSError:
        return True

    return "notion_is_terminal" in cmdline and " run " in f" {cmdline} "


def _remove_pid_file() -> None:
    try:
        PID_FILE.unlink()
    except FileNotFoundError:
        pass


def _tail_lines(path: Path, count: int) -> list[str]:
    if count <= 0:
        return []
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        data = stream.readlines()
    return data[-count:]
