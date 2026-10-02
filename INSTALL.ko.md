# Terminal4GPTWeb 설치 및 최초 설정

[English](./INSTALL.md) · [메인 README](./README.ko.md)

이 문서는 Terminal4GPTWeb을 처음 설치하는 사용자를 위한 전체 절차입니다.

완료 후 구조는 다음과 같습니다.

```text
ChatGPT Web
    │
    │ ChatGPT의 Notion 연결
    ▼
Notion
└─ 사용자가 미리 만든 Parent Page
   └─ Terminal4GPTWeb              ← t4g init이 생성
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

## 1. 준비물

필수:

- Linux 또는 WSL2 Ubuntu
- Python 3.11 이상
- Git
- Bash
- Notion 계정
- Notion API token
- Terminal4GPTWeb이 생성될 위치로 사용할 Notion page
- GPT 웹에서 사용할 경우 ChatGPT의 Notion 연결

선택:

- `bubblewrap` — PTY sandbox를 사용할 경우 필요
- ChatGPT GitHub 연결 — 코드/이슈/PR 분석과 로컬 테스트를 함께 사용할 경우 권장
- ChatGPT 일정/자동화 — OPS 정기 점검에 활용 가능

버전 확인:

```bash
python3 --version
git --version
bash --version
```

Python이 3.11 미만이면 먼저 3.11 이상의 Python을 설치하세요.

## 2. Linux 패키지 설치

Ubuntu / WSL2 기준:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv
```

sandbox를 사용할 예정이라면:

```bash
sudo apt install -y bubblewrap
bwrap --version
```

`read_only = false, workspace = false, masking = false`로 사용할 경우 bubblewrap은 필요하지 않습니다.

## 3. Notion Parent Page 만들기

Notion에서 빈 페이지를 하나 만듭니다.

예:

```text
Terminal4GPTWeb Root
```

현재 Terminal4GPTWeb의 `t4g init`은 생성할 페이지의 **parent page**를 하나 선택합니다.

이 parent page 아래에 자동으로:

```text
Terminal4GPTWeb
├─ Terminal4GPTWeb Help
└─ Browser Vision Payload
```

가 생성됩니다.

Parent Page URL을 반드시 복사해둘 필요는 없습니다. Wizard에서:

```text
1. Search pages
2. Enter URL / page ID
```

중 하나를 사용할 수 있습니다.

## 4. Notion API Token 준비

로컬 `t4g` daemon은 Notion API를 직접 호출합니다. 따라서 **ChatGPT의 Notion 연결과 별도로 Notion API token이 필요합니다.**

두 방식 중 하나를 사용할 수 있습니다.

### 방법 A — Personal Access Token

개인 환경에서는 가장 단순합니다.

1. Notion Developer portal을 엽니다.
2. **Personal access tokens**로 이동합니다.
3. **New token**을 선택합니다.
4. 이름을 지정하고 Notion API capability를 선택합니다.
5. 필요한 경우 workspace를 선택합니다.
6. token을 생성하고 즉시 안전한 곳에 복사합니다.

Notion 공식 문서:
https://developers.notion.com/guides/get-started/quick-start

PAT는 token을 만든 사용자의 Notion page 권한으로 동작합니다.

### 방법 B — Internal Connection

팀용/전용 bot 권한을 분리하고 싶다면 internal connection을 사용할 수 있습니다.

1. Notion Developer portal을 엽니다.
2. **Build → Internal connections**로 이동합니다.
3. **Create a new connection**을 선택합니다.
4. workspace와 이름을 지정합니다.
5. Configuration에서 Installation access token을 복사합니다.
6. Terminal4GPTWeb에 필요한 content capability를 허용합니다.
   - Read content
   - Update content
   - Insert content
7. 만든 Parent Page를 connection에 공유합니다.

페이지 권한 부여 방법은 둘 중 하나입니다.

- Developer portal의 **Content access → Edit access**에서 Parent Page 선택
- Notion Parent Page의 `••• → Connections → Add connection`에서 connection 추가

Parent Page에 권한을 주면 그 아래 생성되는 child page에도 권한이 상속됩니다.

Notion 공식 문서:
https://developers.notion.com/guides/get-started/internal-connections

> Token은 source code, README, Notion Input, Git repository에 넣지 마세요.

## 5. Terminal4GPTWeb 설치

```bash
git clone https://github.com/hyeongmin90/terminal4gptweb.git
cd terminal4gptweb

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -e .
```

설치 확인:

```bash
t4g --version
t4g --help
```

`t4g: command not found`가 나오면 venv가 활성화되어 있는지 확인합니다.

```bash
source ~/terminal4gptweb/.venv/bin/activate
```

프로젝트 폴더를 이동/이름 변경한 뒤 editable install이 깨졌다면:

```bash
cd ~/terminal4gptweb
pip install -e .
hash -r
```

## 6. Playwright Chromium 설치

Browser/Vision 기능을 사용하려면:

```bash
playwright install chromium
```

Linux system dependency가 부족하다는 오류가 나오면:

```bash
playwright install --with-deps chromium
```

Browser 기능을 쓰지 않더라도 Terminal 기능 자체는 사용할 수 있습니다.

## 7. 최초 초기화

```bash
t4g init
```

Wizard 순서는 대략 다음과 같습니다.

### Notion API token

```text
Notion API token (PAT or internal connection token):
```

여기에 4단계에서 만든 token을 입력합니다.

입력은 화면에 표시되지 않습니다.

### Parent Page 선택

```text
Choose parent Notion page

  1. Search pages
  2. Enter URL / page ID

Select [1]:
```

#### Search pages

```text
Search page title (blank = recent pages):
```

검색 결과에서 번호를 고릅니다.

```text
1. Terminal4GPTWeb Root
2. Developer Tools

r. Search again
u. Enter URL / page ID
```

#### Enter URL / page ID

Notion에서 Parent Page URL을 복사해 입력할 수도 있습니다.

```text
https://www.notion.so/...
```

URL 전체 또는 page ID 모두 지원합니다.

### Shell

보통 기본값을 그대로 사용합니다.

```text
Shell [/bin/bash]:
```

### Initial working directory

PTY가 시작할 기본 디렉터리입니다.

예:

```text
/home/user/project
```

### PTY security

Wizard는 preset 대신 기능을 각각 묻습니다.

```text
Read-only filesystem [y/N]:
Restrict filesystem to one workspace [y/N]:
Workspace path [...] :        # workspace=true일 때만
Enable credential file masking [y/N]:
```

조합:

- `read_only=false, workspace=false`: 일반 PTY
- `read_only=true, workspace=false`: host 전체 read-only
- `read_only=false, workspace=true`: 지정 workspace만 RW
- `read_only=true, workspace=true`: 지정 workspace만 보이고 workspace 자체도 read-only
- `masking=true`: credential file 규칙 적용. read_only/workspace 없이 단독 사용도 가능

추가 `deny_read` / `deny_write` 경로도 입력할 수 있습니다.

Credential masking의 파일별 규칙은 초기화 후 config에서 명시적으로 설정합니다.

### 나머지 설정

```text
Prompt user
Prompt host
Terminal columns
Terminal rows
Input poll interval
Screen refresh interval
Notion page title
```

대부분 기본값으로 시작해도 됩니다.

## 8. 생성되는 파일과 Notion 페이지

로컬 설정:

```text
~/.config/notion_is_terminal/config.toml
```

runtime:

```text
~/.cache/notion_is_terminal/
├─ daemon.pid
├─ daemon.log
├─ instance.lock
└─ ...
```

Notion:

```text
Parent Page
└─ Terminal4GPTWeb
   ├─ Terminal
   ├─ Input
   ├─ Quick Commands
   ├─ Browser Status
   ├─ Browser Screenshot
   ├─ Terminal4GPTWeb Help
   └─ Browser Vision Payload
```

## 9. Sandbox / Workspace / Masking 설정

모든 보안 기능은 config에서 독립적으로 끄고 켤 수 있습니다.

예:

```toml
[sandbox]
read_only = false
workspace = true
workspace_path = "/home/user/project"
masking = true

deny_read = []
deny_write = [".git"]
```

### 모든 filesystem 제한 OFF

```toml
[sandbox]
read_only = false
workspace = false
masking = false
deny_read = []
deny_write = []
```

이 상태에서는 bubblewrap을 사용하지 않고 기존 PTY처럼 실행됩니다.

### Read-only

```toml
[sandbox]
read_only = true
workspace = false
masking = false
```

효과:

- host filesystem read 가능
- host filesystem write 차단
- sandbox `/tmp`만 writable

### Workspace 격리

```toml
[sandbox]
read_only = false
workspace = true
workspace_path = "/home/user/project"
masking = false
```

효과:

- project는 sandbox 내부에서 `/workspace`로 보임
- workspace는 RW
- 실행에 필요한 system path는 RO
- 다른 home/project는 노출하지 않음
- sandbox 전용 HOME과 `/tmp` 사용

### Workspace + Read-only

```toml
[sandbox]
read_only = true
workspace = true
workspace_path = "/home/user/project"
masking = false
```

이 경우 workspace만 노출되며 `/workspace` 자체도 read-only입니다.

### Credential masking OFF

규칙은 보존하면서 기능만 끌 수 있습니다.

```toml
masking = false
```

### Credential masking ON

```toml
masking = true

[[sandbox.credentials.files]]
path = ".env"
mode = "mask"
extract = '(?m)^(?:OPENAI_API_KEY|DATABASE_URL|JWT_SECRET)=(\S+)$'
on_extract_no_match = "deny"
mask_duplicates = false
```

실제:

```dotenv
OPENAI_API_KEY=sk-real
DATABASE_URL=postgres://real
PORT=8080
```

sandbox 내부:

```dotenv
OPENAI_API_KEY=fake_value_<uuid>
DATABASE_URL=fake_value_<uuid>
PORT=8080
```

