# Terminal4GPTWeb installation and first-time setup

[한국어](./INSTALL.ko.md) · [Main README](./README.md)

This guide walks through a clean installation from an empty machine/workspace to the first GPT Web command.

The final topology is:

```text
ChatGPT Web
    │
    │ ChatGPT Notion connection
    ▼
Notion
└─ Parent Page created by you
   └─ Terminal4GPTWeb              ← created by t4g init
      ├─ Terminal / Input / Browser
      ├─ Terminal4GPTWeb Help
      └─ Browser Vision Payload
              ▲
              │ Notion API
              │
        local t4g daemon
              │
              ├─ Linux PTY
              └─ Playwright Chromium
```

## 1. Prerequisites

Required:

- Linux or WSL2 Ubuntu
- Python 3.11+
- Git and Bash
- A Notion account
- A Notion API token
- A Notion page that will be used as the parent for generated pages
- A ChatGPT Notion connection when GPT Web control is desired

Optional:

- PTY sandbox: Node.js 22.12+, [Anthropic Sandbox Runtime (`srt`)](https://github.com/anthropic-experimental/sandbox-runtime), `bubblewrap`, `socat`, `ripgrep`, `script` (util-linux)
- ChatGPT GitHub connection for repository-aware development workflows
- ChatGPT scheduled tasks/automations for recurring operations checks

Check versions:

```bash
python3 --version
git --version
bash --version
```

## 2. Install system packages

Ubuntu / WSL2:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv
```

Only if you plan to enable the PTY sandbox (`sandbox.enabled = true`):

```bash
sudo apt install -y bubblewrap socat ripgrep util-linux
# Node.js 22.12+ is required for srt
npm install -g @anthropic-ai/sandbox-runtime
srt --version
```

With `sandbox.enabled = false` (the default) none of these are required. If the sandbox is enabled and `srt` is missing, the daemon refuses to start and shows the install command.

## 3. Create a Notion parent page

Create an empty Notion page, for example:

```text
Terminal4GPTWeb Root
```

The current `t4g init` flow asks for one parent page. The generated control page and child documentation/vision pages are created below it.

You do not need to copy the URL in advance. The wizard supports both:

```text
1. Search pages
2. Enter URL / page ID
```

## 4. Obtain a Notion API token

The local daemon calls the Notion API directly. This token is **separate from the Notion connection used by ChatGPT Web**.

### Option A — Personal Access Token

For a personal trusted CLI setup:

1. Open the Notion Developer portal.
2. Open **Personal access tokens**.
3. Select **New token**.
4. Choose a name and the Notion API capability.
5. Select the workspace if prompted.
6. Create and securely copy the token.

Official guide:
https://developers.notion.com/guides/get-started/quick-start

### Option B — Internal Connection

For a dedicated bot identity:

1. Open the Notion Developer portal.
2. Go to **Build → Internal connections**.
3. Create a new connection.
4. Select its workspace.
5. Copy the Installation access token from Configuration.
6. Enable the required content capabilities:
   - Read content
   - Update content
   - Insert content
7. Grant the connection access to the parent page.

Access can be granted through either the Developer portal Content access page or the Notion page's **Connections → Add connection** UI.

Official guide:
https://developers.notion.com/guides/get-started/internal-connections

Never place the token in source code, a Git repository, or the Notion Input block.

## 5. Install Terminal4GPTWeb

```bash
git clone https://github.com/hyeongmin90/terminal4gptweb.git
cd terminal4gptweb

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -e .
```

Verify:

```bash
t4g --version
t4g --help
```

If the repository directory is renamed or moved after an editable install:

```bash
cd ~/terminal4gptweb
pip install -e .
hash -r
```

## 6. Install Playwright Chromium

```bash
playwright install chromium
```

If Linux dependencies are missing:

```bash
playwright install --with-deps chromium
```

The terminal bridge still works without using the browser feature.

## 7. Run the setup wizard

```bash
t4g init
```

The wizard asks for:

- Notion API token
- parent page via Search Page or URL/Page ID
- shell
- initial working directory
- whether to enable the srt PTY sandbox, and if so:
  - Read-only filesystem toggle
  - Workspace restriction toggle and optional workspace path
  - extra writable paths, deny-read / deny-write paths
  - allowed network domains
- prompt label, terminal size and refresh timing
- generated Notion page title

Read-only and Workspace are independent switches. Enabling both makes the selected workspace visible but read-only. If srt or its system tools are missing the wizard warns but still saves the config.

Credential masking rules are configured after initialization in `config.toml`.

## 8. Configuration

Default path:

```text
~/.config/notion_is_terminal/config.toml
```

Sandbox settings:

```toml
[sandbox]
enabled = true            # false: run the shell directly, srt not needed
srt_path = ""             # empty: srt on PATH
read_only = false
workspace = true
workspace_path = "/home/user/project"
allow_write = ["~/.cache"]
deny_read = []
deny_write = [".git"]
allowed_domains = ["github.com", "*.githubusercontent.com", "pypi.org", "files.pythonhosted.org"]
denied_domains = []
tls_terminate = true
allow_plaintext_inject = false
```

Semantics:

- `enabled = false`: unrestricted PTY; every other key is ignored
- `read_only = false, workspace = false`: host readable and writable
- `read_only = true, workspace = false`: read-only host; only `allow_write` paths are writable
- `read_only = false, workspace = true`: `/home`, `/root`, `/mnt`, `/media` hidden; only the workspace is visible and writable
- `read_only = true, workspace = true`: read-only workspace isolation
- network: only `allowed_domains` are reachable; an empty list blocks all network access

Credential masking (files and environment variables):

```toml
[[sandbox.credentials.files]]
path = ".env"
mode = "mask"
extract = '(?m)^(?:OPENAI_API_KEY|DATABASE_URL|JWT_SECRET)=(\S+)$'
on_extract_no_match = "deny"
mask_duplicates = false
inject_hosts = ["api.openai.com"]

[[sandbox.credentials.env]]
name = "GITHUB_TOKEN"
mode = "mask"
inject_hosts = ["api.github.com"]
```

Inside the shell, masked values read as `fake_value_<uuid>`. srt replaces them with the real value only in HTTP(S) requests to the credential's `inject_hosts` (default: all allowed domains). The regex must have exactly one capture group; only capture group 1 is replaced. Masking requires `tls_terminate = true` (or the explicit `allow_plaintext_inject = true`).

A server started inside the sandboxed terminal is not reachable from the Playwright browser, which runs outside the sandbox's network namespace.

Restart after config changes:

```bash
t4g daemon restart
```

## 9. Validate the installation

```bash
t4g doctor
```

Then:

```bash
t4g daemon start
t4g daemon status
```

Use:

```bash
t4g daemon logs
t4g daemon logs -f
```

for troubleshooting.

## 10. Connect Notion in ChatGPT Web

This is separate from the local Notion API token.

Depending on the ChatGPT UI available to your account:

1. Open Apps or Plugins.
2. Find Notion.
3. Connect/install it.
4. Sign in to the Notion account containing the generated page.
5. Approve the workspace/content access required to reach Terminal4GPTWeb.

OpenAI guide:
https://help.openai.com/en/articles/12532955-notion-app-and-setup-in-chatgpt

## 11. First manual smoke test

On the generated Notion control page, put this in Input and submit with a blank line (Enter twice in the UI):

```text
> pwd

```

The Terminal block should update and Input should return to `>`.

Then try:

```text
> whoami

```

Browser smoke test:

```text
> :b goto https://example.com
```

Browser Status and Browser Screenshot should update.

## 12. First ChatGPT request

Example:

```text
Find my Terminal4GPTWeb page in Notion, inspect the current Terminal,
run pwd, wait for Input to reset, and report the result.
```

With GitHub connected:

```text
Review the latest repository changes in GitHub, run the relevant tests
locally through Terminal4GPTWeb, and verify the affected web UI with Playwright.
```

## 13. Recovery

For deleted Terminal/Input runtime blocks, the daemon attempts self-healing.

If the entire generated control page was deleted:

```bash
t4g reinit
t4g daemon restart
```

The saved parent page is reused. Older configs without a saved parent will show the Search Page / URL selection again.

## 14. Security checklist

- run the daemon as a non-root user
- do not type passwords or raw credentials into Notion Input
- prefer `sandbox.enabled = true` with workspace isolation for development
- keep `allowed_domains` to what the work needs
- use credential mask/deny rules for known credential files and environment variables
- protect important paths with `deny_write` when appropriate
- restrict access to the generated Notion control page
- remember that masking protects only configured files/variables, and only HTTP(S) traffic gets the real value

See [README.md](./README.md) for the full feature and command reference.
