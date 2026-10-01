# notion_is_terminal

[한국어](./README.ko.md)

**Give GPT on the web a real terminal surface without exposing a shell server to the internet.**

`notion_is_terminal` turns a Notion page into a bridge between a web-based GPT session and a persistent Linux PTY.

When GPT can read and edit the generated Notion page through a Notion connector, it can:

- inspect the current terminal screen;
- send shell commands;
- press terminal keys such as Enter, arrows, Backspace, Esc, and function keys;
- send Ctrl combinations such as Ctrl-C, Ctrl-O, and Ctrl-X;
- interact with TUI programs such as `nano`, `vim`, `less`, `top`, Codex, and other terminal applications;
- keep shell state such as `cd`, environment variables, REPL sessions, and foreground programs alive between requests.

In short:

> **GPT Web ↔ Notion ↔ local PTY ↔ WSL / Linux**

Notion is the shared control surface. The local daemon owns the real terminal.

## Demo

https://github.com/user-attachments/assets/a23b9865-3baf-4068-ab32-4756d1ac5a20

> [!CAUTION]
> This is **not a sandbox**. Anything written to the Input block is executed with the permissions of the Linux user running the daemon. Use a non-root account and do not send passwords, API keys, or other secrets through Notion.

---

## Why this exists

Web-based GPT clients are convenient for reasoning, coding, and remote assistance, but they normally do not have direct access to your local WSL terminal.

This project uses Notion as a lightweight bridge:

1. GPT reads the **Terminal** block.
2. GPT writes commands or key events to the **Input** block.
3. `notion-terminal` polls that block and forwards the input to a real PTY.
4. The PTY output is rendered back into the **Terminal** block.
5. GPT reads the updated screen and continues.

No public SSH endpoint, custom web server, database, or message queue is required.

---

## Architecture

```text
┌──────────────────────┐
│  GPT / ChatGPT Web   │
│   Notion connector   │
└──────────┬───────────┘
           │ read / edit
           ▼
┌──────────────────────┐
│     Notion page      │
│                      │
│  Terminal code block │◄─────────────┐
│  Input code block    │──────────────┐│
└──────────────────────┘              ││
                                      ││ Notion API
                                      ││
                              ┌───────▼▼────────┐
                              │ notion-terminal │
                              │     daemon      │
                              └───────┬─────────┘
                                      │
                                      ▼
                              ┌───────────────┐
                              │ persistent PTY│
                              │ Bash / TUI    │
                              └───────┬───────┘
                                      │
                                      ▼
                                WSL / Linux
```

The Terminal block is a **screen snapshot**, not an append-only stdout log. ANSI cursor movement, clearing, scrolling, and redraw sequences are interpreted locally with `pyte` before the screen is written back to Notion.

That is why redraw-oriented applications can work at a text-UI level.

---

## What it can do

- Persistent interactive Bash session
- Real PTY semantics: `isatty(stdin/stdout/stderr) == true`
- ANSI / VT screen emulation
- Shell state persistence
- Foreground-process stdin
- Ctrl-C / Ctrl-D / Ctrl-Z / Ctrl-L / Ctrl-\\
- Arrow keys, Home/End, Page Up/Down
- Enter, Backspace, Delete, Insert, Tab, Esc
- F1-F12
- Raw byte / escape-sequence input
- Runtime terminal resize
- Detached background daemon
- Single-instance locking
- Runtime block self-healing
- `doctor` diagnostics

Tested interaction patterns include Bash, Python REPL, nano, vim-style key sequences, Codex TUI, interactive prompts, and long-running processes interrupted with Ctrl-C.

---

## Requirements

- WSL2 Ubuntu or another Linux environment
- Python 3.11+
- Bash
- A Notion internal integration
- A Notion page shared with that integration
- Optional: a GPT / ChatGPT web session with access to the same Notion workspace

---

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

---

## Setup

Create a Notion internal integration and give it access to a parent page.

Then run:

```bash
notion-terminal init
```

The wizard creates a child page with two runtime blocks:

```text
Terminal
[ live terminal screen ]

Input
> 
```

Configuration is stored at:

```text
~/.config/notion_is_terminal/config.toml
```

The config is chmod `0600` where supported.

---

## Run as a background daemon

For normal use:

```bash
notion-terminal daemon start
```

Lifecycle commands:

```bash
notion-terminal daemon status
notion-terminal daemon restart
notion-terminal daemon stop
notion-terminal daemon logs
notion-terminal daemon logs -f
```

Runtime files:

