# Terminal4GPTWeb

[한국어](./README.ko.md) · [Detailed installation](./INSTALL.md) · [한국어 설치 가이드](./INSTALL.ko.md)

**Give GPT on the web a real terminal surface without exposing a shell server to the internet.**

`Terminal4GPTWeb` turns Notion into a bridge between a web-based GPT session, a persistent Linux PTY, and a Playwright-controlled browser.

When GPT can read and edit the generated Notion page through a Notion connector, it can:

- inspect the current terminal screen;
- send shell commands;
- press terminal keys such as Enter, arrows, Backspace, Esc, and function keys;
- send Ctrl combinations such as Ctrl-C, Ctrl-O, and Ctrl-X;
- interact with TUI programs such as `nano`, `vim`, `less`, `top`, Codex, and other terminal applications;
- keep shell state such as `cd`, environment variables, REPL sessions, and foreground programs alive between requests;
- open web pages with Playwright, inspect screenshots with GPT Vision, and control the browser with viewport-relative mouse coordinates;
- optionally run the shell inside [Anthropic Sandbox Runtime (srt)](https://github.com/anthropic-experimental/sandbox-runtime), with filesystem and network limits and credential masking.

In short:

> **GPT Web ↔ Notion ↔ PTY / Playwright ↔ WSL / Linux / Web**

Notion is the shared control surface. The local daemon owns the real terminal.

> [!CAUTION]
> PTY sandboxing is **optional**. With `sandbox.enabled = false` (the default), anything written to Input runs with the permissions of the Linux user running the daemon. With `sandbox.enabled = true` the shell runs inside [Anthropic Sandbox Runtime (srt)](https://github.com/anthropic-experimental/sandbox-runtime), which adds filesystem, network and credential-masking rules, but it does not replace normal secret-management practices.

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
                              │   t4g daemon    │──► Playwright Chromium
                              └───────┬─────────┘
                                      │
                                      ▼
                              ┌─────────────────┐
                              │ persistent PTY  │
                              └───────┬─────────┘
                                      │ sandbox.enabled = true
                                      ▼
                         ┌───────────────────────────┐
                         │ srt (optional)            │
                         │  bubblewrap fs rules      │
                         │  network allowlist proxy  │
                         │  credential masking       │
                         └────────────┬──────────────┘
                                      │
                                      ▼
                              Bash / TUI on WSL / Linux
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
- Optional srt PTY sandbox: read-only / workspace filesystem isolation, write allow/deny lists, outbound domain allowlist
- Claude Code-style credential masking for files and environment variables: the shell sees `fake_value_<uuid>`, allowed HTTPS requests carry the real value

Tested interaction patterns include Bash, Python REPL, nano, vim-style key sequences, Codex TUI, interactive prompts, and long-running processes interrupted with Ctrl-C.

---

## Requirements

- WSL2 Ubuntu or another Linux environment
- Python 3.11+
- Bash
- A Notion API token: Personal Access Token or Internal Connection token
- A Notion page to use as the parent for generated Terminal4GPTWeb pages
- **GPT / ChatGPT Web with the Notion connection enabled** for remote GPT control
- Optional but recommended for development: **GitHub connection** in ChatGPT
- Optional for recurring operations: ChatGPT scheduled tasks / automations, where available
- Only for sandbox mode: Node.js 22.12+, [`@anthropic-ai/sandbox-runtime`](https://github.com/anthropic-experimental/sandbox-runtime) (`srt`), `bubblewrap`, `socat`, `ripgrep`, and `script` (util-linux)

> [!IMPORTANT]
> Terminal4GPTWeb does not expose a standalone GPT API. GPT Web reaches the local runtime by reading and editing the generated Notion pages, so the Notion connection is required for the GPT-Web workflow.

---

## First-time installation and setup

For a completely new installation, see **[INSTALL.md](./INSTALL.md)**. It covers the Notion Developer portal, token creation, parent-page access, Linux packages, Playwright, the wizard, sandbox configuration, ChatGPT's Notion connection, and the first smoke test.

The short version is below.

### 1. Prepare a Notion parent page

Create an empty Notion page, for example:

```text
Terminal4GPTWeb Root
```

The current `t4g init` flow creates the generated control page under a parent page. You can select it by search in the wizard, so copying its URL in advance is optional.

### 2. Obtain a Notion API token

The **local daemon** needs a Notion API token. This is separate from the Notion app/plugin connection used by ChatGPT Web.

You can use either:

- a **Personal Access Token (PAT)** for a trusted personal CLI workflow; or
- an **Internal Connection** token for a dedicated bot identity.

For an Internal Connection, grant it access to the parent page and enable content permissions needed to read, insert, and update page content.

Official Notion guides:

- https://developers.notion.com/guides/get-started/quick-start
- https://developers.notion.com/guides/get-started/internal-connections

### 3. Install the local package

```bash
git clone https://github.com/hyeongmin90/terminal4gptweb.git
cd terminal4gptweb

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
playwright install chromium
```

Only if you plan to enable the PTY sandbox (Ubuntu/WSL2, Node.js 22.12+):

```bash
sudo apt install -y bubblewrap socat ripgrep util-linux
npm install -g @anthropic-ai/sandbox-runtime
srt --version
```

Without `sandbox.enabled = true` none of these are needed.

Verify:

```bash
t4g --version
t4g --help
```

If an editable install stops working after the repository directory is renamed or moved:

```bash
cd ~/terminal4gptweb
pip install -e .
hash -r
```

### 4. Run the setup wizard

```bash
t4g init
```

The wizard asks for the Notion API token and then offers:

```text
Choose parent Notion page

  1. Search pages
  2. Enter URL / page ID
```

It also asks for the shell, initial working directory, terminal size and whether to enable the srt PTY sandbox (plus its filesystem and network options).

The generated Notion structure is:

```text
Parent Page
└─ Terminal4GPTWeb
   ├─ Terminal / Input / Browser
   ├─ Terminal4GPTWeb Help
   └─ Browser Vision Payload
```

Local config is stored at:

```text
~/.config/notion_is_terminal/config.toml
```

### 5. Validate and start

```bash
t4g doctor
t4g daemon start
t4g daemon status
```

### 6. Connect Notion in ChatGPT Web

This is a **second, separate connection** from the local API token.

Connect Notion from ChatGPT Apps/Plugins, sign in to the account/workspace containing the generated page, and approve access to the relevant content.

OpenAI setup guide:

https://help.openai.com/en/articles/12532955-notion-app-and-setup-in-chatgpt

### 7. First smoke test

In the generated Notion Input block:

```text
> pwd

```

Submit with a trailing blank line (Enter twice in the Notion UI). Terminal should update and Input should reset to `>`.

Browser:

```text
> :b goto https://example.com
```

Browser Status and Browser Screenshot should update.

If the whole generated page is deleted later:

```bash
t4g reinit
t4g daemon restart
```

---

## Recommended ChatGPT Web setup

Terminal4GPTWeb is most useful when ChatGPT Web has the following connections.

### 1. Notion — required

Connect Notion to ChatGPT and make the generated Terminal4GPTWeb page accessible to that connection.

The Notion connection is the transport used by GPT Web:

```text
GPT Web
  ↓ read/write through Notion
Terminal4GPTWeb control page
  ↓ polled by local daemon
PTY / Playwright
```

Without the Notion connection, the local daemon still works, but GPT Web cannot use the generated page as its terminal/browser tool surface.

### 2. GitHub — recommended for development

Connect GitHub when you want GPT to work with repository context in addition to the local runtime.

A useful development loop is:

```text
GitHub
  ↓ issue / PR / history / code context
GPT Web
  ↓
Notion → Terminal4GPTWeb
  ↓
edit / build / unit test / integration test
  ↓
Playwright + Vision
  ↓
browser E2E verification
```

This lets GPT use GitHub for repository-level context while using the local terminal for commands that must run on your machine.

Example requests:

```text
Review the latest changes in this repository, run the relevant tests locally,
and verify the web UI with Playwright.

Check the linked issue, reproduce it locally, fix it, run the test suite,
then verify the affected screen through Browser Vision.
```

### 3. Scheduled tasks / automations — optional for OPS

If your ChatGPT client supports scheduled tasks or automations, Terminal4GPTWeb can also act as an operations surface.

A scheduled task can periodically ask GPT to:

- inspect `docker ps`, service/process state, disk and memory usage;
- call local health endpoints;
- inspect recent logs for errors;
- run a lightweight browser smoke test;
- report only when a check fails or needs attention.

Example OPS instruction:

```text
Every morning, inspect my Terminal4GPTWeb page.
Run the service health checklist, check recent error logs,
and verify the main web page with Playwright.
Notify me only if something needs attention.
```

Keep recurring checks read-only where possible. Do not put credentials, sudo passwords, private keys, or other secrets into the Notion Input block.

---

## How GPT / agents should operate

For reliable agent behavior, use a strict observe → act → observe loop:

1. Read **Terminal** or **Browser Status**.
2. Write exactly one command/action to **Input**.
3. Wait until Input resets to `>`.
4. Read the refreshed output before issuing the next action.
5. For browser coordinate actions, use only the latest `observation_id`.
6. When Vision is needed, fetch `vision_page_url`, decode `data_base64` as JPEG, and verify that its observation ID matches Browser Status.
7. Stop and surface the error when Browser Status is `failed`; do not continue with stale coordinates.
8. Input is submitted only when it ends with a blank line. When an agent writes Input through the Notion API or a connector, end the text with **one extra newline** (three in total): connectors may trim one, and without the blank line the command just sits in Input.
9. If Input shows `[SANDBOX UNAVAILABLE]`, the sandbox is enabled but srt or one of its tools is missing; report it rather than retrying commands.

This protocol is also documented in the generated **Terminal4GPTWeb Help** Notion child page.

---

## Example workflows

### Development + test

```text
GitHub context
→ inspect code / issue / PR
→ run local build and tests through Terminal
→ start the application
→ open it with Playwright
→ inspect with Vision
→ interact and verify the result
```

### Local troubleshooting

```text
read Terminal
→ inspect process/container state
→ inspect logs
→ run health request
→ apply a fix
→ restart service
→ verify again
```

### Browser E2E

```text
:b goto <url>
→ read latest Vision payload
→ choose coordinates
→ :b click <obs_id> <x> <y>
→ wait for new observation
→ verify the changed screen
```

### OPS / recurring checks

Use a fixed, minimal checklist such as:

```text
1. process/container status
2. health endpoint
3. recent ERROR logs
4. disk + memory
5. browser smoke test
```

For automated runs, prefer notifications only on actionable failures rather than sending a success message every time.

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

To intentionally recreate a deleted full control page, run:

```bash
t4g reinit
t4g daemon restart
```

`reinit` preserves the existing local terminal/browser settings and replaces the Notion page and runtime block IDs in the config.

---

## PTY sandbox (srt)

By default the shell runs with the full permissions of the user running the daemon. Setting `sandbox.enabled = true` runs it inside [Anthropic Sandbox Runtime (srt)](https://github.com/anthropic-experimental/sandbox-runtime), the sandbox runtime behind Claude Code's sandboxed Bash. t4g does not reimplement the sandbox: it translates `[sandbox]` into an srt settings file and launches the shell through srt.

```text
sandbox.enabled = false   →  bash                                  (srt not needed)
sandbox.enabled = true    →  srt -s ~/.cache/notion_is_terminal/srt-settings.json \
                               -- script -qfec "bash --rcfile … -i" /dev/null
```

srt applies three layers:

| Layer | What it does |
| --- | --- |
| Filesystem | bubblewrap mounts: writes denied except allowed paths; selected paths hidden |
| Network | the shell gets its own network namespace; all traffic goes through srt's proxy, which only lets `allowed_domains` through |
| Credentials | configured files and environment variables are replaced by `fake_value_<uuid>` inside the shell; the proxy swaps in the real value on requests to allowed hosts |

`script` gives the shell a controlling terminal inside srt's session, so job control and Ctrl-C keep working. Terminal resize (`:rs`) is relayed to it as well.

### Quick start

```bash
# 1. install (Node.js 22.12+)
sudo apt install -y bubblewrap socat ripgrep util-linux
npm install -g @anthropic-ai/sandbox-runtime

# 2. enable: answer "y" to "Enable sandbox" in `t4g init`,
#    or set `enabled = true` under [sandbox] in config.toml

# 3. check and restart
t4g doctor            # checks srt, bwrap, socat, rg, script and runs a smoke test through srt
t4g daemon restart
```

If the sandbox is enabled and a tool is missing, the daemon refuses to start, writes `[SANDBOX UNAVAILABLE]` with the install command into the Notion Input block, and logs the same message. With `enabled = false` none of these tools are needed. `srt_path` points at a specific `srt` binary; empty means `srt` on `PATH`.

### Filesystem

srt denies writes by default and allows reads by default.

| Setting | Effect |
| --- | --- |
| `read_only = false`, `workspace = false` | Whole host readable and writable (`allowWrite = ["/"]`), except srt's protected files. |
| `read_only = true`, `workspace = false` | Whole host readable, nothing writable except `allow_write` entries. |
| `read_only = false`, `workspace = true` | `/home`, `/root`, `/mnt` and `/media` are hidden; only `workspace_path` is visible and writable. The shell starts in `workspace_path`. |
| `read_only = true`, `workspace = true` | Same, but the workspace is read-only too. |
| `allow_read` | Paths kept readable inside hidden areas, e.g. `~/.nvm` or `~/.local/bin` for tools installed under the home directory in workspace mode. srt's own package is always kept readable. |
| `allow_write` | Extra writable paths, e.g. `~/.cache`, `~/.npm`, `~/.local`. |
| `deny_write` | Paths kept read-only inside writable areas (wins over `allow_write`). |
| `deny_read` | Paths hidden from the shell. |

- Relative paths resolve against `workspace_path` in workspace mode, otherwise against `cwd`.
- On Linux, `allow_write`/`deny_write` take literal paths (no globs), and create/modify/delete are not distinguished.
- srt always blocks writes to shell rc files, `.gitconfig`, `.git/hooks`, `.git/config`, `.vscode/`, `.idea/` and similar files, even inside writable paths.
- Temporary files go to srt's writable `TMPDIR` (`/tmp/claude`).
- Filesystem rules are fixed when the shell starts; run `t4g daemon restart` after changing them.

### Network

- Only `allowed_domains` are reachable. `*.example.com` wildcards are allowed; a bare `*` is rejected by srt.
- `denied_domains` wins over `allowed_domains`.
- Blocked requests fail with `Connection blocked by network allowlist` (HTTP) or `CONNECT tunnel failed, response 403` (HTTPS).
- An empty list means no network at all.

### Credential masking

```toml
[[sandbox.credentials.env]]
name = "GITHUB_TOKEN"
mode = "mask"
inject_hosts = ["api.github.com"]

[[sandbox.credentials.files]]
path = ".env"
mode = "mask"
extract = '(?m)^(?:OPENAI_API_KEY|JWT_SECRET)=(\S+)$'
on_extract_no_match = "deny"
inject_hosts = ["api.openai.com"]
```

What the shell sees, and what reaches the server:

```text
$ echo $GITHUB_TOKEN
fake_value_f38d04a3-6216-492f-96b4-d49ba120db07

$ curl -H "Authorization: Bearer $GITHUB_TOKEN" https://api.github.com/user
  → srt proxy replaces the sentinel → api.github.com receives the real token
```

- `mode = "mask"`: the value is replaced by a per-session `fake_value_<uuid>` sentinel. srt substitutes the real value only on requests to the credential's `inject_hosts` (default: every allowed domain), so one credential cannot be sent to another credential's host.
- `mode = "deny"`: the file is unreadable / the variable is unset.
- `extract`: only capture group 1 of the regex is masked (exactly one group required) and the rest stays intact, e.g. just the password inside `DATABASE_URL`. Without `extract` the whole file or value is replaced.
- `on_extract_no_match`: `warn` (leave readable, fail-open), `deny` (hide, fail-closed) or `error` (refuse to start).
- `tls_terminate = true` is required for masking so substitution also works inside HTTPS requests; srt sets CA trust variables (`SSL_CERT_FILE`, …) in the sandbox. `allow_plaintext_inject = true` is the explicit opt-out and only injects into plain-HTTP requests.
- Only HTTP(S) traffic through the proxy is rewritten. SSH, database wire protocols and other raw TCP connections receive the fake value.

### Sandbox limitations

> [!IMPORTANT]
> The sandboxed shell has its own network namespace. A dev server started **inside** the sandboxed terminal listens on the sandbox's loopback and is **not reachable from the Playwright browser** (`:b goto http://localhost:…`), which runs outside the sandbox. For browser E2E against a local server, start that server outside the sandbox or disable the sandbox for that workflow.

- Network allowlist changes and filesystem changes both need `t4g daemon restart`.
- Masking only protects configured files and variables; it is not a secret scanner.
- srt is experimental (`@anthropic-ai/sandbox-runtime` 0.0.x); pinning a version such as `npm install -g @anthropic-ai/sandbox-runtime@0.0.78` is recommended.

### Upgrading from the earlier bubblewrap sandbox

Earlier versions built the bubblewrap sandbox themselves and used `masking = true`. When such a config is loaded:

- configs without an `enabled` key that had any restriction on (`read_only`, `workspace`, `masking`, `deny_read`, `deny_write`) load as `enabled = true`, so they stay sandboxed (now through srt);
- `masking` is no longer a key; credential rules apply whenever the sandbox is enabled;
- a config with `mode = "mask"` credential rules must add `tls_terminate = true` (or `allow_plaintext_inject = true`), otherwise it fails to load with an explicit error;
- the network is now restricted too: add the domains your work needs to `allowed_domains`;
- workspace mode keeps real paths instead of remapping the workspace to `/workspace`.

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
parent_page_id = "..."
help_page_id = "..."
help_page_url = "https://..."
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

[sandbox]
enabled = true
srt_path = ""
read_only = false
workspace = true
workspace_path = "/home/user/project"
allow_read = ["~/.nvm"]
allow_write = ["~/.cache"]
deny_read = []
deny_write = [".git"]
allowed_domains = ["github.com", "*.githubusercontent.com", "pypi.org", "files.pythonhosted.org", "api.openai.com"]
denied_domains = []
tls_terminate = true
allow_plaintext_inject = false

[[sandbox.credentials.files]]
path = ".env"
mode = "mask"
extract = '(?m)^(?:OPENAI_API_KEY|JWT_SECRET)=(\S+)$'
on_extract_no_match = "deny"
mask_duplicates = false
inject_hosts = ["api.openai.com"]

[[sandbox.credentials.env]]
name = "GITHUB_TOKEN"
mode = "mask"
inject_hosts = ["api.github.com"]

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

The `[sandbox]` keys are explained in [PTY sandbox (srt)](#pty-sandbox-srt).

After config changes:

```bash
t4g daemon restart
```

---

## Diagnostics

```bash
t4g doctor
```

Checks config, Linux / WSL environment, shell path, working directory, Notion page access, and both runtime blocks. With `sandbox.enabled = true` it also lists the effective sandbox mode, network allowlist and credential rules, checks `srt`, `bwrap`, `socat`, `rg` and `script`, and runs `true` through srt with the configured policy.

---

## Security model

Terminal4GPTWeb supports an optional PTY sandbox based on [Anthropic Sandbox Runtime (srt)](https://github.com/anthropic-experimental/sandbox-runtime), the same runtime behind Claude Code's sandbox.

```text
enabled = false
  → unrestricted PTY as the daemon user (srt not required)

enabled = true, read_only = false, workspace = false
  → host readable and writable, network limited to allowed_domains

enabled = true, read_only = true, workspace = false
  → read-only host view

enabled = true, workspace = true
  → user data hidden except workspace_path (read/write, or read-only with read_only = true)
```

With the sandbox on:

- writes are allowed only where configured, and srt always protects shell rc files, git hooks/config and editor config;
- outbound network is limited to `allowed_domains` through srt's proxy;
- configured credential files and environment variables are replaced by `fake_value_<uuid>` sentinels, and the real value is only sent to the credential's allowed hosts.

Masking is not a universal secret scanner: only configured files and variables are protected.

Recommended precautions:

- run the daemon as a dedicated non-root user;
- prefer `enabled = true` with workspace isolation for coding workflows;
- keep `allowed_domains` to what the work needs;
- protect known credential files and environment variables with mask or deny rules;
- never send sudo passwords or raw credentials through Notion Input;
- restrict access to the generated Notion page;
- treat Docker sockets or other privileged IPC endpoints as sandbox escapes if you expose them manually.

---

## Verification

The regression suite currently covers:

- config parsing and legacy config migration;
- Search Page / URL parent-page wizard paths;
- persistent PTY behavior and terminal controls;
- sandbox on/off launch paths and the missing-`srt` error;
- translation of read-only / workspace / allow-write / deny rules, network allowlists and credential rules into srt settings;
- legacy sandbox config migration to `sandbox.enabled`;
- Notion runtime block handling and browser control helpers.

GitHub Actions runs the test suite on Python 3.11, 3.12 and 3.13.

The sandbox path has been exercised end to end through `PTYSession → pty.fork() → srt → script → bash`: environment-variable and file masking, sentinel→real substitution on outbound HTTP requests, the network allowlist, deny-write, workspace isolation, Ctrl-C and terminal resize. On WSL2 Ubuntu (srt 0.0.78 installed through nvm) it was also driven through the Notion control page: HTTPS substitution with `tls_terminate` (the shell saw `fake_value_…`, the server received the real value), blocked HTTPS to a non-allowed domain, workspace isolation and resize. Browser smoke testing has been verified through Notion with Playwright and the Vision payload observation ID.

Destructive recovery cases such as deleting the live production control page are covered by automated tests rather than repeatedly deleting the active user page during routine regression runs.

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
- reaching a server started inside the srt sandbox from the Playwright browser (see [Sandbox limitations](#sandbox-limitations))

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
