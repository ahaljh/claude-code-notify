# claude-code-notify

Claude Code 작업 완료 또는 입력 대기 시 Slack DM으로 알림을 보내는 유틸리티.

Claude Code의 [훅(Hooks)](https://docs.anthropic.com/en/docs/claude-code/hooks) 기능과 연동하여, 터미널을 보고 있지 않아도 작업 상태를 실시간으로 확인할 수 있습니다.

## 알림 종류

| 상태 | 설명 | 예시 |
|------|------|------|
| `wait` | 사용자 입력 대기 중 | 권한 승인 요청, 프롬프트 입력 필요 |
| `done` | 작업 완료 | Claude Code가 응답을 마침 |

## 사전 요구사항

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) (패키지 매니저)
- Slack Bot Token (`chat:write` 권한 필요)

## Slack Bot 설정

1. [Slack API](https://api.slack.com/apps)에서 새 앱 생성
2. **OAuth & Permissions** 에서 `chat:write` 스코프 추가
3. 워크스페이스에 앱 설치
4. **Bot User OAuth Token** (`xoxb-...`) 복사

## 설치

```bash
git clone <repository-url>
cd claude-code-notify
uv sync
```

## 환경 설정

`.env.example`을 복사하여 `.env` 파일 생성:

```bash
cp .env.example .env
```

`.env` 파일 편집:

```env
SLACK_BOT_TOKEN=xoxb-your-bot-token
USER_ID=U0XXXXXXXXX  # Slack 프로필에서 확인 (대문자 U로 시작하는 문자열)
LOG_LEVEL=DEBUG       # DEBUG, INFO, WARNING, ERROR, CRITICAL (기본값: DEBUG)
```

> **주의**: `USER_ID`는 사용자 이름이 아닌 사용자 ID입니다. Slack 프로필 > 더보기(⋯) > 멤버 ID 복사에서 확인할 수 있습니다.

## Claude Code 훅 설정

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
            "command": "/path/to/claude-code-notify/notify_claude.sh wait"
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
            "command": "/path/to/claude-code-notify/notify_claude.sh done"
          }
        ]
      }
    ]
  }
}
```

> `/path/to/claude-code-notify/`를 실제 프로젝트 경로로 변경하세요.

## 로깅

로그 파일은 프로젝트 디렉토리에 `slack_notifier.log`로 생성됩니다.

```bash
# 로그 실시간 확인
tail -f slack_notifier.log
```

`LOG_LEVEL` 환경변수로 로그 레벨을 조정할 수 있습니다. 운영 환경에서는 `INFO` 또는 `WARNING`을 권장합니다.
