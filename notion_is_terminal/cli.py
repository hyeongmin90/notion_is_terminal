from __future__ import annotations

import argparse
import os
import platform
import shutil
import sys
from pathlib import Path

from . import __version__
from .background import (
    InstanceLock,
    daemon_status,
    restart_daemon,
    show_logs,
    start_daemon,
    stop_daemon,
)
from .config import DEFAULT_CONFIG_PATH, load_config
from .daemon import TerminalDaemon
from .notion import NotionClient, NotionError
from .wizard import run_init, run_reinit


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="t4g",
        description="Bridge GPT Web to local terminal and Playwright browser tools through Notion.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("init", "reinit", "run", "doctor"):
        command = sub.add_parser(name)
        command.add_argument(
            "--config",
            type=Path,
            default=DEFAULT_CONFIG_PATH,
            help=f"Config path (default: {DEFAULT_CONFIG_PATH})",
        )

    daemon = sub.add_parser("daemon", help="Manage the detached background daemon.")
    daemon.add_argument(
        "action",
        choices=("start", "stop", "restart", "status", "logs"),
        help="Daemon lifecycle action.",
    )
    daemon.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"Config path (default: {DEFAULT_CONFIG_PATH})",
    )
    daemon.add_argument(
        "-n",
        "--lines",
        type=int,
        default=100,
        help="Number of lines for 'daemon logs' (default: 100).",
    )
    daemon.add_argument(
        "-f",
        "--follow",
        action="store_true",
        help="Follow daemon logs until Ctrl-C.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            run_init(args.config)
            return 0

        if args.command == "reinit":
            run_reinit(args.config)
            return 0

        if args.command == "run":
            config = load_config(args.config)
            with InstanceLock():
                print(f"Terminal4GPTWeb {__version__}")
                if config.notion.page_url:
                    print(f"Notion: {config.notion.page_url}")
                print("Starting persistent PTY in foreground. Press Ctrl-C here to stop.")
                TerminalDaemon(config, config_path=args.config).run()
            return 0

        if args.command == "doctor":
            return doctor(args.config)

        if args.command == "daemon":
            if args.action == "start":
                return start_daemon(args.config)
            if args.action == "stop":
                return stop_daemon()
            if args.action == "restart":
                return restart_daemon(args.config)
            if args.action == "status":
                return daemon_status(args.config)
            if args.action == "logs":
                return show_logs(lines=args.lines, follow=args.follow)
    except KeyboardInterrupt:
        print("\nStopped.")
        return 130
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 2


def doctor(config_path: Path) -> int:
    checks: list[tuple[bool, str]] = []
    try:
        config = load_config(config_path)
        checks.append((True, f"Config loaded: {config_path.expanduser()}"))
    except Exception as exc:
        print(f"✗ Config: {exc}")
        return 1

    checks.append((sys.platform.startswith("linux"), f"Linux/WSL platform: {platform.platform()}"))
    checks.append((Path(config.terminal.shell).exists(), f"Shell exists: {config.terminal.shell}"))
    checks.append((Path(config.terminal.cwd).expanduser().is_dir(), f"Working directory exists: {config.terminal.cwd}"))
    checks.append((os.access(Path(config.terminal.cwd).expanduser(), os.R_OK | os.X_OK), "Working directory is accessible"))

    sandbox = config.terminal.sandbox
    checks.append((
        True,
        f"PTY sandbox: {sandbox.mode} (enabled={str(sandbox.enabled).lower()}, "
        f"workspace_enabled={str(sandbox.workspace_enabled).lower()})",
    ))
    checks.append((
        True,
        f"Credential masking: {'enabled' if sandbox.masking_enabled else 'disabled'} "
        f"({len(sandbox.credential_files)} configured file rule(s))",
    ))
    if sandbox.mode != "none":
        bwrap = shutil.which("bwrap")
        checks.append((bwrap is not None, f"bubblewrap is installed: {bwrap or 'not found'}"))
        if sandbox.mode == "workspace":
            workspace = Path(sandbox.workspace or config.terminal.cwd).expanduser()
            checks.append((workspace.is_dir(), f"Sandbox workspace exists: {workspace}"))
    try:
        import playwright  # noqa: F401
        checks.append((True, "Playwright Python package is installed"))
    except ImportError:
        checks.append((False, "Playwright package missing: pip install -e ."))

    try:
        with NotionClient(config.notion.token, api_version=config.notion.api_version) as notion:
            notion.get_page(config.notion.page_id)
            terminal = notion.get_block(config.notion.terminal_block_id)
            input_block = notion.get_block(config.notion.input_block_id)
            browser_status = (
                notion.get_block(config.notion.browser_status_block_id)
                if config.notion.browser_status_block_id
                else None
            )
        checks.append((terminal.get("type") == "code" and not terminal.get("archived", False), "Terminal block is active"))
        checks.append((input_block.get("type") == "code" and not input_block.get("archived", False), "Input block is active"))
        if browser_status is not None:
            checks.append((browser_status.get("type") == "code" and not browser_status.get("archived", False), "Browser Status block is active"))
        else:
            checks.append((True, "Browser Status will be created on next daemon start"))
        checks.append((True, "Notion page is readable"))
    except NotionError as exc:
        checks.append((False, f"Notion access: {exc}"))

    failed = False
    for ok, message in checks:
        print(("✓" if ok else "✗") + " " + message)
        failed |= not ok
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