```text
~/.cache/notion_is_terminal/daemon.pid
~/.cache/notion_is_terminal/daemon.log
~/.cache/notion_is_terminal/instance.lock
```

The daemon survives closing the WSL terminal window. It does not currently auto-start after WSL itself shuts down or Windows reboots.

Foreground mode is available for debugging:

```bash
notion-terminal run
```

---

## Using it from GPT Web

Once the generated Notion page is visible to GPT through a Notion connector, the page becomes a terminal tool surface.

A typical flow:

```text
You:
Check my Notion Terminal and run git status.

GPT:
1. reads the Terminal block
2. writes "git status" to Input
3. waits for the daemon to execute it
4. reads the refreshed Terminal block
5. explains the result
```

Because the underlying PTY is persistent, GPT can continue with:

```bash
cd ~/project
git status
python3
codex
nano notes.txt
```

without creating a new shell for every request.

### TUI programs

Some TUI applications distinguish pasted text from an actual Enter key press.

For example, text may appear inside Codex's input field without being submitted. Send Enter separately:

```text
> :k ENTER
```

The same control protocol can drive editors and other interactive applications.

---

## Input protocol

Normal text is submitted only after a blank line. In the Notion UI, type the command and press **Enter twice**.

```text
> pwd

```

After submission, the Input block is reset to:

```text
> 
```

### Control commands

| Action | Long form | Short form | Example |
| --- | --- | --- | --- |
| Special key | `:key NAME` | `:k NAME` | `:k ENTER` |
| Ctrl key | `:ctrl KEY` | `:c KEY` | `:c O` |
| Raw input | `:send TEXT` | `:s TEXT` | `:s \\e:wq\\r` |
| Resize | `:resize COLSxROWS` | `:rs COLSxROWS` | `:rs 140x50` |

Key aliases:

```text
ENTER      RETURN RET ENT
BACKSPACE  BS BKSP
ESC        ESCAPE
DELETE     DEL
INSERT     INS
PAGEUP     PGUP
PAGEDOWN   PGDN
```

Other supported keys:

```text
UP DOWN LEFT RIGHT
HOME END
TAB
F1 ... F12
```

Immediate control tokens:

```text
^C   interrupt
^D   EOF
^Z   suspend
^L   clear / redraw
^\   quit signal
```

---

## TUI examples

### Codex / Claude Code

Submit text already visible in the TUI:

```text
> :k ENTER
```

Edit the current input:

```text
> :k BS
> :k LEFT
> :k RIGHT
```

### nano

```text
> :c O        # save
> :k ENTER    # confirm filename
> :c X        # exit
> :c W        # search
```

### vim

```text
> :s \e:wq\r   # save and quit
> :s \e:q!\r   # quit without saving
```

---

## Runtime block self-healing

The Notion page ID is the durable anchor. Terminal and Input block IDs are replaceable runtime references.

Every `health_check_interval` seconds, each runtime block is validated independently.

If one block is deleted, trashed, invalid, or moved away from its expected position:

1. the healthy block is kept unchanged;
2. only the damaged block is recreated;
3. it is inserted back at its original section;
4. only the changed block ID is persisted to `config.toml`.

If both runtime blocks are removed, both are recreated.

If the stable Terminal/Input anchor sections are also removed, recovery falls back to creating a fresh runtime section at the end of the page.

If the page itself is deleted or inaccessible, the daemon stops instead of silently creating another page.

---

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

---

## Diagnostics

```bash
notion-terminal doctor
```

Checks config, Linux / WSL environment, shell path, working directory, Notion page access, and both runtime blocks.

---

## Security model

This project deliberately does **not** implement a command allowlist or sandbox.

The security boundary is the Linux account running the daemon. A GPT session that can write to the Notion Input block can execute commands with that user's permissions.

Recommended precautions:

- run the daemon as a dedicated non-root user;
- never send sudo passwords through Notion;
- never send API keys, SSH private keys, or other secrets through the Input block;
- restrict access to the generated Notion page;
- use a separate local authentication path for privileged work.

---

## Limitations

Notion is not a low-latency terminal transport. Terminal semantics are preserved, but every interaction still passes through the Notion API.

Currently not supported as a native Notion terminal experience:

- mouse reporting
- sixel / kitty graphics
- pixel graphics
- terminal color styling
- clipboard escape sequences
- sub-second keystroke streaming
- multiple simultaneous PTY sessions
- automatic startup after WSL / Windows restart

---

## Development

```bash
pip install -e . pytest
pytest
python -m compileall -q notion_is_terminal tests
```

GitHub Actions tests Python 3.11, 3.12, and 3.13.

---

## License

MIT
