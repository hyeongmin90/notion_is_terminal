# notion_is_terminal

Use a Notion page as a remote terminal UI for a local WSL/Ubuntu shell.

`notion_is_terminal` keeps a **persistent PTY session** open on the Linux machine, renders the terminal screen into one Notion code block, and uses a second Notion code block as the input/control surface.

> The goal is not merely “run a command from Notion.” The goal is to make Notion behave as much like a text terminal/TUI as the Notion API allows.

## Features

- Persistent Bash/PTTY session: `cd`, exported variables, REPL state, shell jobs, etc. stay alive.
- ANSI/VT screen emulation via `pyte`.
- Two-code-block Notion UI:
  - **Terminal**: current terminal screen.
  - **Input**: commands and control input.
- Live screen refresh through the Notion API.
- Immediate `^C` interrupt support.
- `Ctrl-D`, `Ctrl-Z`, `Ctrl-L`, `Ctrl-\\`.
- Arrow keys, Home/End, Page Up/Down, Insert/Delete, Tab, Escape, Backspace, F1-F12.
- Raw keystroke input for `vim`, `less`, REPLs, prompts, etc.
- Runtime terminal resize.
- Setup wizard that creates the correctly shaped Notion page, writes the controls guide, and saves block IDs.
- Self-healing runtime blocks: deleted/trashed Terminal or Input blocks are recreated automatically and new IDs are persisted.
- Built-in detached daemon lifecycle: `start`, `stop`, `restart`, `status`, `logs`.
- Single-instance lock prevents foreground/background sessions from racing.
- `doctor` diagnostics.
- No DB, MQ, server, or sandbox in the MVP.

## Architecture

```text
Notion page
  ├─ code block #1: Terminal screen
  └─ code block #2: Input / control
              ↕
          Notion API
              ↕
      notion-terminal daemon
              ↕
      persistent Linux PTY
              ↕
        interactive Bash
```

The Terminal block is a **screen snapshot**, not an append-only stdout log. ANSI cursor movement, clearing, scrolling and redraw commands are interpreted locally before plain text is written back to Notion. This is what makes redraw-oriented programs such as `top`, `less`, and `vim` possible at a text-UI level.

## Requirements

- WSL2 Ubuntu or another Linux environment
- Python 3.11+
- Bash
- A Notion internal integration with page read/update/insert-content access
- A parent Notion page shared with that integration

## Install

```bash
git clone https://github.com/hyeongmin90/notion_is_terminal.git
cd notion_is_terminal

python -m venv .venv
source .venv/bin/activate
pip install -e .
```

This installs:

```bash
notion-terminal
nit
```

## First-run wizard

Create a Notion internal integration, copy its token, and share one parent page with that integration.

Then run:

```bash
notion-terminal init
```

The wizard asks for:

- Notion integration token
- parent Notion page URL or ID
- shell path
- initial working directory
- prompt user / host
- terminal columns / rows
- polling interval
- screen refresh interval

It creates a child page containing built-in usage/help blocks plus **exactly two runtime code blocks** (Terminal + Input) and writes:

```text
~/.config/notion_is_terminal/config.toml
```

The config is chmod `0600` on Unix when possible.

## Run

### Background daemon

Recommended for normal use:

```bash
notion-terminal daemon start
```

The process is detached from the current shell, so closing the WSL terminal window does not stop it.

Check status:

```bash
notion-terminal daemon status
```

Restart after updating config or code:

```bash
notion-terminal daemon restart
```

Stop:

```bash
notion-terminal daemon stop
```

Read the last 100 log lines:

```bash
notion-terminal daemon logs
```

Follow logs:

```bash
notion-terminal daemon logs -f
```

Runtime files:

```text
~/.cache/notion_is_terminal/daemon.pid
~/.cache/notion_is_terminal/daemon.log
~/.cache/notion_is_terminal/instance.lock
```

Only one terminal session can run at a time. A foreground `run` and background daemon cannot both own the same local terminal session.

The detached daemon survives closing the shell, but it does **not** automatically restart after WSL itself shuts down or Windows reboots. Use a systemd service later if boot-time auto-start is required.

### Foreground mode

Useful for debugging:

```bash
notion-terminal run
```

Open the generated Notion page.

The Terminal block keeps the real shell prompt, while the Input block stays compact:

```text
> 
```

### Sending a normal command

Notion exposes text while a user is still editing it. If the daemon executed on every change, typing `kubectl` could accidentally execute `kub`.

For that reason, normal input is submitted only when it ends with a **blank line**.

Type:

```text
> pwd

```

In practice: type the command and press **Enter twice**.

The daemon sends the line to the PTY and resets the Input block to the fixed `> ` prompt.

## Stop a running command

`^C` is special and is recognized immediately; no blank-line submit is needed.

```text
> ^C
```

