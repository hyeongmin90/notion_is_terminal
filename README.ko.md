# Terminal4GPTWeb

[English](./README.md)

**GPT 웹에 로컬 WSL/Linux 셸 서버를 직접 노출하지 않고도 실제 터미널 도구를 연결합니다.**

`Terminal4GPTWeb`은 Notion을 **GPT 웹 세션, 로컬 Linux PTY, Playwright 브라우저 사이의 브리지**로 사용합니다.

GPT가 Notion 커넥터를 통해 생성된 페이지를 읽고 수정할 수 있다면 다음과 같은 작업이 가능합니다.

- 현재 터미널 화면 읽기
- 셸 명령 실행
- Enter, 방향키, Backspace, Esc, Function key 입력
- Ctrl-C, Ctrl-O, Ctrl-X 같은 Ctrl 조합 입력
- `nano`, `vim`, `less`, `top`, Codex 같은 TUI 프로그램 조작
- `cd`, 환경변수, REPL, foreground process 등 셸 상태 유지
- Playwright로 웹 페이지를 열고 GPT Vision으로 화면을 확인한 뒤 viewport 좌표로 마우스 조작

한 줄로 표현하면:

> **GPT Web ↔ Notion ↔ PTY / Playwright ↔ WSL / Linux / Web**

Notion은 GPT와 로컬 daemon이 공유하는 입출력 화면이고, 실제 터미널 세션은 로컬 daemon이 관리합니다.

> [!CAUTION]
> 이 프로젝트는 **sandbox가 아닙니다.** Input 블록에 입력된 내용은 daemon을 실행한 Linux 사용자의 권한으로 실행됩니다. root 계정으로 실행하지 말고, 비밀번호·API Key·SSH Key 같은 비밀정보를 Notion을 통해 입력하지 마세요.

---

## 왜 만들었나요?

GPT 웹은 코드 분석, 문제 해결, 원격 작업 지시에 편리하지만 일반적으로 사용자의 로컬 WSL 터미널에 직접 접근할 수는 없습니다.

이 프로젝트는 Notion을 중간 브리지로 사용합니다.

1. GPT가 **Terminal** 블록을 읽습니다.
2. GPT가 **Input** 블록에 명령 또는 키 입력을 작성합니다.
3. `t4g` daemon이 이를 읽어 실제 PTY로 전달합니다.
4. PTY 화면을 다시 **Terminal** 블록에 렌더링합니다.
5. GPT가 갱신된 화면을 읽고 다음 작업을 이어갑니다.

별도의 공개 SSH endpoint, 자체 웹 서버, DB, MQ가 필요하지 않습니다.

---

## 구조

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

Terminal 블록은 stdout을 계속 쌓는 로그가 아니라 **현재 터미널 화면의 snapshot**입니다.

ANSI cursor 이동, 화면 지우기, scrolling, redraw sequence를 로컬에서 `pyte`로 처리한 뒤 최종 화면만 Notion에 기록합니다.

그래서 `top`, `less`, `vim`, Codex처럼 화면을 다시 그리는 프로그램도 텍스트 TUI 수준에서 사용할 수 있습니다.

---

## 주요 기능

- Persistent interactive Bash
- 실제 PTY 기반 동작
- ANSI / VT screen emulation
- `cd`, 환경변수, REPL 상태 유지
- foreground process stdin 전달
- Ctrl-C / Ctrl-D / Ctrl-Z / Ctrl-L / Ctrl-\\
- 방향키, Home/End, Page Up/Down
- Enter, Backspace, Delete, Insert, Tab, Esc
- F1-F12
- raw byte / escape sequence 입력
- runtime terminal resize
- persistent Playwright Chromium session
- Notion Browser Screenshot 자동 갱신
- 별도 child page의 압축 JPEG Vision payload
- observation ID 기반 mouse move/click/drag/scroll
- browser keyboard / navigation 제어
- background daemon
- single-instance lock
- runtime block 자동 복구
- `doctor` 진단

현재 Bash, Python REPL, nano, vim 스타일 key sequence, Codex TUI, interactive prompt, long-running process + Ctrl-C 형태를 실제로 테스트했습니다.

---

## 요구사항

