# Terminal4GPTWeb

[한국어](./README.ko.md)

**Give GPT on the web a real terminal surface without exposing a shell server to the internet.**

`Terminal4GPTWeb` turns Notion into a bridge between a web-based GPT session, a persistent Linux PTY, and a Playwright-controlled browser.

When GPT can read and edit the generated Notion page through a Notion connector, it can:

- inspect the current terminal screen;
- send shell commands;
- press terminal keys such as Enter, arrows, Backspace, Esc, and function keys;
- send Ctrl combinations such as Ctrl-C, Ctrl-O, and Ctrl-X;
- interact with TUI programs such as `nano`, `vim`, `less`, `top`, Codex, and other terminal applications;
- keep shell state such as `cd`, environment variables, REPL sessions, and foreground programs alive between requests;
- open web pages with Playwright, inspect screenshots with GPT Vision, and control the browser with viewport-relative mouse coordinates.

In short:

> **GPT Web ↔ Notion ↔ PTY / Playwright ↔ WSL / Linux / Web**

Notion is the shared control surface. The local daemon owns the real terminal.

> [!CAUTION]
> This is **not a sandbox**. Anything written to the Input block is executed with the permissions of the Linux user running the daemon. Use a non-root account and do not send passwords, API keys, or other secrets through Notion.

---

## Why this exists

Web-based GPT clients are convenient for reasoning, coding, and remote assistance, but they normally do not have direct access to your local WSL terminal.

This project uses Notion as a lightweight bridge:

1. GPT reads the **Terminal** block.
2. GPT writes commands or key events to the **Input** block.
3. `t4g` polls that block and forwards the input to a real PTY.
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
                              │ t4g │
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
- Persistent Playwright Chromium session
- Browser screenshots published to Notion
- Compact JPEG Vision payload on an isolated Notion child page
- Observation-ID guarded mouse move/click/drag/scroll
- Browser keyboard input and navigation
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
git clone https://github.com/hyeongmin90/terminal4gptweb.git
cd terminal4gptweb

python -m venv .venv
source .venv/bin/activate
pip install -e .
playwright install chromium
```

The second command installs the Chromium binary used by the browser controller.

This installs:

```bash
terminal4gptweb
t4g
```

Legacy compatibility aliases `notion-terminal` and `nit` are also kept for now.

---

## Setup

Create a Notion internal integration and give it access to a parent page.

Then run:

```bash
t4g init
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
t4g daemon start
```

Lifecycle commands:

```bash
t4g daemon status
t4g daemon restart
t4g daemon stop
t4g daemon logs
t4g daemon logs -f
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
t4g run
```

---

## Using it from GPT Web

Once the generated Notion page is visible to GPT through a Notion connector, the page becomes a terminal tool surface.

A typical flow:

```text
You:
Check my Terminal4GPTWeb page and run git status.

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

## Browser + Vision

The daemon can also keep a persistent Playwright Chromium session. Every browser action produces a new observation:

```text
Browser Status
  observation_id
  url / title
  viewport / scroll
  cursor
  vision_page_url

Browser Screenshot
  latest full-resolution viewport image

Browser Vision Payload
  compressed JPEG payload on a separate child page
```

The child page keeps the machine-readable Vision payload out of the main terminal page. GPT can fetch it only when visual reasoning is required.

Start a browser session:

```text
> :b goto https://example.com
```

Useful commands:

| Action | Command |
| --- | --- |
| Navigate | `:b goto <url>` |
| Capture a fresh observation | `:b shot` |
| Move mouse | `:b move <observation_id> <x> <y>` |
| Click | `:b click <observation_id> <x> <y>` |
| Drag | `:b drag <observation_id> <x1> <y1> <x2> <y2>` |
| Scroll | `:b scroll <dx> <dy>` |
| Type text | `:b type <text>` |
| Press key | `:b key <key>` |
| Back | `:b back` |
| Reload | `:b reload` |

Mouse coordinates use **viewport-relative CSS pixels**. The default viewport is `1280x720`, and screenshots are captured in the same CSS-pixel coordinate system.

Coordinate actions require the latest `observation_id`:

```text
> :b click obs_20261001T173408Z_0001 640 418
```

If GPT tries to click using an older screenshot, the daemon rejects it with `STALE_OBSERVATION` instead of applying stale coordinates to a changed page.

After each successful action, the daemon automatically replaces the previous screenshot, updates the Vision payload, and issues a new observation ID.

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
browser_status_block_id = "..."
browser_image_block_id = "..."
browser_vision_page_id = "..."
browser_vision_block_id = "..."
browser_vision_page_url = "https://..."

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

[browser]
width = 1280
height = 720
headless = true
timeout_ms = 15000
settle_ms = 350
show_cursor_overlay = true
vision_enabled = true
vision_quality = 35
vision_max_base64_chars = 160000
```

`NOTION_TOKEN` overrides the token stored in the config.

---

## Diagnostics

```bash
t4g doctor
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

- terminal mouse reporting (Playwright browser mouse control is supported)
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
