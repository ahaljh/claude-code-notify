# claude-code-notify

Claude Code 작업 완료 또는 입력 대기 시 Slack DM으로 알림을 보내는 유틸리티.

Claude Code의 [훅(Hooks)](https://docs.anthropic.com/en/docs/claude-code/hooks) 기능과 연동하여, 터미널을 보고 있지 않아도 작업 상태를 실시간으로 확인할 수 있습니다.

## 알림 종류

| 상태 | 설명 | 예시 |
|------|------|------|
| `wait` | 사용자 입력 대기 중 | 권한 승인 요청, 프롬프트 입력 필요 |
| `done` | 작업 완료 | Claude Code가 응답을 마침 |

> **참고**: `idle_prompt` 타입 알림(사용자 미응답 시 발생하는 중복 알림)은 자동으로 필터링됩니다.

## 사전 요구사항

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (패키지 매니저)
- Slack Bot Token (`chat:write` 권한 필요)

## Slack Bot 설정

1. [Slack API](https://api.slack.com/apps)에서 새 앱 생성
2. **OAuth & Permissions** 에서 `chat:write` 스코프 추가
3. 워크스페이스에 앱 설치
4. **Bot User OAuth Token** (`xoxb-...`) 복사

## 설치 및 설정

```bash
# 1. 설치
uv tool install git+https://github.com/ahaljh/claude-code-notify

# 2. 초기 설정 (Slack 토큰 입력 + Claude Code 훅 자동 등록)
uvx claude-code-notify init
```

> **참고**: `uv tool install` 후 PATH 설정 없이도 `uvx` 명령어로 바로 실행할 수 있습니다.

`init` 명령어가 다음을 자동으로 처리합니다:
- Slack Bot Token과 User ID 입력 안내
- `~/.config/claude-code-notify/config.env`에 설정 저장
- `~/.claude/settings.json`에 훅 자동 등록
- (선택) 테스트 알림 전송

설정 완료 후 Claude Code를 재시작하면 알림이 동작합니다.

> **참고**: `USER_ID`는 사용자 이름이 아닌 사용자 ID입니다. Slack 프로필 > 더보기(⋯) > 멤버 ID 복사에서 확인할 수 있습니다.

## 수동 설정

`init` 명령어 대신 직접 설정할 수도 있습니다.

### 설정 파일

`~/.config/claude-code-notify/config.env` 파일 생성:

```env
SLACK_BOT_TOKEN=xoxb-your-bot-token
USER_ID=U0XXXXXXXXX
LOG_LEVEL=INFO
```

### Claude Code 훅

`~/.claude/settings.json`에 다음 훅을 추가합니다:

```json
{
  "hooks": {
    "Notification": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "claude-code-notify notify wait"
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "claude-code-notify notify done"
          }
        ]
      }
    ]
  }
}
```

## 업데이트

```bash
uv tool install --force git+https://github.com/ahaljh/claude-code-notify
```

## 제거

```bash
# 1. 도구 제거
uv tool uninstall claude-code-notify

# 2. 설정 파일 삭제
rm -rf ~/.config/claude-code-notify

# 3. ~/.claude/settings.json에서 claude-code-notify 관련 훅 제거
```

## 로깅

로그 파일: `~/.config/claude-code-notify/notify.log`

```bash
# 로그 실시간 확인
tail -f ~/.config/claude-code-notify/notify.log
```

로그 파일은 자동 로테이션됩니다 (최대 1MB, 백업 3개, 총 ~4MB).

`LOG_LEVEL` 환경변수로 로그 레벨을 조정할 수 있습니다 (DEBUG, INFO, WARNING, ERROR, CRITICAL).