- WSL2 Ubuntu 또는 Linux
- Python 3.11+
- Bash
- Notion internal integration
- integration에 공유된 Notion parent page
- GPT 웹에서 원격 제어하려면 **ChatGPT의 Notion 연결이 필수**
- 개발 워크플로에는 **GitHub 연결 권장**
- 반복 운영 점검에는 지원되는 경우 ChatGPT 일정/자동화 기능 사용 가능

> [!IMPORTANT]
> Terminal4GPTWeb 자체가 별도의 GPT API를 제공하는 구조는 아닙니다. GPT 웹은 생성된 Notion 페이지를 읽고 수정하는 방식으로 로컬 runtime에 접근하므로 GPT 웹에서 사용할 때는 Notion 연결이 필요합니다.

---

## 설치

```bash
git clone https://github.com/hyeongmin90/terminal4gptweb.git
cd terminal4gptweb

python -m venv .venv
source .venv/bin/activate
pip install -e .
playwright install chromium
```

두 번째 명령은 browser controller가 사용할 Chromium binary를 설치합니다.

기본 명령은 다음과 같습니다.

```bash
terminal4gptweb
t4g
```

기존 `notion-terminal`, `nit`도 당분간 호환 alias로 유지합니다.

---

## 초기 설정

Notion internal integration을 만들고 사용할 parent page를 integration에 공유합니다.

이후:

```bash
t4g init
```

wizard가 다음 형태의 child page를 생성합니다.

```text
Terminal
[ 현재 터미널 화면 ]

Input
> 
```

설정 파일은 다음 위치에 저장됩니다.

```text
~/.config/notion_is_terminal/config.toml
```

가능한 환경에서는 권한을 `0600`으로 설정합니다.

초기화하면 다음 3개의 Notion surface가 생성됩니다.

```text
Terminal4GPTWeb
├─ Terminal / Input / Browser      # 실제 제어 페이지
├─ Terminal4GPTWeb Help            # 사람 + 에이전트 사용법
└─ Browser Vision Payload          # Vision용 JPEG payload
```

나중에 메인 Notion 페이지 자체를 삭제했다면 다음 명령으로 전체 페이지와 runtime ID를 다시 만들 수 있습니다.

```bash
t4g reinit
t4g daemon restart
```

최초 초기화 이후에는 parent Notion page ID를 로컬 config에 저장합니다. 기존 버전 config라면 `reinit` 시 parent page를 한 번 다시 물을 수 있습니다.

---

## GPT 웹 연결 구성

Terminal4GPTWeb은 ChatGPT 웹에서 다음 연결을 함께 사용할 때 활용 범위가 가장 넓습니다.

### 1. Notion — 필수

ChatGPT에 Notion을 연결하고 생성된 Terminal4GPTWeb 페이지를 ChatGPT가 읽고 수정할 수 있게 해야 합니다.

GPT 웹이 로컬 runtime에 접근하는 경로는 다음과 같습니다.

```text
GPT Web
  ↓ Notion 읽기/수정
Terminal4GPTWeb 제어 페이지
  ↓ local daemon polling
PTY / Playwright
```

Notion 연결이 없더라도 로컬 daemon 자체는 실행할 수 있지만, GPT 웹에서 이 페이지를 터미널/브라우저 도구처럼 사용할 수는 없습니다.

### 2. GitHub — 개발 작업에 권장

ChatGPT에 GitHub도 연결하면 repository context와 로컬 실행 환경을 함께 사용할 수 있습니다.

권장 개발 흐름:

```text
GitHub
  ↓ issue / PR / commit history / code context
GPT Web
  ↓
Notion → Terminal4GPTWeb
  ↓
로컬 수정 / build / unit test / integration test
  ↓
Playwright + Vision
  ↓
브라우저 E2E 검증
```

GitHub에서는 코드, 이슈, PR, 변경 이력을 확인하고, 실제 머신에서 실행해야 하는 build/test 명령은 Terminal4GPTWeb을 통해 수행하는 식입니다.

예:

```text
이 저장소 최신 변경사항을 리뷰하고 관련 테스트를 로컬에서 실행한 뒤
Playwright로 실제 웹 화면까지 검증해줘.

연결된 이슈를 확인하고 로컬에서 재현한 뒤 수정하고,
테스트를 통과시키고 Browser Vision으로 영향받은 화면까지 확인해줘.
```

### 3. 일정 / 자동화 — OPS에 선택적으로 활용

사용 중인 ChatGPT 환경에서 일정/자동화 기능을 지원한다면 Terminal4GPTWeb을 반복 운영 점검 surface로 사용할 수도 있습니다.

예를 들어 주기적으로 다음을 확인하게 할 수 있습니다.

- `docker ps`, process/service 상태
- 로컬 health endpoint
- 최근 ERROR 로그
- disk / memory 상태
- Playwright 기반 간단한 브라우저 smoke test
- 이상이 있을 때만 알림

예시:

```text
매일 아침 Terminal4GPTWeb 페이지를 확인해.
서비스 health checklist와 최근 오류 로그를 확인하고,
Playwright로 메인 화면 smoke test까지 실행해.
문제가 있을 때만 알려줘.
```

반복 점검은 가능한 한 read-only 명령 위주로 구성하는 것을 권장합니다. 비밀번호, API Key, private key 같은 비밀정보를 Notion Input에 넣으면 안 됩니다.

---

## GPT / 에이전트 동작 규칙

안정적으로 사용하려면 에이전트가 다음 `observe → act → observe` 규칙을 따르는 것이 좋습니다.

1. 먼저 **Terminal** 또는 **Browser Status**를 읽습니다.
2. **Input**에는 한 번에 하나의 명령/action만 작성합니다.
3. Input이 다시 `>`로 초기화될 때까지 기다립니다.
4. 다음 action 전에 갱신된 Terminal/Browser Status를 다시 읽습니다.
5. 브라우저 좌표 action은 반드시 최신 `observation_id`를 사용합니다.
6. Vision이 필요하면 `vision_page_url`을 읽고 `data_base64`를 JPEG로 해석한 뒤 observation ID가 일치하는지 확인합니다.
7. Browser Status가 `failed`라면 이전 좌표를 계속 쓰지 말고 오류를 먼저 처리합니다.

이 규칙은 생성되는 **Terminal4GPTWeb Help** Notion child page에도 같이 기록됩니다.

---

## 활용 예시

### 개발 + 테스트

```text
GitHub context 확인
→ 코드 / 이슈 / PR 분석
→ Terminal에서 로컬 build/test
→ 애플리케이션 실행
→ Playwright로 접속
→ Vision으로 화면 확인
→ 실제 상호작용 후 결과 검증
```

### 로컬 장애 대응

```text
Terminal 확인
→ process/container 상태 확인
→ 로그 확인
→ health request
→ 수정/재시작
→ 다시 검증
```

### Browser E2E

```text
:b goto <url>
→ 최신 Vision payload 확인
→ 좌표 판단
→ :b click <obs_id> <x> <y>
→ 새 observation 대기
→ 변경된 화면 확인
```

### OPS / 정기 점검

고정 checklist를 짧게 두는 방식이 좋습니다.

```text
1. process/container 상태
2. health endpoint
3. 최근 ERROR 로그
4. disk + memory
5. browser smoke test
```

자동화한다면 매번 정상 보고를 보내기보다는 실제 조치가 필요한 실패가 있을 때만 알리도록 구성하는 편이 좋습니다.

---

## 백그라운드 실행

일반적으로는 daemon 모드를 권장합니다.

```bash
t4g daemon start
```

관리 명령:

```bash
t4g daemon status
t4g daemon restart
t4g daemon stop
t4g daemon logs
t4g daemon logs -f
```

runtime 파일:

```text
~/.cache/notion_is_terminal/daemon.pid
~/.cache/notion_is_terminal/daemon.log
~/.cache/notion_is_terminal/instance.lock
```

WSL 터미널 창을 닫아도 daemon은 계속 실행됩니다.

단, 현재는 WSL 자체가 종료되거나 Windows를 재부팅했을 때 자동으로 다시 실행되지는 않습니다.

디버깅할 때는 foreground 실행도 가능합니다.

```bash
t4g run
```

---

## GPT 웹에서 사용하기