The daemon writes byte `0x03` into the PTY. The Linux terminal driver therefore delivers `SIGINT` to the foreground process group just as a real local Ctrl-C would.

Other immediate control tokens:

```text
^D
^Z
^L
^\
```

## Special keys

Submit special keys through the Input block:

```text
> :key UP

```

Supported names:

```text
UP DOWN LEFT RIGHT
HOME END PAGEUP PAGEDOWN
INSERT DELETE
TAB ENTER ESC BACKSPACE
F1 ... F12
```

Aliases include `PGUP`, `PGDN`, `DEL`, `INS`, and `RETURN`.

## Raw input

For programs that need input without an automatic Enter:

```text
> :send ihello

```

Supported escapes:

```text
\e      Escape
\x1b    hexadecimal byte
\n      newline
\r      carriage return
\t      tab
\\      literal backslash
```

Example while inside Vim:

```text
:send \e:wq\r

```

This sends Escape, `:wq`, and Enter to the PTY.

## Resize

```text
> :resize 140x50

```

This updates the PTY window size, terminal emulator size, and sends the normal terminal resize signal.

## TUI applications

Because the child shell sees an actual pseudo-terminal and ANSI control sequences are interpreted locally, programs that normally require a TTY can work at a text-UI level:

```bash
top
htop
less
vim
nano
python
node
psql
ssh
```

Notion itself is not a low-latency terminal client. Input and screen frames travel through the Notion API, so interactive programs have visible network/API latency. The project preserves terminal semantics; it does not provide local-terminal responsiveness.

Not rendered in the MVP:

- mouse reporting
- sixel/kitty images
- pixel graphics
- clipboard escape sequences
- terminal color styling inside Notion
- sub-second keystroke streaming

## Configuration

Default:

```text
~/.config/notion_is_terminal/config.toml
```

Example:

```toml
[notion]
token = "secret_xxx"
api_version = "2026-03-11"
page_id = "..."
terminal_block_id = "..."
input_block_id = "..."
page_url = "https://..."

[terminal]
shell = "/bin/bash"
cwd = "/home/user"
user = "user"
host = "ubuntu"
input_prompt = "> "
columns = 120
rows = 40
poll_interval = 1.2
refresh_interval = 1.5
health_check_interval = 10.0
show_cursor = true
source_bashrc = true
```

`NOTION_TOKEN` overrides the token stored in the config.

## Bash startup and current directory

For Bash, the daemon creates:

```text
~/.cache/notion_is_terminal/bashrc
```

By default it sources the user's normal `~/.bashrc`, installs the configured prompt, and adds an OSC 7 prompt hook.

That hook reports the real `$PWD` back to the daemon so the **Terminal screen** shows the correct Bash prompt after `cd`.

The Input block intentionally does not mirror the Bash prompt. It remains:

```text
> 
```

The daemon does not emulate `cd` itself; the persistent Bash session owns the real shell state.

## Runtime block self-healing

The daemon treats the Notion page ID as the durable anchor and the two runtime block IDs as replaceable references.

Every `health_check_interval` seconds it verifies both configured runtime blocks. If either Terminal or Input was deleted, moved to trash, or is no longer a usable code block:

1. the surviving old runtime block is archived when possible;
2. a fresh Terminal/Input pair is appended to the same Notion page;
3. the current terminal screen and prompt are restored;
4. the new block IDs replace the old IDs in `config.toml`.

A missing/inaccessible **page itself** is not silently recreated. In that case the daemon stops and asks you to run `notion-terminal init` again.

## Diagnostics

```bash
notion-terminal doctor
```

Checks:

- config
- Linux/WSL environment
- shell path
- working directory
- Notion page access
- Terminal code block
- Input code block

## Security

**The MVP intentionally has no sandbox or command allowlist.**

Anything entered through the Notion Input block executes with the permissions of the Linux user running the daemon. Treat write access to the Notion page and possession of the integration token as security-sensitive.

Run it as a non-root user.

## Why PTY instead of stdout pipes?

With `subprocess.PIPE`, programs can detect that stdin/stdout are not terminals and often disable interactivity, line buffering, progress rendering, cursor movement, and full-screen TUI modes.

A PTY gives the child process terminal semantics:

```text
isatty(stdin)  == true
isatty(stdout) == true
isatty(stderr) == true
```

That is the basis for using Notion as a TUI surface rather than only as a remote command runner.

## Development

```bash
pip install -e . pytest
pytest
python -m compileall -q notion_is_terminal tests
```

GitHub Actions tests Python 3.11, 3.12, and 3.13.

## MVP scope

Included:

- one Notion page
- exactly two code blocks
- one persistent PTY session
- Bash on Linux/WSL
- TUI screen rendering
- terminal control input

Intentionally deferred:

- sandboxing
- DB / MQ
- multiple sessions
- multi-user locking
- webhook-based input
- automatic restart after WSL/Windows restart
- service/systemd installer

## License

MIT