`extract`의 **capture group 1**만 masking됩니다.

`extract`를 생략하면 파일 전체가 하나의 sentinel로 바뀝니다.

`on_extract_no_match`:

- `warn`: 경고 후 실제 파일을 그대로 노출 — fail-open
- `deny`: masking 대신 read deny — fail-closed
- `error`: PTY 시작 자체를 실패시킴

보수적인 credential 설정에는 `deny` 또는 `error`를 권장합니다.

> 현재는 Claude-style **file masking 단계만** 구현되어 있습니다. Sentinel을 허용된 외부 host로 보낼 때 실제 secret으로 다시 바꾸는 egress proxy/injectHosts 기능은 아직 없습니다. 따라서 masking된 credential로 실제 외부 인증을 수행해야 하는 프로그램은 현재 실패할 수 있습니다.

설정을 수정했다면:

```bash
t4g daemon restart
```

## 10. 진단

```bash
t4g doctor
```

확인 항목:

- config parsing
- Linux / WSL
- shell
- working directory
- bubblewrap 설치 여부
- workspace 존재 여부
- Notion page
- Terminal/Input blocks
- Playwright Python package

문제가 있다면:

```bash
t4g daemon logs
t4g daemon logs -f
```

도 확인합니다.

## 11. Daemon 실행

```bash
t4g daemon start
t4g daemon status
```

Foreground 디버깅:

```bash
t4g run
```

정지/재시작:

```bash
t4g daemon stop
t4g daemon restart
```

## 12. ChatGPT Web에서 Notion 연결

이 단계는 **로컬 Notion API token 설정과 별개**입니다.

ChatGPT에서 계정에 표시되는 Apps 또는 Plugins 설정을 열고 Notion을 연결합니다.

현재 OpenAI 도움말 기준 일반 흐름:

1. ChatGPT의 Apps/Plugins 설정을 엽니다.
2. Notion을 찾습니다.
3. Connect 또는 Install/Connect를 선택합니다.
4. 사용할 Notion 계정에 로그인합니다.
5. Terminal4GPTWeb 페이지가 있는 workspace/content에 대한 연결을 승인합니다.

OpenAI 도움말:
https://help.openai.com/en/articles/12532955-notion-app-and-setup-in-chatgpt

ChatGPT가 Terminal4GPTWeb 페이지를 찾지 못하면:

- 다른 Notion 계정을 연결하지 않았는지
- 다른 workspace를 연결하지 않았는지
- 해당 계정이 Parent/Terminal4GPTWeb 페이지를 볼 수 있는지
- 연결 승인 범위에 페이지가 포함되는지

확인합니다.

## 13. 첫 테스트

먼저 Notion의 Terminal4GPTWeb 페이지를 직접 열고 Input에:

```text
> pwd

```

처럼 입력합니다. 명령 뒤에 빈 줄이 있어야 제출됩니다. Notion UI에서는 Enter를 두 번 누르면 됩니다.

정상이라면 Terminal이 갱신되고 Input은 다시:

```text
>
```

로 초기화됩니다.

다음:

```text
> whoami

```

를 테스트합니다.

Browser:

```text
> :b goto https://example.com
```

Browser Status와 Browser Screenshot이 갱신되면 브라우저도 정상입니다.

## 14. ChatGPT에서 첫 요청

예:

```text
Notion의 Terminal4GPTWeb 페이지를 찾아서 현재 Terminal을 확인하고
pwd를 실행한 뒤 결과를 알려줘.
```

개발에 GitHub도 연결했다면:

```text
GitHub에서 이 저장소의 최근 변경사항을 확인하고,
Terminal4GPTWeb으로 로컬 테스트를 실행해줘.
필요하면 Playwright로 웹 화면도 검증해줘.
```

## 15. 페이지가 삭제된 경우

Terminal/Input block만 삭제된 경우 daemon이 자동 복구를 시도합니다.

메인 Terminal4GPTWeb page 전체를 삭제했다면:

```bash
t4g reinit
t4g daemon restart
```

저장된 `parent_page_id`가 있으면 같은 parent 아래에 새 control page를 만듭니다.

오래된 config라 parent 정보가 없으면 Search Page / URL 선택 UI가 다시 표시됩니다.

## 16. 보안 체크리스트

- daemon은 root로 실행하지 않기
- Notion Input에 password/token/private key 직접 입력하지 않기
- 가능하면 workspace sandbox 사용
- credential 파일은 masking 또는 deny 정책 적용
- `.git`, 중요한 설정 디렉터리는 필요하면 `deny_write`
- Notion control page 접근 권한 제한
- masking은 **설정된 파일/패턴만** 보호하며 universal secret scanner가 아님
- Docker socket을 sandbox에 노출하는 기능은 현재 제공하지 않음
- 현재 network isolation / credential egress proxy는 구현되지 않음

## 다음 문서

- [README.ko.md](./README.ko.md) — 전체 기능 및 사용법
- [INSTALL.md](./INSTALL.md) — English installation guide