생성된 Notion 페이지를 GPT가 Notion 커넥터를 통해 읽고 수정할 수 있다면, 이 페이지가 사실상 **GPT용 터미널 도구 인터페이스**가 됩니다.

예를 들면:

```text
사용자:
Terminal4GPTWeb 페이지 확인해서 git status 실행해줘.

GPT:
1. Terminal 블록 확인
2. Input 블록에 "git status" 작성
3. daemon이 명령 실행
4. Terminal 블록 갱신
5. 결과를 다시 읽고 설명
```

실제 PTY 세션이 계속 유지되므로 GPT는 다음과 같은 흐름도 이어서 사용할 수 있습니다.

```bash
cd ~/project
git status
python3
codex
nano notes.txt
```

명령마다 새로운 shell을 만드는 구조가 아닙니다.

### TUI 프로그램

Codex 같은 일부 TUI는 붙여넣어진 문자열과 실제 Enter key press를 구분합니다.

예를 들어 문자열은 Codex 입력칸에 들어갔지만 submit되지 않은 경우:

```text
> :k ENTER
```

를 별도로 보내 실제 Enter key를 전달할 수 있습니다.

같은 방식으로 editor나 다른 interactive program도 조작할 수 있습니다.

---

## Browser + Vision

daemon은 Playwright Chromium 세션도 지속적으로 유지할 수 있습니다. 각 browser action이 끝날 때마다 새로운 observation을 생성합니다.

```text
Browser Status
  observation_id
  url / title
  viewport / scroll
  cursor
  vision_page_url

Browser Screenshot
  최신 full-resolution viewport 이미지

Browser Vision Payload
  별도 child page에 저장되는 압축 JPEG payload
```

Vision용 base64는 메인 Terminal 페이지를 크게 만들지 않도록 별도의 child page에 저장됩니다. GPT는 시각적 판단이 필요할 때만 해당 페이지를 읽습니다.

브라우저 시작:

```text
> :b goto https://example.com
```

주요 명령:

| 동작 | 명령 |
| --- | --- |
| 이동 | `:b goto <url>` |
| 새 observation 생성 | `:b shot` |
| 마우스 이동 | `:b move <observation_id> <x> <y>` |
| 클릭 | `:b click <observation_id> <x> <y>` |
| 드래그 | `:b drag <observation_id> <x1> <y1> <x2> <y2>` |
| 스크롤 | `:b scroll <dx> <dy>` |
| 문자열 입력 | `:b type <text>` |
| 키 입력 | `:b key <key>` |
| 뒤로 가기 | `:b back` |
| 새로고침 | `:b reload` |

마우스 좌표는 **viewport 기준 CSS pixel**입니다. 기본 viewport는 `1280x720`이고 screenshot도 동일한 CSS-pixel 좌표계로 생성됩니다.

좌표 action에는 반드시 최신 `observation_id`를 사용합니다.

```text
> :b click obs_20261001T173408Z_0001 640 418
```

GPT가 이전 screenshot을 기준으로 클릭하려 하면 daemon은 변경된 화면에 잘못된 좌표를 적용하지 않고 `STALE_OBSERVATION`으로 거부합니다.

정상 action 이후에는 이전 screenshot을 제거하고, 새 screenshot과 Vision payload를 갱신한 뒤 새로운 observation ID를 발급합니다.

---

## 입력 방식

일반 문자열은 **빈 줄로 끝날 때** 실행됩니다.

Notion에서 명령을 입력한 뒤 Enter를 두 번 누르면 됩니다.

```text
> pwd

```

실행 후 Input은 다시 다음 상태로 초기화됩니다.

```text
> 
```

### 제어 명령

| 동작 | 긴 명령 | 축약형 | 예시 |
| --- | --- | --- | --- |
| 특수키 | `:key NAME` | `:k NAME` | `:k ENTER` |
| Ctrl | `:ctrl KEY` | `:c KEY` | `:c O` |
| Raw input | `:send TEXT` | `:s TEXT` | `:s \\e:wq\\r` |
| Resize | `:resize COLSxROWS` | `:rs COLSxROWS` | `:rs 140x50` |

Key alias:

```text
ENTER      RETURN RET ENT
BACKSPACE  BS BKSP
ESC        ESCAPE
DELETE     DEL
INSERT     INS
PAGEUP     PGUP
PAGEDOWN   PGDN
```

추가 지원 키:

```text
UP DOWN LEFT RIGHT
HOME END
TAB
F1 ... F12
```

즉시 처리되는 control token:

```text
^C   실행 중단
^D   EOF
^Z   suspend
^L   clear / redraw
^\   quit signal
```

---

## TUI 사용 예시

### Codex / Claude Code

TUI 입력칸에 문자열은 들어갔지만 submit되지 않은 경우:

```text
> :k ENTER
```

입력 수정:

```text
> :k BS
> :k LEFT
> :k RIGHT
```

### nano

```text
> :c O        # 저장
> :k ENTER    # 파일명 확인
> :c X        # 종료
> :c W        # 검색
```

### vim

```text
> :s \e:wq\r   # 저장 후 종료
> :s \e:q!\r   # 저장하지 않고 종료
```

---

## Runtime block 자동 복구

Notion page ID는 고정 anchor로 보고, Terminal/Input code block ID는 교체 가능한 runtime reference로 관리합니다.

`health_check_interval`마다 Terminal과 Input을 각각 독립적으로 검사합니다.

한쪽 블록만 삭제되거나 trash로 이동하거나 잘못된 위치로 이동한 경우:

1. 정상 블록은 그대로 유지합니다.
2. 문제가 있는 블록만 다시 생성합니다.
3. 원래 Terminal/Input section 위치에 다시 삽입합니다.
4. 변경된 block ID만 `config.toml`에 반영합니다.

두 블록을 모두 삭제하면 둘 다 복구합니다.

Terminal/Input section 자체까지 삭제된 경우에는 원래 위치를 알 수 없으므로 페이지 하단에 새 runtime section을 생성하는 fallback을 사용합니다.

페이지 자체가 삭제되거나 접근 불가능한 경우에는 새 페이지를 임의 생성하지 않고 daemon을 중단합니다.

메인 제어 페이지 자체를 의도적으로 다시 만들려면:

```bash
t4g reinit
t4g daemon restart
```

`reinit`은 기존 로컬 terminal/browser 설정은 유지하고 Notion page와 runtime block ID만 새 값으로 교체합니다.

---

## 설정

기본 경로:

```text
~/.config/notion_is_terminal/config.toml
```

예시:

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

환경변수 `NOTION_TOKEN`이 있으면 config의 token보다 우선합니다.

---

## 진단

```bash
t4g doctor
```

config, Linux / WSL 환경, shell 경로, working directory, Notion page 접근, Terminal/Input block을 확인합니다.

---

## 보안

이 프로젝트는 의도적으로 command allowlist나 sandbox를 제공하지 않습니다.

보안 경계는 daemon을 실행하는 **Linux 사용자 계정**입니다.

즉 GPT가 Notion Input 블록을 수정할 수 있다면 해당 Linux 사용자의 권한으로 명령을 실행할 수 있습니다.

권장사항:

- 전용 non-root 사용자로 daemon 실행
- Notion을 통해 sudo password 입력 금지
- API Key, SSH private key 등 비밀정보 입력 금지
- 생성된 Notion page 접근 권한 제한
- privileged 작업은 별도의 로컬 인증 경로 사용

---

## 한계

Notion은 저지연 터미널 전송 프로토콜이 아닙니다.

터미널 의미론은 유지하지만 모든 입력과 화면 갱신이 Notion API를 거치므로 로컬 터미널보다 지연이 큽니다.

현재 지원하지 않거나 Notion에서 자연스럽게 표현되지 않는 기능:

- 터미널 mouse reporting (Playwright browser mouse control은 지원)
- sixel / kitty graphics
- pixel graphics
- terminal color styling
- clipboard escape sequence
- sub-second keystroke streaming
- multiple simultaneous PTY sessions
- WSL / Windows 재시작 후 자동 실행

---

## 개발

```bash
pip install -e . pytest
pytest
python -m compileall -q notion_is_terminal tests
```

GitHub Actions에서 Python 3.11, 3.12, 3.13을 테스트합니다.

---

## License

MIT
