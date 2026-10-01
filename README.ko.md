# notion_is_terminal

[English](./README.md)

**GPT 웹에 로컬 WSL/Linux 셸 서버를 직접 노출하지 않고도 실제 터미널 도구를 연결합니다.**

`notion_is_terminal`은 Notion 페이지를 **GPT 웹 세션과 로컬 Linux PTY 사이의 브리지**로 사용합니다.

GPT가 Notion 커넥터를 통해 생성된 페이지를 읽고 수정할 수 있다면 다음과 같은 작업이 가능합니다.

- 현재 터미널 화면 읽기
- 셸 명령 실행
- Enter, 방향키, Backspace, Esc, Function key 입력
- Ctrl-C, Ctrl-O, Ctrl-X 같은 Ctrl 조합 입력
- `nano`, `vim`, `less`, `top`, Codex 같은 TUI 프로그램 조작
- `cd`, 환경변수, REPL, foreground process 등 셸 상태 유지

한 줄로 표현하면:

> **GPT Web ↔ Notion ↔ local PTY ↔ WSL / Linux**

Notion은 GPT와 로컬 daemon이 공유하는 입출력 화면이고, 실제 터미널 세션은 로컬 daemon이 관리합니다.

## 데모

<details>
<summary>▶ 데모 영상 보기</summary>

https://github.com/user-attachments/assets/b4f553b5-d72d-4a52-9a13-f1684ed406f3

</details>

> [!CAUTION]
> 이 프로젝트는 **sandbox가 아닙니다.** Input 블록에 입력된 내용은 daemon을 실행한 Linux 사용자의 권한으로 실행됩니다. root 계정으로 실행하지 말고, 비밀번호·API Key·SSH Key 같은 비밀정보를 Notion을 통해 입력하지 마세요.

---

## 왜 만들었나요?

GPT 웹은 코드 분석, 문제 해결, 원격 작업 지시에 편리하지만 일반적으로 사용자의 로컬 WSL 터미널에 직접 접근할 수는 없습니다.

이 프로젝트는 Notion을 중간 브리지로 사용합니다.

1. GPT가 **Terminal** 블록을 읽습니다.
2. GPT가 **Input** 블록에 명령 또는 키 입력을 작성합니다.
3. `notion-terminal` daemon이 이를 읽어 실제 PTY로 전달합니다.
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
- 선택사항: 동일 Notion workspace에 접근할 수 있는 GPT / ChatGPT 웹 세션

---

## 설치

```bash
git clone https://github.com/hyeongmin90/notion_is_terminal.git
cd notion_is_terminal

python -m venv .venv
source .venv/bin/activate
pip install -e .
```

다음 두 명령이 설치됩니다.

```bash
notion-terminal
nit
```

---

## 초기 설정

Notion internal integration을 만들고 사용할 parent page를 integration에 공유합니다.

이후:

```bash
notion-terminal init
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

---

## 백그라운드 실행

일반적으로는 daemon 모드를 권장합니다.

```bash
notion-terminal daemon start
```

관리 명령:

```bash
notion-terminal daemon status
notion-terminal daemon restart
notion-terminal daemon stop
notion-terminal daemon logs
notion-terminal daemon logs -f
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
notion-terminal run
```

---

## GPT 웹에서 사용하기

생성된 Notion 페이지를 GPT가 Notion 커넥터를 통해 읽고 수정할 수 있다면, 이 페이지가 사실상 **GPT용 터미널 도구 인터페이스**가 됩니다.

예를 들면:

```text
사용자:
Notion Terminal 확인해서 git status 실행해줘.

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

환경변수 `NOTION_TOKEN`이 있으면 config의 token보다 우선합니다.

---

## 진단

```bash
notion-terminal doctor
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

- mouse reporting
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
